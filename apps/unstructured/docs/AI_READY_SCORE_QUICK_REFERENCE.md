# AI Ready Score Generation - Quick Reference

## Overview

The **AI Ready Score** (0-100) indicates how ready your data is for AI/RAG applications. It combines 5 quality dimensions through a data pipeline.

---

## The 5-Stage Pipeline

### Stage 1: EXTRACT & PREPROCESS
- **What**: Text extraction and chunking
- **Input**: PDF, DOCX, XLSX, TXT files
- **Process**: Load → Normalize → Chunk → Save processed_chunks_*.jsonl
- **Output**: ~3,800+ chunks from your documents

### Stage 2: SCORE
- **What**: Calculate quality metrics per chunk
- **Metrics**:
  - **Confidence** (0-100): How good was text extraction?
  - **Coherence** (0-100): Do sentences flow together?
  - **Noise** (0-100): How much junk/artifacts? (lower is better)
- **Output**: metrics.json with avg scores

### Stage 3: FINGERPRINT & AI READY SCORE
- **What**: Aggregate metrics into final readiness score
- **Formula**: Weighted combination of 5 factors (see below)
- **Output**: fingerprint.json with score 0-100

### Stages 4-5: VALIDATE & INDEX
- **Validation**: DQ rule checking
- **Indexing**: Vector embeddings for search

---

## AI Ready Score Formula

```
AI_READY_SCORE =
    (Data Quality     × 0.25) +
    (Completeness     × 0.20) +
    (Consistency      × 0.20) +
    (Coverage         × 0.15) +
    (Compliance       × 0.20)
```

### Component Details

| Component | Weight | What It Measures | How Calculated |
|-----------|--------|------------------|-----------------|
| **Data Quality** | 25% | Individual chunk quality | Avg of confidence (33%) + coherence (33%) + noise (34%) |
| **Completeness** | 20% | Data field coverage | (1 - violations) × 70% + chunk_coverage × 30% |
| **Consistency** | 20% | Quality uniformity | Ratio of excellent/good chunks vs poor |
| **Coverage** | 15% | Processing completeness | Actual chunks / expected chunks (capped at 100%) |
| **Compliance** | 20% | Policy adherence | Policy evaluation pass/fail + violation count |

---

## Quality Score Interpretation

| Range | Status | Meaning |
|-------|--------|---------|
| 90-100 | 🟢 EXCELLENT | Production-ready for AI/RAG |
| 75-89 | 🟡 GOOD | Ready with minor improvements |
| 60-74 | 🟠 FAIR | Improvements recommended |
| 40-59 | 🔴 POOR | Major improvements needed |
| 0-39 | 🔴 NOT READY | Significant rework required |

---

## Example: Your Documents

```
INPUT:
  • Document1.pdf (45 pages)
  • Document2.docx (20 pages)

AFTER EXTRACTION:
  • 2,850 chunks from Document1
  • 980 chunks from Document2
  • TOTAL: 3,830 chunks

QUALITY METRICS:
  • Avg Confidence: 84.5 (extraction quality)
  • Avg Coherence: 72.1 (sentence flow)
  • Avg Noise: 18.3 (artifacts/junk)

DISTRIBUTION:
  • Excellent (>90): 1,950 chunks (50.9%)
  • Good (70-90): 1,384 chunks (36.1%)
  • Fair (50-70): 426 chunks (11.1%)
  • Poor (<50): 70 chunks (1.8%)

DQ VALIDATION:
  • Missing fields: 12
  • Out-of-range values: 5
  • Policy violations: 0

AI READY SCORE CALCULATION:
  ┌──────────────────────────────────┐
  │ Data Quality:    78.9 × 0.25 = 19.7
  │ Completeness:    85.5 × 0.20 = 17.1
  │ Consistency:     74.2 × 0.20 = 14.8
  │ Coverage:        98.0 × 0.15 = 14.7
  │ Compliance:     100.0 × 0.20 = 20.0
  ├──────────────────────────────────┤
  │ FINAL AI READY SCORE: 86.3       │
  │ STATUS: EXCELLENT ✓              │
  └──────────────────────────────────┘

RECOMMENDATION:
  "Ready for production AI/RAG applications
   with excellent data quality and coverage"
```

---

## Where to Find the Score

### In APIs
1. **Fingerprint API**
   ```
   GET /api/v1/products/{id}/fingerprint
   → Returns: AI_Trust_Score, AI_Ready_Score
   ```

2. **Product Details**
   ```
   GET /api/v1/products/{id}
   → Returns: readiness_fingerprint, trust_score
   ```

3. **Quality Improvement**
   ```
   GET /api/v1/products/{id}/quality-improvement
   → Returns: overall_quality + drill-down metrics
   ```

### In Database
```sql
SELECT
  trust_score,           -- Overall trust (avg of chunks)
  readiness_fingerprint, -- JSON with AI ready score
  policy_status,         -- Policy compliance
  policy_violations      -- Violation details
FROM products
WHERE id = 'product-id';
```

### In UI
- Product Dashboard: Displays AI Ready Score badge
- Fingerprint Report: Detailed breakdown by component
- Quality Drill-Down: Individual chunk scores

---

## How to Improve Your Score

### Low Data Quality?
- Review chunks with confidence < 70
- Check for OCR extraction issues
- Verify source documents are clean

### Low Completeness?
- Address DQ violations (see details in API)
- Add missing required fields
- Ensure all sections are represented

### Low Consistency?
- Investigate "poor" quality chunks
- Adjust chunking strategy (sentence vs paragraph)
- Consider re-processing with different settings

### Low Coverage?
- Upload all required documents
- Ensure file format compatibility
- Check for upload errors

### Low Compliance?
- Review policy violations
- Adjust data to meet governance requirements
- Update policy thresholds if needed

---

## Technical Details

### Quality Score Calculation (Per Chunk)

```python
# Coherence: Semantic similarity of sentences
if sentence_similarity < 0.3:
    coherence = (similarity / 0.3) * 50
else:
    coherence = 50 + ((similarity - 0.3) / 0.7) * 50

# Noise: Artifact and junk detection
noise = min(
    special_chars * 400 +     # 0-40 points
    whitespace * 200 +        # 0-20 points
    non_ascii * 100 +         # 0-30 points
    long_words * 100,         # 0-10 points
    100                       # Cap at 100
)

# Overall Trust Score
trust = (confidence * 0.4) + (coherence * 0.3) + ((100 - noise) * 0.3)
```

### Fingerprint Generation

```python
# Aggregate chunk scores
avg_confidence = mean([c.confidence for c in chunks])
avg_coherence = mean([c.coherence for c in chunks])
avg_noise = mean([c.noise for c in chunks])

# Calculate AI Ready components
data_quality = (avg_confidence * 0.33) + (avg_coherence * 0.33) + ((100 - avg_noise) * 0.34)
completeness = ((1 - violation_ratio) * 0.7) + (chunk_coverage * 0.3)
consistency = quality_distribution_balance()
coverage = min((total_chunks / expected) * 100, 100)
compliance = 100 if policy_passed else (1 - violations/total) * 100

# Final Score
ai_ready = (data_quality * 0.25) + (completeness * 0.20) +
           (consistency * 0.20) + (coverage * 0.15) + (compliance * 0.20)
```

---

## Common Questions

**Q: What does each quality score mean?**
- **Confidence**: Trust in text extraction (OCR quality)
- **Coherence**: How well text flows logically
- **Noise**: Artifacts, special chars, encoding errors

**Q: Why is my score low?**
- Check individual chunk scores in quality drill-down
- Review policy violations
- Verify source document quality

**Q: How often is it recalculated?**
- When pipeline runs (after file upload/processing)
- Can be manual or scheduled
- Previous versions retained for comparison

**Q: Can I export the score?**
- Yes, via API responses
- Included in fingerprint.json artifact
- Available in audit logs for compliance

---

**For detailed implementation**: See `EXTRACTION_AND_AI_READY_SCORE_WORKFLOW.md`
