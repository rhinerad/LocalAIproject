"""Default policy/rubric paths for receipt-gated still QA."""
from __future__ import annotations

from pathlib import Path

HERE = Path(__file__).resolve().parent
PROVISIONAL_POLICY = HERE / "profiles" / "provisional_loop_labels_v1.json"
C017_END_RUBRIC = HERE / "profiles" / "br24_c017_end_rubric.json"
C017_START_RUBRIC = HERE / "profiles" / "br24_c017_rubric.json"
