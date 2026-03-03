"""
Isolated subprocess runner for Aakda chart code.
Never import or call this directly — spawned as a child process by sandbox.py.

Environment variables (all required):
    ACFV_CODE_FILE  : path to temp .py file containing chart code
    ACFV_OUT_FILE   : path where this script writes the JSON result
    ACFV_UTILS_PATH : path to app/utils/ (for graphutils.py)

Exit codes:
    0 — success, result JSON written to ACFV_OUT_FILE
    1 — failure, error message written to stderr
"""

import contextlib
import io
import json
import os
import sys

# ── Resolve env vars ──────────────────────────────────────────────────────────
code_file = os.environ.get("ACFV_CODE_FILE")
out_file = os.environ.get("ACFV_OUT_FILE")
utils_path = os.environ.get("ACFV_UTILS_PATH")

if not (code_file and out_file):
    sys.stderr.write("Missing required ACFV_* environment variables.\n")
    sys.exit(1)

# ── Import chart libraries ─────────────────────────────────────────────────────
try:
    import pandas as pd
    import yfinance as yf
    import plotly.express as px
    import plotly.graph_objects as go
    import numpy as np
    import json as _json
    from datetime import datetime, timedelta
    import datetime as _dt_module
except ImportError as e:
    sys.stderr.write(f"Library import failed: {e}\n")
    sys.exit(1)


# ── flatten_yf defined inline — no external import needed ─────────────────────
def flatten_yf(df):
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [col[0] for col in df.columns]
    return df


# ── Restricted builtins ───────────────────────────────────────────────────────
_SAFE_BUILTINS = {
    "range": range,
    "len": len,
    "min": min,
    "max": max,
    "sum": sum,
    "abs": abs,
    "round": round,
    "int": int,
    "float": float,
    "str": str,
    "bool": bool,
    "list": list,
    "dict": dict,
    "tuple": tuple,
    "set": set,
    "print": print,
    "True": True,
    "False": False,
    "None": None,
    "enumerate": enumerate,
    "zip": zip,
    "sorted": sorted,
    "any": any,
    "all": all,
    "map": map,
    "filter": filter,
    "reversed": reversed,
    "next": next,
    "iter": iter,
    "isinstance": isinstance,
    "type": type,
    "hasattr": hasattr,
    "getattr": getattr,
    "vars": vars,
    "Exception": Exception,
    "ValueError": ValueError,
    "KeyError": KeyError,
    "IndexError": IndexError,
    "TypeError": TypeError,
    "AttributeError": AttributeError,
    "RuntimeError": RuntimeError,
}

_SAFE_GLOBALS = {
    "__builtins__": _SAFE_BUILTINS,
    "pd": pd,
    "yf": yf,
    "px": px,
    "go": go,
    "np": np,
    "datetime": datetime,
    "timedelta": timedelta,
    "flatten_yf": flatten_yf,
    "json": _json,
    "datetime": _dt_module,
    "timedelta": _dt_module.timedelta,
}

# ── Read code ─────────────────────────────────────────────────────────────────
try:
    with open(code_file, "r", encoding="utf-8") as f:
        code = f.read()
except OSError as e:
    sys.stderr.write(f"Could not read code file: {e}\n")
    sys.exit(1)

# ── Execute ───────────────────────────────────────────────────────────────────
local_vars: dict = {}
stdout_buffer: io.StringIO = io.StringIO()

try:
    with contextlib.redirect_stdout(stdout_buffer):
        exec(compile(code, "<aakda_chart>", "exec"), _SAFE_GLOBALS, local_vars)
except Exception as e:
    sys.stderr.write(f"{type(e).__name__}: {e}\n")
    sys.exit(1)

captured = stdout_buffer.getvalue().strip()

# ── Validate output contract ──────────────────────────────────────────────────
plot_html = local_vars.get("plot_html")

if not plot_html:
    sys.stderr.write(
        "Code did not assign plot_html. "
        "Ensure the final block assigned all four required variables.\n"
    )
    sys.exit(1)

if "SUCCESS: plot ready" not in captured:
    sys.stderr.write(
        f"Code ran but did not print 'SUCCESS: plot ready'. "
        f"Captured stdout: {captured!r}\n"
    )
    sys.exit(1)

# ── Write result ──────────────────────────────────────────────────────────────
result = {
    "plot_html": plot_html,
    "data_html": local_vars.get("data_html") or "",
    "sources": local_vars.get("sources") or [],
}

try:
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(result, f)
except OSError as e:
    sys.stderr.write(f"Could not write output file: {e}\n")
    sys.exit(1)

sys.exit(0)
