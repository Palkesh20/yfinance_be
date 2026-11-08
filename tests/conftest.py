"""Shared pytest configuration.

Layer-specific fixtures are added alongside the modules they exercise.
"""

from __future__ import annotations

import os

os.environ["APP_ENV"] = "test"
os.environ["SETTINGS_ENV_FILE"] = ""
