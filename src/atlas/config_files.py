"""Loaders for the YAML knob files under `config/`.

`scoring.yaml` is the experiment-knob file (SCORING.md): weights, admission bands,
stopping thresholds, mode budgets. Never hardcode these — the ablation study zeroes
them from here.
"""

from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

_SCORING = Path("config/scoring.yaml")
_MODELS = Path("config/models.yaml")


@lru_cache
def scoring() -> dict[str, Any]:
    return dict(yaml.safe_load(_SCORING.read_text(encoding="utf-8")))


@lru_cache
def mode_budget(mode: str) -> dict[str, Any]:
    modes = scoring().get("modes", {})
    if mode not in modes:
        raise ValueError(f"unknown mode {mode!r}; have {sorted(modes)}")
    return dict(modes[mode])


def config_hash(mode: str) -> str:
    """Stable hash of the config that governs a run (R9 reproducibility)."""
    blob = json.dumps(
        {"scoring": scoring(), "models": yaml.safe_load(_MODELS.read_text(encoding="utf-8")),
         "mode": mode},
        sort_keys=True,
    )
    return hashlib.sha256(blob.encode()).hexdigest()[:16]
