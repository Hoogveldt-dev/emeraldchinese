"""Shim: the catalog helpers of the upstream port (tools/localize_portuguese.py).

The Chinese tools reuse its catalog format, text hashes and charset checks.
The module is loaded from the emerald-3ds checkout the build made
(build/emerald-3ds, or $WOOFER_PORT).
"""
import importlib.util
import os
import sys
from pathlib import Path

_port = Path(os.environ.get("WOOFER_PORT", Path(__file__).resolve().parents[1] / "build" / "emerald-3ds"))
_path = _port / "tools" / "localize_portuguese.py"
if not _path.exists():
    raise SystemExit("lp: %s not found, run scripts/build.sh first (or set WOOFER_PORT)" % _path)
_spec = importlib.util.spec_from_file_location("localize_portuguese", _path)
_mod = importlib.util.module_from_spec(_spec)
sys.modules["localize_portuguese"] = _mod
_spec.loader.exec_module(_mod)
globals().update({k: v for k, v in vars(_mod).items() if not k.startswith("__")})
