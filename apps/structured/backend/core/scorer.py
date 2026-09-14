"""ScoringEngine — the deterministic core.

Hard rules from CLAUDE.md:
- No LLM calls, no I/O, no randomness.
- Same input → same output (verified by test_scorer_reproducibility.py).

Phase 3 scoring model:
- Per-dimension score uses pass=1 / warn=0.5 / fail=0 / deferred=excluded,
  divided by counted (non-deferred) checks. Deferred checks live in
  `TableAssessment.deferred[]` for human attestation and do NOT influence
  any number.
- Per-table overall = weighted average across the dimensions that apply
  to this table. N/A dimensions (`Dimension.applicability(profile) == False`)
  are dropped and the remaining weights renormalize to 100%.
- Blocker gating: any `fail` on a `severity="blocker"` rule caps the table's
  overall score at `BLOCKER_CAP` (59 — keeps gated tables in the red band)
  and that rule_id appears in `TableAssessment.gated_by`. Schema-level
  `gated_by` is the union across tables.
- Tier bands: ≥80 green, 60-79 yellow, <60 red. Bands changed in Phase 3
  to align with EXECUTION_PLAN_1.md (was ≥65/40-64/<40 pre-Phase-3).
"""
from __future__ import annotations

from core.dimensions import DIMENSIONS, Dimension, Lens, Rule
from core.models import (
    DimensionResult,
    LensScore,
    MetadataProfile,
    Priority,
    RuleCheck,
    SchemaAssessment,
    TableAssessment,
    TableProfile,
    Tier,
)


GREEN_MIN = 80
YELLOW_MIN = 60
BLOCKER_CAP = 59
_CHECK_STATUS_POINTS = {"pass": 100, "warn": 50, "fail": 0}


def _classify(score: int) -> Tier:
    if score >= GREEN_MIN:
        return "green"
    if score >= YELLOW_MIN:
        return "yellow"
    return "red"


def _stamp(check: RuleCheck, rule: Rule, dim: Dimension) -> RuleCheck:
    """Copy severity/executor/route/dimension_id/explanation from the Rule
    definition onto the RuleCheck so downstream consumers don't have to
    re-look-up the rule registry."""
    from core.models import RuleCheckExplanation
    # Determine evidence basis from executor
    basis = "exact"
    if rule.executor == "hybrid":
        basis = "association"  # regex/heuristic match → needs human confirmation
    elif rule.executor == "metadata":
        basis = "dictionary"
    return check.model_copy(update={
        "severity": rule.severity,
        "executor": rule.executor,
        "route": rule.hybrid_route if rule.executor == "hybrid" else None,
        "dimension_id": dim.id,
        "basis": basis,
        "explanation": RuleCheckExplanation(
            what=rule.explanation.what,
            why=rule.explanation.why,
            example=rule.explanation.example,
        ),
    })


def _finding_uid(table_name: str, rule_id: str, scope_cols: list[str]) -> str:
    """Stable hash for cross-linking a finding. Same inputs → same UID."""
    import hashlib
    payload = f"{table_name}|{rule_id}|{'|'.join(sorted(scope_cols))}"
    return hashlib.sha1(payload.encode()).hexdigest()[:12]


def _stamp_uids(table_name: str, dims: list[DimensionResult]) -> list[DimensionResult]:
    """Stamp finding_uid onto each check in the dimension results."""
    # Rules that primarily assess metadata documentation (not data itself)
    _DICTIONARY_RULES = {"metadata_dictionary", "ops_cadence"}
    updated = []
    for dim in dims:
        new_checks = []
        for c in dim.checks:
            # Extract scope columns from evidence
            scope_cols = (
                c.evidence.get("candidates", [])
                or c.evidence.get("columns", [])
                or ([c.evidence["column"]] if "column" in c.evidence else [])
            )
            uid = _finding_uid(table_name, c.rule_id, scope_cols)
            updates: dict = {"finding_uid": uid}
            # Override basis for known dictionary-dependent rules
            if c.rule_id in _DICTIONARY_RULES and c.basis == "exact":
                updates["basis"] = "dictionary"
            new_checks.append(c.model_copy(update=updates))
        updated.append(dim.model_copy(update={"checks": new_checks}))
    return updated


class ScoringEngine:
    """Stateless, deterministic. One instance is fine for the whole process."""

    def _build_metadata_profile(self, profile: TableProfile) -> MetadataProfile | None:
        if not profile.metadata_entries:
            return None
        return MetadataProfile(
            entries=profile.metadata_entries,
            total_columns=len(profile.metadata_entries),
            columns_with_metadata=len(profile.metadata_entries),
            coverage_pct=100.0,
        )

    def _reconcile_profile(self, profile: TableProfile) -> list:
        from core.reconciler import reconcile

        return reconcile(profile, self._build_metadata_profile(profile))

    def _retune_metadata_dimension(
        self,
        table: TableAssessment,
        profile: TableProfile,
        reconciliation: list,
    ) -> TableAssessment:
        """Replace the flat metadata-rule average with the metadata-quality
        rollup score. Column naming now lives in Schema — metadata is purely
        about documentation and governance coverage.
        """
        metadata_quality = self._build_metadata_quality([profile], reconciliation)
        metadata_dim = next((d for d in table.dimensions if d.id == "metadata"), None)
        if metadata_dim is None:
            return table

        metadata_score = round(metadata_quality.dimension_score)

        updated_dimensions: list[DimensionResult] = []
        for dim in table.dimensions:
            if dim.id == "metadata":
                updated_dimensions.append(dim.model_copy(update={
                    "score": metadata_score,
                    "tier": _classify(metadata_score),
                }))
            else:
                updated_dimensions.append(dim)

        active_results = [d for d in updated_dimensions if d.weight > 0]
        total_weight = sum(d.weight for d in active_results)
        weighted = sum(d.score * d.weight for d in active_results)
        base_score = round(weighted / total_weight) if total_weight else 0
        overall = min(base_score, BLOCKER_CAP) if table.gated_by and base_score > BLOCKER_CAP else base_score

        if table.gated_by:
            klass = "gated"
        elif overall >= GREEN_MIN:
            klass = "ready"
        else:
            klass = "conditional"

        dim_scores = {
            dim.id: dim.score if dim.weight > 0 else None
            for dim in updated_dimensions
        }

        return table.model_copy(update={
            "base_score": base_score,
            "overall_score": overall,
            "tier": _classify(overall),
            "klass": klass,
            "dimensions": updated_dimensions,
            "dimension_scores": dim_scores,
            "summary": self._summarize_table(profile, overall, active_results, table.gated_by),
        })

    # ── Per-dimension ─────────────────────────────────────────────────────
    def _score_dimension(self, dim: Dimension,
                         profile: TableProfile) -> DimensionResult:
        checks: list[RuleCheck] = [
            _stamp(rule.evaluate(profile), rule, dim) for rule in dim.rules
        ]
        # Deferred checks are excluded from the dimension's score — they
        # await human resolution in the attestation queue. They still
        # appear in DimensionResult.checks so the FE can render them.
        counted = [c for c in checks if c.status != "deferred"]
        if not counted:
            # Every check deferred (or no rules): the dimension has no
            # determinate score yet. Render as 0/red so the FE flags it
            # for attestation; the caller decides whether to drop it from
            # the weighted aggregate.
            return DimensionResult(id=dim.id, label=dim.label, weight=dim.weight,
                                   score=0, tier="red", checks=checks)
        points = sum(
            1.0 if c.status == "pass" else 0.5 if c.status == "warn" else 0.0
            for c in counted
        )
        score = round((points / len(counted)) * 100)
        return DimensionResult(
            id=dim.id, label=dim.label, weight=dim.weight,
            score=score, tier=_classify(score), checks=checks,
        )

    # ── Per-table ─────────────────────────────────────────────────────────
    def score_table(self, profile: TableProfile) -> TableAssessment:
        from config import settings

        # Classification decision order (metadata_layer.md §2.3):
        # 1. Engineer override (not yet implemented — future attestation)
        # 2. Explicit metadata entity_classification
        # 3. Row-threshold heuristic (weak signal)
        # 4. Default: included
        is_reference = False
        exclusion_reason = ""

        # Check metadata entity_classification
        if profile.metadata_entries:
            table_classifications = {
                e.entity_classification.strip().lower()
                for e in profile.metadata_entries
                if e.entity_classification
            }
            if table_classifications & {"reference", "staging", "lookup", "enum"}:
                is_reference = True
                exclusion_reason = (
                    f"Metadata declares entity_classification="
                    f"'{next(iter(table_classifications & {'reference', 'staging', 'lookup', 'enum'}))}' "
                    f"— excluded from AI scoring."
                )

        # Row-threshold heuristic (advisory, weaker than metadata)
        if not is_reference and profile.row_count < settings.reference_row_threshold:
            is_reference = True
            exclusion_reason = (
                f"{profile.row_count} rows — below the {settings.reference_row_threshold}-row "
                f"threshold. Treated as a reference/lookup table, excluded from AI scoring."
            )

        if is_reference:
            return TableAssessment(
                table_name=profile.name,
                row_count=profile.row_count,
                column_count=profile.column_count,
                base_score=0,
                overall_score=0,
                tier="red",
                klass="reference",
                included=False,
                excluded_reason=exclusion_reason,
                dimensions=[],
                dimension_scores={},
                summary=f"{profile.name}: {exclusion_reason}",
            )

        # Step 1: applicability — drop dimensions that don't apply.
        active_dims: list[Dimension] = [
            d for d in DIMENSIONS if d.applicability(profile)
        ]
        active_ids = {d.id for d in active_dims}

        # Step 2: score every dimension.
        all_results: list[DimensionResult] = []
        for d in DIMENSIONS:
            res = self._score_dimension(d, profile)
            if d.id not in active_ids:
                res = res.model_copy(update={"weight": 0})
            all_results.append(res)

        # Step 3: weighted average across active dimensions.
        active_results = [r for r in all_results if r.id in active_ids]
        total_weight = sum(r.weight for r in active_results)
        weighted = sum(r.score * r.weight for r in active_results)
        base_score = round(weighted / total_weight) if total_weight else 0
        overall = base_score

        # Step 4: blocker gating.
        gated_by: list[str] = []
        for r in active_results:
            for c in r.checks:
                if c.severity == "blocker" and c.status == "fail":
                    gated_by.append(c.rule_id)
        if gated_by and overall > BLOCKER_CAP:
            overall = BLOCKER_CAP

        # Step 5: collect deferred candidates.
        deferred: list[RuleCheck] = [
            c for r in all_results for c in r.checks if c.status == "deferred"
        ]

        # Step 6: recommendations.
        recs: list[str] = []
        for r in active_results:
            for c in r.checks:
                if c.status in ("pass", "deferred"):
                    continue
                if c.recommendation:
                    recs.append(c.recommendation)

        # Step 7: klass assignment.
        if gated_by:
            klass = "gated"
        elif overall >= GREEN_MIN:
            klass = "ready"
        else:
            klass = "conditional"

        summary = self._summarize_table(profile, overall, active_results, gated_by)

        # Build dimension_scores dict and field_issues
        dim_scores = {
            d.id: d.score if d.weight > 0 else None
            for d in all_results
        }
        # Stamp finding UIDs for cross-linking
        all_results = _stamp_uids(profile.name, all_results)
        # Mark basis as "sample" when data was row-capped
        if profile.profiled_row_count and profile.profiled_row_count < profile.row_count:
            all_results = [
                dim.model_copy(update={"checks": [
                    c.model_copy(update={"basis": "sample"})
                    if c.basis == "exact" else c
                    for c in dim.checks
                ]})
                for dim in all_results
            ]
        field_issues = self._build_field_issues(all_results)

        return TableAssessment(
            table_name=profile.name,
            row_count=profile.row_count,
            column_count=profile.column_count,
            profiled_row_count=profile.profiled_row_count or profile.row_count,
            base_score=base_score,
            overall_score=overall,
            tier=_classify(overall),
            klass=klass,
            included=True,
            dimensions=all_results,
            dimension_scores=dim_scores,
            field_issues=field_issues,
            summary=summary,
            recommendations=recs[:10],
            gated_by=gated_by,
            deferred=deferred,
        )

    # ── Multi-table → schema ──────────────────────────────────────────────
    def score_schema(self, profiles: list[TableProfile]) -> SchemaAssessment:
        if not profiles:
            raise ValueError("score_schema requires at least one TableProfile")

        tables = [self.score_table(p) for p in profiles]

        reconciliations_by_table: dict[str, list] = {}
        all_reconciliation = []
        for profile in profiles:
            findings = self._reconcile_profile(profile)
            reconciliations_by_table[profile.name] = findings
            all_reconciliation.extend(findings)

        tables = [
            table if table.klass == "reference"
            else self._retune_metadata_dimension(
                table,
                profile,
                reconciliations_by_table[profile.name],
            )
            for profile, table in zip(profiles, tables)
        ]

        # Split into assessed (non-reference) and reference.
        assessed = [t for t in tables if t.klass != "reference"]
        reference = [t for t in tables if t.klass == "reference"]

        if not assessed:
            return SchemaAssessment(
                base_score=0, overall_score=0, tier="red", verdict="Conditional",
                dimensions=[], tables=tables, table_count=len(tables),
                assessed_count=0, reference_count=len(reference),
                summary="All tables are below the row threshold — no assessed tables.",
            )

        # Roll up dimensions from ASSESSED tables only.
        schema_active_ids: set[str] = set()
        for t in assessed:
            for d in t.dimensions:
                if d.weight > 0:
                    schema_active_ids.add(d.id)

        rolled: list[DimensionResult] = []
        for dim in DIMENSIONS:
            scores = [
                next((d.score for d in t.dimensions
                      if d.id == dim.id and d.weight > 0), None)
                for t in assessed
            ]
            present = [s for s in scores if s is not None]
            avg = round(sum(present) / len(present)) if present else 0
            severity_rank = {"pass": 0, "warn": 1, "fail": 2, "deferred": 3}
            rule_to_worst: dict[str, RuleCheck] = {}
            for t in assessed:
                t_dim = next((d for d in t.dimensions if d.id == dim.id), None)
                if not t_dim:
                    continue
                for c in t_dim.checks:
                    prev = rule_to_worst.get(c.rule_id)
                    if prev is None or severity_rank[c.status] > severity_rank[prev.status]:
                        rule_to_worst[c.rule_id] = c

            weight = dim.weight if dim.id in schema_active_ids else 0
            rolled.append(DimensionResult(
                id=dim.id, label=dim.label, weight=weight,
                score=avg, tier=_classify(avg),
                checks=list(rule_to_worst.values()),
            ))

        # Schema overall from assessed tables.
        active_rolled = [r for r in rolled if r.weight > 0]
        total_weight = sum(r.weight for r in active_rolled)
        weighted_total = sum(r.score * r.weight for r in active_rolled)
        base_score = round(weighted_total / total_weight) if total_weight else 0
        overall = base_score

        # Schema gating from assessed tables.
        schema_gated: list[str] = []
        seen_gates: set[str] = set()
        for t in assessed:
            for rid in t.gated_by:
                if rid not in seen_gates:
                    seen_gates.add(rid)
                    schema_gated.append(rid)
        if schema_gated and overall > BLOCKER_CAP:
            overall = BLOCKER_CAP

        # Verdict.
        if schema_gated:
            verdict = "At Risk"
        elif overall >= GREEN_MIN:
            verdict = "AI Ready"
        else:
            verdict = "Conditional"

        # Action groups — consolidate findings by rule across assessed tables.
        action_groups = self._build_action_groups(assessed)

        # Score-impact simulation: compute Δ for each action group's rule
        for ag in action_groups:
            # Simulate on the first affected table for a representative delta
            target_table = next(
                (t for t in assessed if t.table_name in ag.affected_tables), None
            )
            if target_table:
                ag.score_delta = self.simulate_resolution(target_table, ag.rule_id)

        # Dimension detail — per-dimension weak tables + issues.
        dim_detail = self._build_dimension_detail(assessed, rolled)

        # Build MetadataQuality summary
        mq = self._build_metadata_quality(profiles, all_reconciliation)

        priorities = self._build_priorities(assessed)
        summary = self._summarize_schema(tables, overall, rolled, schema_gated)

        return SchemaAssessment(
            base_score=base_score,
            overall_score=overall,
            tier=_classify(overall),
            verdict=verdict,
            summary=summary,
            top_priorities=priorities,
            dimensions=rolled,
            tables=tables,
            table_count=len(tables),
            gated_by=schema_gated,
            active_dimensions=sorted(schema_active_ids),
            action_groups=action_groups,
            dimension_detail=dim_detail,
            assessed_count=len(assessed),
            reference_count=len(reference),
            reconciliation=all_reconciliation,
            metadata_quality=mq,
            lens_scores=self.compute_lens_scores(tables),
        )

    # ── Helpers ───────────────────────────────────────────────────────────
    def _build_field_issues(self, dims: list[DimensionResult]) -> list:
        """Explode multi-column findings into per-field entries. Table-level
        findings (no target columns in evidence) are excluded.
        Only blocker and warning severity (high-impact) are surfaced."""
        from core.models import FieldIssue
        issues: list[FieldIssue] = []
        for d in dims:
            for c in d.checks:
                if c.status in ("pass", "deferred"):
                    continue
                if c.severity not in ("blocker", "warning"):
                    continue
                # Extract target columns from evidence dict
                targets = c.evidence.get("candidates", []) or c.evidence.get("columns", [])
                if not targets:
                    col = c.evidence.get("column")
                    if col:
                        targets = [col]
                if targets:
                    for field in targets:
                        issues.append(FieldIssue(
                            field=field,
                            dimension=d.id,
                            severity=c.severity,
                            issue=c.recommendation or c.detail,
                        ))
        return issues

    def _build_priorities(self, tables: list[TableAssessment]) -> list[Priority]:
        """Collect failing/warning checks across all tables, rank by:
           1. blocker severity before non-blocker
           2. fail before warn
           3. dimension weight DESC
           4. table order (stable)
        Return top 5 distinct (rule_id, table) priorities. Deferred checks
        are excluded — they live in their own attestation section.
        """
        weight_by_dim = {d.id: d.weight for d in DIMENSIONS}
        items: list[tuple[int, int, int, int, Priority]] = []

        for ti, t in enumerate(tables):
            for dim in t.dimensions:
                for chk in dim.checks:
                    if chk.status in ("pass", "deferred"):
                        continue
                    if not chk.recommendation:
                        continue
                    blocker_rank = 0 if chk.severity == "blocker" else 1
                    sev_rank = 0 if chk.status == "fail" else 1
                    items.append((
                        blocker_rank,
                        sev_rank,
                        -weight_by_dim.get(dim.id, 0),
                        ti,
                        Priority(
                            severity="high" if chk.status == "fail" else "medium",
                            title=chk.recommendation,
                            dimension_id=dim.id,
                            table_name=t.table_name,
                        ),
                    ))
        items.sort(key=lambda x: (x[0], x[1], x[2], x[3]))
        seen: set[str] = set()
        out: list[Priority] = []
        for *_, p in items:
            key = f"{p.dimension_id}::{p.title}"
            if key in seen:
                continue
            seen.add(key)
            out.append(p)
            if len(out) >= 5:
                break
        return out

    def _build_action_groups(self, assessed: list[TableAssessment]) -> list:
        """Consolidate findings by rule across assessed tables into ActionGroups.

        Each rule_id that has at least one non-pass, non-deferred check appears
        ONCE with all affected table names. Sorted by severity then table count.
        Excludes universal info-level warnings (fire on ALL assessed tables).
        """
        from core.models import ActionGroup, ActionTableDetail
        groups: dict[str, dict] = {}
        sev_rank = {"blocker": 0, "warning": 1, "info": 2}
        all_table_names = {t.table_name for t in assessed}

        for t in assessed:
            for d in t.dimensions:
                for c in d.checks:
                    if c.status in ("pass", "deferred"):
                        continue
                    rid = c.rule_id
                    if rid not in groups:
                        groups[rid] = {
                            "rule_id": rid,
                            "issue": c.title,
                            "severity": c.severity,
                            "dimension_id": c.dimension_id or d.id,
                            "recommended_fix": c.recommendation or "",
                            "explanation": c.explanation,
                            "tables": set(),
                            "table_details": [],
                        }
                    groups[rid]["tables"].add(t.table_name)
                    groups[rid]["table_details"].append(ActionTableDetail(
                        table_name=t.table_name,
                        detail=c.detail or "",
                        evidence=c.evidence or {},
                    ))
                    if sev_rank.get(c.severity, 2) < sev_rank.get(groups[rid]["severity"], 2):
                        groups[rid]["severity"] = c.severity

        result: list[ActionGroup] = []
        for g in groups.values():
            if g["severity"] == "info" and g["tables"] == all_table_names:
                continue
            tables_list = sorted(g["tables"])
            result.append(ActionGroup(
                rule_id=g["rule_id"],
                issue=g["issue"],
                severity=g["severity"],
                dimension_id=g["dimension_id"],
                recommended_fix=g["recommended_fix"],
                explanation=g["explanation"],
                affected_tables=tables_list,
                table_count=len(tables_list),
                table_details=g["table_details"],
            ))
        result.sort(key=lambda a: (sev_rank.get(a.severity, 9), -a.table_count))
        return result

    def _build_dimension_detail(self, assessed: list[TableAssessment],
                                rolled: list[DimensionResult]) -> list:
        """Per-dimension detail: weak tables + issue titles."""
        from core.models import DimensionDetail
        detail: list[DimensionDetail] = []
        for dim_r in rolled:
            if dim_r.weight == 0:
                detail.append(DimensionDetail(
                    id=dim_r.id, label=dim_r.label, score=None,
                ))
                continue
            weak: list[str] = []
            issues: set[str] = set()
            for t in assessed:
                t_dim = next((d for d in t.dimensions if d.id == dim_r.id), None)
                if not t_dim:
                    continue
                if t_dim.score < GREEN_MIN:
                    weak.append(t.table_name)
                for c in t_dim.checks:
                    if c.status in ("fail", "warn"):
                        issues.add(c.title)
            detail.append(DimensionDetail(
                id=dim_r.id, label=dim_r.label, score=dim_r.score,
                weak_tables=sorted(weak),
                issues=sorted(issues),
            ))
        return detail

    def _build_metadata_quality(self, profiles: list[TableProfile],
                                reconciliation: list) -> "MetadataQuality":
        """Build BOTL v2.0 metadata quality assessment.

        Pipeline (from metadatalogic.md):
          1. EXTRACTION — extract each BOTL field from profile.metadata_entries
          2. VALIDITY   — validate each present field
          3. ESCALATION — apply ESC-1..ESC-4 (fail-closed)
          4. SCORING    — earned/possible per category, overall = mean(4)
          5. GATES      — RED if HIGH fails, YELLOW if MEDIUM fails, else GREEN
          6. REMEDIATION — ranked list for frontend display
        """
        from core.botl_register import (
            REGISTER, evaluate_profile, FieldResult,
        )
        from core.models import (
            MetadataQuality, BOTLFieldStatus, BOTLCategoryScore, BOTLRemediation,
        )

        # Use first profile (single-table is the common case)
        profile = profiles[0] if profiles else None
        if profile is None:
            return MetadataQuality(
                verdict="RED",
                dimension_score=0,
                findings=["No tables to assess"],
            )

        # Steps 1-3: extract, validate, escalate
        field_results: list[FieldResult] = evaluate_profile(profile)

        # Step 4: Scoring — compute points earned per field
        _SEVERITY_PTS = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}
        field_statuses: list[BOTLFieldStatus] = []
        for fr in field_results:
            eff_sev = fr.effective_severity or fr.field.severity
            pts_possible = float(_SEVERITY_PTS[eff_sev])
            pts_earned = 0.0

            if fr.valid:
                if fr.extraction.column_coverage:
                    cov = fr.extraction.column_coverage
                    fraction = cov["covered"] / max(cov["total"], 1)
                    pts_earned = pts_possible * fraction
                else:
                    pts_earned = pts_possible

            status_val: str
            if fr.extraction.status == "absent":
                status_val = "absent"
            elif not fr.valid:
                status_val = "invalid"
            else:
                status_val = "present"

            field_statuses.append(BOTLFieldStatus(
                field_id=fr.field.id,
                field_name=fr.field.name,
                category=fr.field.category,
                status=status_val,
                valid=fr.valid,
                reason=fr.reason,
                effective_severity=eff_sev,
                points_possible=round(pts_possible, 2),
                points_earned=round(pts_earned, 2),
                column_coverage=fr.extraction.column_coverage,
                escalation_applied=fr.escalation_applied,
                why=fr.field.why,
            ))

        # Category scores — mean of 4 categories (equal weight)
        cat_scores: list[BOTLCategoryScore] = []
        scores_dict: dict[str, float] = {}
        for cat in ("business", "operational", "technical", "lineage"):
            cat_fields = [f for f in field_statuses if f.category == cat]
            possible = sum(f.points_possible for f in cat_fields)
            earned = sum(f.points_earned for f in cat_fields)
            score_ratio = earned / possible if possible > 0 else 0.0
            scores_dict[cat] = round(score_ratio, 4)
            cat_scores.append(BOTLCategoryScore(
                category=cat,
                score_pct=round(score_ratio * 100),
                points_earned=round(earned, 2),
                points_possible=round(possible, 2),
                fields_total=len(cat_fields),
                fields_present=sum(1 for f in cat_fields if f.status == "present"),
                fields_valid=sum(1 for f in cat_fields if f.valid),
            ))

        overall_score = sum(scores_dict.values()) / 4.0
        scores_dict["overall"] = round(overall_score, 4)

        # Step 5: Gates — RED if any HIGH fails, YELLOW if any MEDIUM fails
        verdict = "GREEN"
        for fs in field_statuses:
            if fs.effective_severity == "HIGH" and not fs.valid:
                # For column-grain HIGH fields: gate threshold is 0.95 (B3/T2) or 1.0 (B13)
                if fs.column_coverage:
                    cov = fs.column_coverage
                    frac = cov["covered"] / max(cov["total"], 1)
                    threshold = 1.0 if fs.field_id == "B13" else 0.95
                    if frac < threshold:
                        verdict = "RED"
                        break
                else:
                    verdict = "RED"
                    break
        if verdict != "RED":
            for fs in field_statuses:
                if fs.effective_severity == "MEDIUM" and not fs.valid:
                    verdict = "YELLOW"
                    break

        # Step 6: Remediation — ranked: HIGH first, then MEDIUM, by points desc
        remediation: list[BOTLRemediation] = []
        failed_fields = [f for f in field_statuses if not f.valid]
        # Sort: HIGH before MEDIUM before LOW, then by points_possible desc
        sev_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
        failed_fields.sort(key=lambda f: (sev_order.get(f.effective_severity, 3), -f.points_possible))

        for i, ff in enumerate(failed_fields):
            pts_recoverable = ff.points_possible - ff.points_earned
            owner = "business" if ff.category == "business" else "platform"
            remediation.append(BOTLRemediation(
                field_id=ff.field_id,
                field_name=ff.field_name,
                priority=i + 1,
                points_recoverable=round(pts_recoverable, 2),
                effective_severity=ff.effective_severity,
                category=ff.category,
                reason=ff.reason or f"{ff.field_name} is not documented.",
                why=ff.why,
                owner_route=owner,
            ))

        # Escalations summary
        escalations_applied = []
        for fr in field_results:
            if fr.escalation_applied:
                escalations_applied.append({
                    "rule": fr.escalation_applied,
                    "field_id": fr.field.id,
                    "basis": "fail_closed" if fr.extraction.status == "absent" else "triggered",
                })

        # Backward compat: dimension_score = round(overall * 100)
        dimension_score = round(overall_score * 100)

        # Findings summary for backward compat
        findings: list[str] = []
        if not profile.metadata_entries:
            findings.append("No data dictionary uploaded")
        high_missing = sum(1 for f in field_statuses if f.effective_severity == "HIGH" and not f.valid)
        if high_missing:
            findings.append(f"{high_missing} HIGH-severity fields missing or invalid")

        # Reconciliation accuracy from existing reconciler
        all_entries = [e for p in profiles for e in p.metadata_entries]
        verifiable = [f for f in reconciliation if f.status == "confirmed"]
        total = max(len(all_entries), 1)
        if verifiable:
            recon_accuracy = max(0.0, 1.0 - (len(verifiable) / total))
        else:
            recon_accuracy = 1.0 if all_entries else 0.0

        return MetadataQuality(
            standard_version="2.0",
            verdict=verdict,
            scores=scores_dict,
            categories=cat_scores,
            fields=field_statuses,
            escalations_applied=escalations_applied,
            remediation=remediation,
            dimension_score=dimension_score,
            findings=findings,
            weighted_coverage=round(overall_score * 100, 1),
            reconciliation_accuracy=round(recon_accuracy * 100, 1),
        )

    def _summarize_table(self, profile: TableProfile, overall: int,
                         dims: list[DimensionResult],
                         gated_by: list[str]) -> str:
        tier = _classify(overall)
        if not dims:
            return f"{profile.name}: no applicable dimensions to score."
        worst = min(dims, key=lambda d: d.score)
        if gated_by:
            return (f"{profile.name}: Gated at {overall}/100 — "
                    f"{len(gated_by)} blocker(s) must be resolved before AI use. "
                    f"Weakest dimension: {worst.label} ({worst.score}).")
        if tier == "green":
            return (f"{profile.name}: AI-ready with {overall}/100. "
                    f"Weakest dimension: {worst.label} ({worst.score}).")
        if tier == "yellow":
            return (f"{profile.name}: Conditional ({overall}/100). "
                    f"Focus area: {worst.label} ({worst.score}).")
        return (f"{profile.name}: Remediate before use ({overall}/100). "
                f"Top blocker: {worst.label} ({worst.score}).")

    def _summarize_schema(self, tables: list[TableAssessment], overall: int,
                          dims: list[DimensionResult],
                          gated_by: list[str]) -> str:
        if len(tables) == 1:
            return tables[0].summary
        worst_table = min(tables, key=lambda t: t.overall_score)
        active_dims = [d for d in dims if d.weight > 0]
        worst_dim = min(active_dims, key=lambda d: d.score) if active_dims else None
        gate_phrase = (f" Schema gated by {len(gated_by)} blocker(s)."
                       if gated_by else "")
        if worst_dim:
            return (
                f"Schema-level verdict: {overall}/100 across {len(tables)} tables.{gate_phrase} "
                f"A schema is only as ready as its weakest table — "
                f"{worst_table.table_name} scored {worst_table.overall_score}. "
                f"Cross-cutting weakness: {worst_dim.label} ({worst_dim.score})."
            )
        return (
            f"Schema-level verdict: {overall}/100 across {len(tables)} tables.{gate_phrase} "
            f"Weakest table: {worst_table.table_name} ({worst_table.overall_score})."
        )

    # ── Lens scores ──────────────────────────────────────────────────────
    def compute_lens_scores(self, tables: list[TableAssessment]) -> list[LensScore]:
        """Aggregate checks by lens (DQ/ML/AI) across all assessed tables.

        Each rule has a `lens` frozenset on the Rule definition. We match
        checks back to their rule via rule_id, then aggregate pass/total per lens.
        """
        _LENS_LABELS = {"DQ": "Data Quality", "ML": "ML Readiness", "AI": "AI Readiness"}
        # Build rule→lens lookup from DIMENSIONS
        rule_lens: dict[str, frozenset] = {}
        for dim in DIMENSIONS:
            for rule in dim.rules:
                rule_lens[rule.id] = rule.lens

        # Collect checks across assessed (non-reference) tables
        lens_pass: dict[str, int] = {"DQ": 0, "ML": 0, "AI": 0}
        lens_total: dict[str, int] = {"DQ": 0, "ML": 0, "AI": 0}

        for table in tables:
            if not table.included:
                continue
            for dim in table.dimensions:
                if dim.weight == 0:
                    continue
                for check in dim.checks:
                    if check.status == "deferred":
                        continue
                    lenses = rule_lens.get(check.rule_id, frozenset())
                    for lens in lenses:
                        lens_total[lens] += 1
                        if check.status == "pass":
                            lens_pass[lens] += 1

        results: list[LensScore] = []
        for lens_id in ("DQ", "ML", "AI"):
            total = lens_total[lens_id]
            passed = lens_pass[lens_id]
            score = round((passed / total) * 100) if total else 0
            results.append(LensScore(
                lens=lens_id,
                label=_LENS_LABELS[lens_id],
                score=score,
                tier=_classify(score),
                check_count=total,
                pass_count=passed,
            ))
        return results

    # ── Score-impact simulation ──────────────────────────────────────────
    def simulate_resolution(self, table: TableAssessment, rule_id: str) -> int:
        """Returns Δ to overall_score if a specific rule were resolved (→ pass).

        Simulates flipping one non-pass check to pass and recomputing the
        weighted average. Returns the point gain (always >= 0).
        """
        active_dims = [d for d in table.dimensions if d.weight > 0]
        if not active_dims:
            return 0

        # Current score
        current = table.overall_score

        # Simulate: flip the target rule to pass in its dimension
        simulated_dims: list[DimensionResult] = []
        for dim in active_dims:
            found = False
            new_checks = []
            for c in dim.checks:
                if c.rule_id == rule_id and c.status in ("warn", "fail"):
                    new_checks.append(c.model_copy(update={"status": "pass"}))
                    found = True
                else:
                    new_checks.append(c)
            if found:
                # Recompute dimension score
                counted = [c for c in new_checks if c.status != "deferred"]
                if counted:
                    points = sum(
                        1.0 if c.status == "pass" else 0.5 if c.status == "warn" else 0.0
                        for c in counted
                    )
                    new_score = round((points / len(counted)) * 100)
                else:
                    new_score = 0
                simulated_dims.append(dim.model_copy(update={"score": new_score}))
            else:
                simulated_dims.append(dim)

        # Recompute weighted average
        total_weight = sum(d.weight for d in simulated_dims)
        weighted = sum(d.score * d.weight for d in simulated_dims)
        simulated_overall = round(weighted / total_weight) if total_weight else 0

        # Apply blocker gating — if the resolved rule was the blocker, remove cap
        remaining_blockers = [
            c.rule_id for d in simulated_dims for c in d.checks
            if c.severity == "blocker" and c.status == "fail" and c.rule_id != rule_id
        ]
        if remaining_blockers and simulated_overall > BLOCKER_CAP:
            simulated_overall = BLOCKER_CAP

        return max(0, simulated_overall - current)


# ─── Re-score after attestation approval ──────────────────────────────────

DISMISSIBLE_RULES = frozenset({
    "temporal_ordering",
    "temporal_granularity",
    "stats_no_constants",
    "labels_balance",
    "features_cardinality",
})


def rescore_with_approvals(
    assessment: SchemaAssessment,
    approved_rule_ids: list[str],
    acknowledged_blocker_ids: list[str] | None = None,
    dismissed_rule_ids: list[str] | None = None,
) -> SchemaAssessment:
    """Re-compute the schema assessment with approved deferred items resolved
    to `pass` and acknowledged blockers removed from gating.

    This doesn't re-run the profiler or LLM — it takes the existing checks
    and reclassifies the specified deferred rules to pass, then recomputes
    gating + weighted scores. Acknowledged blockers remain as `fail` in checks
    but are excluded from gating (the user accepted the risk).
    Dismissed rules (from the DISMISSIBLE_RULES set) are converted from
    warn/fail to pass — the user confirmed expected behavior.
    The narrative/strengths/recs stay unchanged.
    """
    approved = set(approved_rule_ids)
    acknowledged = set(acknowledged_blocker_ids or [])
    dismissed = set(dismissed_rule_ids or []) & DISMISSIBLE_RULES
    if not approved and not acknowledged and not dismissed:
        return assessment

    new_tables: list[TableAssessment] = []
    for table in assessment.tables:
        new_dims: list[DimensionResult] = []
        for dim in table.dimensions:
            new_checks: list[RuleCheck] = []
            for c in dim.checks:
                if c.rule_id in approved and c.status == "deferred":
                    new_checks.append(c.model_copy(update={"status": "pass"}))
                elif c.rule_id in dismissed and c.status in ("warn", "fail"):
                    new_checks.append(c.model_copy(update={"status": "pass"}))
                else:
                    new_checks.append(c)

            counted = [c for c in new_checks if c.status != "deferred"]
            if counted:
                points = sum(
                    1.0 if c.status == "pass" else 0.5 if c.status == "warn" else 0.0
                    for c in counted
                )
                score = round((points / len(counted)) * 100)
            else:
                score = 0
            new_dims.append(dim.model_copy(update={
                "score": score,
                "tier": _classify(score),
                "checks": new_checks,
            }))

        # Recompute table overall + gating
        active = [d for d in new_dims if d.weight > 0]
        total_weight = sum(d.weight for d in active)
        weighted = sum(d.score * d.weight for d in active)
        base_score = round(weighted / total_weight) if total_weight else 0
        overall = base_score

        gated_by: list[str] = []
        for d in active:
            for c in d.checks:
                if c.severity == "blocker" and c.status == "fail" and c.rule_id not in acknowledged:
                    gated_by.append(c.rule_id)
        if gated_by and overall > BLOCKER_CAP:
            overall = BLOCKER_CAP

        deferred = [c for d in new_dims for c in d.checks if c.status == "deferred"]

        new_tables.append(table.model_copy(update={
            "base_score": base_score,
            "overall_score": overall,
            "tier": _classify(overall),
            "dimensions": new_dims,
            "gated_by": gated_by,
            "deferred": deferred,
        }))

    # Schema-level rollup
    schema_gated: list[str] = []
    seen_gates: set[str] = set()
    for t in new_tables:
        for rid in t.gated_by:
            if rid not in seen_gates:
                seen_gates.add(rid)
                schema_gated.append(rid)

    # Schema overall from table scores
    active_rolled = [d for d in assessment.dimensions if d.weight > 0]
    # Recompute from per-table dimension scores
    new_schema_dims: list[DimensionResult] = []
    for dim in assessment.dimensions:
        if dim.weight == 0:
            new_schema_dims.append(dim)
            continue
        scores = [
            next((d.score for d in t.dimensions if d.id == dim.id and d.weight > 0), None)
            for t in new_tables
        ]
        present = [s for s in scores if s is not None]
        avg = round(sum(present) / len(present)) if present else 0
        new_schema_dims.append(dim.model_copy(update={
            "score": avg,
            "tier": _classify(avg),
        }))

    active_schema = [d for d in new_schema_dims if d.weight > 0]
    total_w = sum(d.weight for d in active_schema)
    weighted_s = sum(d.score * d.weight for d in active_schema)
    schema_base_score = round(weighted_s / total_w) if total_w else 0
    schema_overall = schema_base_score
    if schema_gated and schema_overall > BLOCKER_CAP:
        schema_overall = BLOCKER_CAP

    return assessment.model_copy(update={
        "base_score": schema_base_score,
        "overall_score": schema_overall,
        "tier": _classify(schema_overall),
        "dimensions": new_schema_dims,
        "tables": new_tables,
        "gated_by": schema_gated,
    })
