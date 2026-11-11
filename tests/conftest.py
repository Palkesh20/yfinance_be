"""Shared pytest configuration.

Layer-specific fixtures are added alongside the modules they exercise.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ["APP_ENV"] = "test"
os.environ["SETTINGS_ENV_FILE"] = ""

FRONTEND = Path(__file__).resolve().parents[1] / "frontend"
if str(FRONTEND) not in sys.path:
    sys.path.insert(0, str(FRONTEND))
