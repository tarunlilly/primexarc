# Testing Strategy

What we test, where the tests live, and what counts as enough coverage.

---

## Backend — pytest

`pytest` is the only framework. No `unittest`. Tests live in
`app/backend/tests/`, mirroring source structure:

```
tests/
├── test_scorer.py     # core/scorer.py
├── test_parser.py     # core/parser.py
├── test_dimensions.py # core/dimensions.py rules
├── test_advisor.py    # llm/advisor.py (mocked LLM)
└── test_api.py        # api/* via FastAPI TestClient
```

### Coverage targets

- Every public method in `core/` has at least one unit test.
- Every FastAPI route has a happy-path test + a validation-failure test.
- LLM advisor has one test for the success path (mocked client) and one for
  the fallback path (empty `LLM_API_KEY`).

### Critical determinism test

The scoring engine **must** produce identical output for identical input.
This is asserted explicitly:

```python
def test_scorer_is_deterministic():
    req = load_fixture("taltz_trust_segmentation.csv")
    results = [engine.score(req) for _ in range(20)]
    assert all(r == results[0] for r in results)
```

Place this in `test_scorer.py` and never delete it. If the test starts
failing, you've introduced non-determinism (random seeds, dict ordering,
set iteration order). Find and remove it before merging.

### Fixtures

- `taltz_trust_segmentation.csv` — 6 columns, 671 rows, all categorical.
  Reliably produces a red/Needs Improvement tier. The canonical fixture.

### Mocking

No test connects to a real database or a real LLM. Use `pytest-mock`:

```python
def test_advisor_falls_back_on_empty_key(mocker):
    mocker.patch("llm.advisor.settings.llm_api_key", "")
    advisor = LLMAdvisor()
    out = advisor.recommend(dim_result)
    assert len(out) >= 1
    assert all(isinstance(s, str) for s in out)
```

### Minimum assertions per scorer test

- Score is an integer between 0 and 100.
- Tier is consistent with the documented thresholds (`≥65` green, `40–64`
  yellow, `<40` red).
- Number of checks equals `len(dimension.rules)`.

---

## Frontend — Playwright

Smoke tests against the dev server. Goal: prove the UI doesn't crash and
critical flows render. We don't unit-test components.

```
frontend/e2e/
├── home.spec.ts        # landing renders, CTA navigates
├── wizard.spec.ts      # 4 steps advance, back navigation works
├── dashboard.spec.ts   # mock dashboard renders tier + breakdown
├── support.spec.ts     # form submits, status message appears
└── navigation.spec.ts  # header nav highlights active route
```

Run:

```bash
cd app/frontend
npm run test:e2e
```

### What we don't test on the frontend

- Scoring logic — there is none in the frontend.
- Tier calculation — there is none in the frontend.
- API integration shapes — covered by backend tests.

The frontend's job is to render the API response. As long as
`api.assessCsv()` returns a well-typed `AssessmentResult`, the dashboard will
display it correctly.

---

## Continuous integration

Future: GitHub Actions workflow runs `pytest tests/ -v` then
`npm run test:e2e` against a built preview. Until that lands, run both
locally before any merge.

---

## When you add a new feature

1. Write the test alongside the code (not after).
2. If you're touching `scorer.py`, add a determinism check on the new code path.
3. If you're touching `parser.py`, assert that no row data leaves the function
   (mock downstream consumers and assert they receive `ColumnProfile` only).
4. If you're touching `advisor.py`, assert the fallback still works.
