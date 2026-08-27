#!/usr/bin/env python3
"""Compatibility facade forwarding manage.py invocations to main.py / src.cli."""
from __future__ import annotations

import sys
from pathlib import Path

_projects_dir = str(Path(__file__).resolve().parent.parent)
if _projects_dir not in sys.path:
    sys.path.insert(0, _projects_dir)

from main import _preparse_profile, main

if __name__ == "__main__":
    _preparse_profile(sys.argv)
    sys.exit(main())
