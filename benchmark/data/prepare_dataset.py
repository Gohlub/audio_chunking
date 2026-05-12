#!/usr/bin/env python3
"""
Prepare corpora (see ``datasets.__init__`` for ids).

  uv run --project . data/prepare_dataset.py list
  uv run --project . data/prepare_dataset.py all
  uv run --project . data/prepare_dataset.py ami
  uv run --project . data/prepare_dataset.py earnings22

``all`` runs every registered dataset in order with each script’s default arguments. For
per-dataset flags, run that id alone.
"""
from __future__ import annotations

import sys
from pathlib import Path

_scripts = Path(__file__).resolve().parent.parent
if str(_scripts) not in sys.path:
    sys.path.insert(0, str(_scripts))

from datasets import main_cli  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main_cli())
