"""Utility to load ML model and feature config in a thread-safe, cached way."""
from typing import Optional
import json
import threading
from pathlib import Path

import joblib

_model = None
_model_lock = threading.Lock()
_feature_config = None


def load_model(path: str):
    global _model
    if _model is None:
        with _model_lock:
            if _model is None:
                _model = joblib.load(path)
    return _model


def load_feature_config(path: str) -> Optional[dict]:
    global _feature_config
    if _feature_config is None:
        p = Path(path)
        if p.exists():
            with p.open("r", encoding="utf-8") as fh:
                _feature_config = json.load(fh)
    return _feature_config
