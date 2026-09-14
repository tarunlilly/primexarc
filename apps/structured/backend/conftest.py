"""Pytest bootstrap + shared fixtures.

1. Adds `backend/` to sys.path so `from core.X import Y` resolves.
2. Provides synthetic CSV bytes fixtures so tests are 100% self-contained:
   no file I/O, no fragile paths, no orphan files in the repo.

Production users always supply their own CSVs at upload time. These fixtures
exist ONLY for the test suite.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# ── sys.path bootstrap ─────────────────────────────────────────────────────
ROOT = Path(__file__).parent.resolve()
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# ── Auth bypass for all API tests ─────────────────────────────────────────
@pytest.fixture(autouse=True)
def override_require_user():
    """Install a no-op require_user override so tests don't need real JWTs.

    Applies to every test in the suite via autouse=True. Resets after each
    test so the override doesn't bleed between tests.
    """
    from dependencies import CurrentUser, require_user
    from main import app

    async def _stub() -> CurrentUser:
        return CurrentUser(user_id="test_user", email="test@lilly.com", roles=["data_owner"])

    app.dependency_overrides[require_user] = _stub
    yield
    app.dependency_overrides.pop(require_user, None)


# ── Shared fixtures ────────────────────────────────────────────────────────

@pytest.fixture
def taltz_bytes() -> bytes:
    """A 60-row synthetic CSV with 6 categorical columns.

    Shape matches the historical 'taltz_trust_segmentation' dataset:
        TRUST_ID, TRUST_NAME, PRIORITY, FORMULARY_POSITION, POSITION, INDICATION
    All-categorical, no datetimes, no numerics — deliberately triggers many
    rules (Temporal Integrity, Labels, Schema audit) so a single fixture
    exercises broad regression coverage.

    Returned as bytes — same shape as a real `await UploadFile.read()`.
    """
    return _SYNTHETIC_TALTZ_BYTES


@pytest.fixture
def healthy_bytes() -> bytes:
    """A small CSV that scores well across most dimensions: has a PK, audit
    columns, a target column, datetimes, numeric features."""
    return _SYNTHETIC_HEALTHY_BYTES


# ── Synthetic data (module-level so it builds once per test session) ───────

_TALTZ_HEADER = "TRUST_ID,TRUST_NAME,PRIORITY,FORMULARY_POSITION,POSITION,INDICATION"

# Generated rows: stable, deterministic content
_TALTZ_ROWS = [
    "T001,Alpha Health Network,high,Tier 1,A,Cardiology",
    "T002,Beta Medical Group,medium,Tier 2,B,Oncology",
    "T003,Gamma Care Systems,low,Tier 3,C,Neurology",
    "T004,Delta Health Partners,high,Tier 1,A,Cardiology",
    "T005,Epsilon Medical,medium,Tier 2,B,Endocrinology",
    "T006,Zeta Healthcare,low,Non-formulary,C,Rheumatology",
    "T007,Eta Health Services,high,Tier 1,A,Oncology",
    "T008,Theta Medical Center,medium,Tier 2,B,Cardiology",
    "T009,Iota Care Network,low,Tier 3,C,Neurology",
    "T010,Kappa Health System,high,Tier 1,A,Endocrinology",
    "T011,Lambda Medical,medium,Tier 2,B,Rheumatology",
    "T012,Mu Healthcare Group,low,Non-formulary,C,Cardiology",
    "T013,Nu Health Partners,high,Tier 1,A,Oncology",
    "T014,Xi Medical Center,medium,Tier 2,B,Neurology",
    "T015,Omicron Care,low,Tier 3,C,Endocrinology",
    "T016,Pi Health Systems,high,Tier 1,A,Rheumatology",
    "T017,Rho Medical Group,medium,Tier 2,B,Cardiology",
    "T018,Sigma Healthcare,low,Tier 3,C,Oncology",
    "T019,Tau Health Network,high,Tier 1,A,Neurology",
    "T020,Upsilon Medical,medium,Tier 2,B,Endocrinology",
    "T021,Phi Care Systems,low,Non-formulary,C,Rheumatology",
    "T022,Chi Health Partners,high,Tier 1,A,Cardiology",
    "T023,Psi Medical Center,medium,Tier 2,B,Oncology",
    "T024,Omega Healthcare,low,Tier 3,C,Neurology",
    "T025,Northeast Health,high,Tier 1,A,Endocrinology",
    "T026,Southeast Medical,medium,Tier 2,B,Rheumatology",
    "T027,Midwest Care,low,Tier 3,C,Cardiology",
    "T028,Southwest Health,high,Tier 1,A,Oncology",
    "T029,West Coast Medical,medium,Tier 2,B,Neurology",
    "T030,Mountain View Health,low,,C,Endocrinology",
    "T031,Lakeshore Medical,high,Tier 1,A,Rheumatology",
    "T032,Riverside Health,medium,Tier 2,B,Cardiology",
    "T033,Hillcrest Care,low,Tier 3,C,Oncology",
    "T034,Bayside Medical,high,Tier 1,A,",
    "T035,Parkview Health,medium,Tier 2,B,Endocrinology",
    "T036,Greenfield Medical,low,Non-formulary,C,Rheumatology",
    "T037,Riverbend Health,high,Tier 1,A,Cardiology",
    "T038,Springfield Care,medium,Tier 2,B,",
    "T039,Fairview Medical,low,Tier 3,C,Neurology",
    "T040,Lakeside Health,high,Tier 1,A,Endocrinology",
    "T041,Oakridge Medical,medium,Tier 2,B,Rheumatology",
    "T042,Pinehurst Health,low,Tier 3,C,Cardiology",
    "T043,Cedar Valley Care,high,Tier 1,A,Oncology",
    "T044,Maple Grove Medical,medium,Tier 2,B,",
    "T045,Birchwood Health,low,Non-formulary,C,Endocrinology",
    "T046,Willow Creek Medical,high,Tier 1,A,Rheumatology",
    "T047,Aspen Health,medium,Tier 2,B,Cardiology",
    "T048,Redwood Medical,low,Tier 3,C,Oncology",
    "T049,Cypress Health Network,high,Tier 1,A,Neurology",
    "T050,Juniper Medical,medium,Tier 2,B,Endocrinology",
    "T051,Sequoia Care,low,Tier 3,C,Rheumatology",
    "T052,Magnolia Health,high,Tier 1,A,Cardiology",
    "T053,Dogwood Medical,medium,,B,Oncology",
    "T054,Hickory Health,low,Tier 3,C,Neurology",
    "T055,Walnut Medical Group,high,Tier 1,A,Endocrinology",
    "T056,Sycamore Care,medium,Tier 2,B,Rheumatology",
    "T057,Elm Health Partners,low,Non-formulary,C,Cardiology",
    "T058,Poplar Medical,high,Tier 1,A,Oncology",
    "T059,Birch Health Systems,medium,Tier 2,B,Neurology",
    "T060,Pine Valley Care,low,Tier 3,C,Endocrinology",
]

_SYNTHETIC_TALTZ_BYTES = ("\n".join([_TALTZ_HEADER] + _TALTZ_ROWS) + "\n").encode("utf-8")


_HEALTHY_HEADER = "patient_id,enrolled_at,updated_at,age,bmi,site,target"

# 30 rows, has datetime + numeric + named target → should score in green tier
_HEALTHY_ROWS = [
    f"P{i:04d},2024-{((i%12)+1):02d}-{((i%27)+1):02d},2024-{((i%12)+1):02d}-{((i%27)+1):02d},"
    f"{30 + (i % 50)},{18.0 + (i % 15)},Site_{(i%5)+1},{i%2}"
    for i in range(30)
]
_SYNTHETIC_HEALTHY_BYTES = (
    "\n".join([_HEALTHY_HEADER] + _HEALTHY_ROWS) + "\n"
).encode("utf-8")