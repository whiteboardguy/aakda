import ast
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Callable, Optional

from ..ai import SYSTEM_PROMPT, call_llm, make_tool_error
from ..print_utils import printStat

# ── CONFIG ────────────────────────────────────────────────────────────────────
MAX_RETRIES = 8
EXEC_TIMEOUT = 30  # per-subprocess seconds

# Paths
_RUNNER = str(Path(__file__).parent / "_runner.py")
_UTILS_PATH = str(Path(__file__).parent.parent)  # app/utils/

# Explicitly resolve the venv Python so the subprocess inherits all installed packages.
# sys.executable under `uv run` can point to the uv shim rather than the venv interpreter.
_VENV_PYTHON = Path(__file__).parents[3] / ".venv" / "bin" / "python"
_PYTHON = str(_VENV_PYTHON) if _VENV_PYTHON.exists() else sys.executable
printStat(
    "o",
    f"Sandbox python: {_PYTHON} (venv={'yes' if _VENV_PYTHON.exists() else 'NO — falling back to sys.executable'})",
)

# Env var prefixes to strip from the child process environment
_STRIP_PREFIXES = (
    "LLM_",
    "JINA_",
    "SECRET",
    "DB_",
    "DATABASE_",
    "REDIS_",
    "SECURITY_",
    "INSTANCE_",
)

# ── AST VALIDATION ────────────────────────────────────────────────────────────
_BLOCKED_CALLS = frozenset(
    {
        "exec",
        "eval",
        "open",
        "__import__",
        "compile",
        "breakpoint",
        "input",
        "memoryview",
    }
)


def validate_ast(code: str) -> Optional[str]:
    """
    Returns an error string if the code is unsafe, None if it passes.
    Runs before any subprocess is spawned.
    """
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return f"SyntaxError at line {e.lineno}: {e.msg}"

    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            return (
                "Import statements are forbidden — all required libraries "
                "are pre-injected as globals. Remove all import lines."
            )
        # This checks every functional call to see if its allowed or not
        if isinstance(node, ast.Call):
            func = node.func
            name: Optional[str] = None
            if isinstance(func, ast.Name):
                name = func.id
            elif isinstance(func, ast.Attribute):
                name = func.attr
            if name and name in _BLOCKED_CALLS:
                return f"Forbidden call: {name}() is not allowed in chart code."

    return None


# ── SUBPROCESS EXECUTION ──────────────────────────────────────────────────────
def _execute_subprocess(code: str, exec_timeout: int = EXEC_TIMEOUT) -> dict:
    """
    Result is read from a temp file (not stdout) to safely handle large HTML.
    """
    code_file = out_file = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".py",
            prefix="aakda_code_",
            encoding="utf-8",
            delete=False,
        ) as cf:
            os.chmod(cf.name, 0o600)
            cf.write(code)
            code_file = cf.name

        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".json",
            prefix="aakda_out_",
            encoding="utf-8",
            delete=False,
        ) as of:
            os.chmod(of.name, 0o600)
            out_file = of.name

        # Strip all sensitive vars, pass only what the runner needs
        child_env = {
            k: v
            for k, v in os.environ.items()
            if not any(k.startswith(p) for p in _STRIP_PREFIXES)
        }
        child_env["ACFV_CODE_FILE"] = code_file
        child_env["ACFV_OUT_FILE"] = out_file

        printStat("o", f"Sandbox exec: python={_PYTHON} timeout={exec_timeout}s")
        t0 = time.monotonic()
        proc = subprocess.run(
            [_PYTHON, _RUNNER],
            capture_output=True,
            text=True,
            timeout=exec_timeout,
            env=child_env,
        )
        elapsed = time.monotonic() - t0
        printStat(
            "o", f"Sandbox exit: returncode={proc.returncode} elapsed={elapsed:.1f}s"
        )

        if proc.returncode != 0:
            error = (
                proc.stderr.strip()
                or "Subprocess exited with a non-zero code. Something's wrong."
            )
            printStat("c", f"Sandbox subprocess stderr: {error}")
            return {"success": False, "error": error}

        with open(out_file, "r", encoding="utf-8") as f:
            result = json.load(f)

        if not result.get("plot_html"):
            return {
                "success": False,
                "error": "Output file exists but there's no 'plot_html'.",
            }

        return {
            "success": True,
            "plot_html": result["plot_html"],
            "data_html": result.get("data_html") or "",
            "sources": result.get("sources") or [],
        }

    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "error": f"Execution timed out after {exec_timeout}s.",
        }
    except json.JSONDecodeError:
        return {
            "success": False,
            "error": "Runner wrote invalid JSON to the output file.",
        }
    except Exception as e:
        return {"success": False, "error": f"Unexpected error: {e}"}
    finally:
        for path in (code_file, out_file):
            if path:
                try:
                    os.unlink(path)
                except OSError:
                    pass


# ── CONTEXT RECONSTRUCTION ────────────────────────────────────────────────────
def _reconstruct_messages(user_messages: list, bot_messages: list) -> list:
    """
    Reconstruct the interleaved LLM message array from the DB's
    user_messages and bot_messages lists, sorted by message_index.
    """
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    u_sorted = sorted(user_messages, key=lambda m: m["message_index"])
    b_sorted = sorted(bot_messages, key=lambda m: m["message_index"])
    b_by_idx = {m["message_index"]: m for m in b_sorted}

    for u in u_sorted:
        idx = u["message_index"]
        user_content = u["message"]

        if u.get("render_reply") and u.get("render_reply_index") is not None:
            ref = b_by_idx.get(u["render_reply_index"])
            if ref and ref.get("render_python"):
                user_content = (
                    f"[Context: the user is referring to the chart produced by this code:\n"
                    f"```python\n{ref['render_python']}\n```]\n\n" + user_content
                )

        messages.append({"role": "user", "content": user_content})

        bot = b_by_idx.get(idx)
        if not bot:
            continue

        tools_called: list = []
        raw_tc = bot.get("tools_called")
        if raw_tc:
            try:
                tools_called = json.loads(raw_tc) if isinstance(raw_tc, str) else raw_tc
            except json.JSONDecodeError, TypeError:
                tools_called = []

        if bot.get("is_render") and tools_called:
            tc_list = []
            for i, tc in enumerate(tools_called):
                name = tc.get("name", "")
                fake_id = f"rc_{idx}_{i}"

                if name == "execute_python_for_chart":
                    tc_list.append(
                        {
                            "id": fake_id,
                            "type": "function",
                            "function": {
                                "name": "execute_python_for_chart",
                                "arguments": json.dumps(
                                    {"code": bot.get("render_python", "")}
                                ),
                            },
                        }
                    )
                elif name == "search_web":
                    tc_list.append(
                        {
                            "id": fake_id,
                            "type": "function",
                            "function": {
                                "name": "search_web",
                                "arguments": json.dumps(
                                    {"query": tc.get("summary", "")}
                                ),
                            },
                        }
                    )

            if tc_list:
                messages.append(
                    {
                        "role": "assistant",
                        "content": bot.get("message") or "",
                        "tool_calls": tc_list,
                    }
                )
                for tc_msg, tc_orig in zip(tc_list, tools_called):
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc_msg["id"],
                            "content": tc_orig.get("response") or "SUCCESS",
                        }
                    )
                continue

        messages.append({"role": "assistant", "content": bot.get("message") or ""})

    return messages


# ── HELPERS ───────────────────────────────────────────────────────────────────
def _error_dict(message: str, model: str, retries: int = 0) -> dict:
    return {
        "render_plot_html": None,
        "render_html_data": None,
        "render_python": None,
        "message": message,
        "model": model,
        "sources": [],
        "message_retries": retries,
        "tools_called": [],
        "is_render": False,
    }


def _clean_error(error: str) -> str:
    if "__import__" in error or "is not allowed" in error:
        return "Import statement detected — remove all import lines. All required libraries (pd, yf, px, go, np, datetime, json) are pre-injected as globals."
    if "429" in error or "Too Many Requests" in error:
        return "The data provider rate-limited this request. Use a shorter date range or fetch less data."
    if "KeyError" in error and "Close" in error:
        return "Column 'Close' not found after download. Ensure you called flatten_yf(df) immediately after yf.download()."
    return error


def _retry_guidance(attempt: int, error: str) -> str:
    """
    Returns progressively more directive error messages as retries increase.
    Attempt is 1-indexed from the caller's perspective.
    """
    cleaned = _clean_error(error)

    if attempt == 1:
        return (
            f"Attempt 1 failed: {cleaned}\n"
            f"Read the error carefully and fix the exact line causing it."
        )
    elif attempt == 2:
        return (
            f"Attempt 2 failed: {cleaned}\n"
            f"Your previous fix did not work. Try a different approach entirely — "
            f"simplify the date range, use fewer traces, or switch to a different data source for the same asset."
        )
    elif attempt == 3:
        return (
            f"Attempt 3 failed: {cleaned}\n"
            f"Significantly restructure your code. If you were using yf.download(), try a minimal version: "
            f"one ticker, explicit start/end strings, auto_adjust=True, and flatten_yf immediately after. "
            f"If you were using FRED, double-check the series ID and column name."
        )
    else:
        return (
            f"Attempt {attempt} failed: {cleaned}\n"
            f"The current approach is not working at all. Write the simplest possible version of this chart — "
            f"one ticker, one trace, no extra calculations, no volume bars, just Close price over time. "
            f"Strip everything back to basics."
        )


# ── PUBLIC API ────────────────────────────────────────────────────────────────
def fetch_graph(
    query: str,
    user_messages: list,
    bot_messages: list,
    opt_web: bool = False,
    model: str = "gpt-oss-120b",
    timeout: int = 300,
    on_status: Optional[Callable] = None,
) -> dict:
    def push(text: str):
        if on_status:
            on_status(text)

    deadline = time.monotonic() + timeout
    retries = 0
    last_error = ""
    llm_result: Optional[dict] = None

    printStat(
        "o",
        f"fetch_graph: query={query[:80]!r} model={model} opt_web={opt_web} timeout={timeout}s",
    )
    base_messages = _reconstruct_messages(user_messages, bot_messages)
    base_messages.append({"role": "user", "content": query})

    for attempt in range(MAX_RETRIES + 1):
        if time.monotonic() > deadline:
            return _error_dict("Total timeout exceeded.", model, retries)

        # ── LLM call ──────────────────────────────────────────────────────
        if llm_result is None:
            llm_result = call_llm(
                base_messages,
                opt_web=opt_web,
                model=model,
                on_status=on_status,
            )
        else:
            working_msgs = llm_result["_working_msgs"]
            working_msgs.append(
                make_tool_error(
                    llm_result["_tc_id"],
                    _retry_guidance(retries, last_error),
                )
            )
            llm_result = call_llm(
                working_msgs,
                opt_web=opt_web,
                model=model,
                on_status=on_status,
            )

        # ── Plain text reply — no chart ────────────────────────────────────
        if llm_result.get("code") is None:
            # If the LLM already used tools (searched the web) and still returned
            # plain text, it genuinely looked and found nothing chartable — accept
            # the answer immediately. Only retry if it gave up without trying at all.
            already_searched = bool(llm_result.get("tools_called"))
            if not already_searched and retries < MAX_RETRIES:
                push(
                    f"No tool call (attempt {retries + 1}) — prompting LLM to call the tool…"
                )
                last_error = "no_tool_call"
                retries += 1
                # _tc_id is None so we can't use make_tool_error — append a
                # user-role correction instead and reset llm_result to force
                # a fresh call_llm on the next iteration.
                working_msgs = llm_result["_working_msgs"]
                working_msgs.append(
                    {
                        "role": "user",
                        "content": (
                            "You must call execute_python_for_chart immediately. "
                            "Do not respond with plain text. Call the tool now."
                        ),
                    }
                )
                llm_result = call_llm(
                    working_msgs,
                    opt_web=opt_web,
                    model=model,
                    on_status=on_status,
                )
                continue
            return {
                "render_plot_html": None,
                "render_html_data": None,
                "render_python": None,
                "message": llm_result["message"],
                "model": model,
                "sources": [],
                "message_retries": retries,
                "tools_called": llm_result["tools_called"],
                "is_render": False,
            }

        code = llm_result["code"]

        # ── AST validation ────────────────────────────────────────────────
        push(f"Validating code (attempt {retries + 1})…")
        ast_error = validate_ast(code)
        if ast_error:
            push(f"Validation failed (attempt {retries + 1}) — asking LLM to fix…")
            printStat("w", f"fetch_graph attempt={retries + 1} AST error: {ast_error}")
            printStat("w", f"Rejected code ({len(code)} chars):\n{code[:800]}")
            last_error = ast_error
            retries += 1
            continue

        # ── Subprocess execution ──────────────────────────────────────────
        exec_secs = min(EXEC_TIMEOUT, int(deadline - time.monotonic()))
        if exec_secs <= 0:
            return _error_dict("Total timeout exceeded.", model, retries)

        push(f"Executing sandbox (attempt {retries + 1})…")
        printStat(
            "o",
            f"fetch_graph attempt={retries + 1} running code ({len(code)} chars):\n{code[:800]}",
        )
        exec_result = _execute_subprocess(code, exec_timeout=exec_secs)

        if exec_result["success"]:
            push("Rendering chart…")
            printStat("o", f"fetch_graph success on attempt={retries + 1}")
            return {
                "render_plot_html": exec_result["plot_html"],
                "render_html_data": exec_result.get("data_html") or "",
                "render_python": code,
                "message": llm_result["message"],
                "model": model,
                "sources": exec_result.get("sources") or [],
                "message_retries": retries,
                "tools_called": llm_result["tools_called"],
                "is_render": True,
            }

        printStat(
            "w",
            f"fetch_graph attempt={retries + 1} sandbox error: {exec_result['error']}",
        )
        push(f"Sandbox error on attempt {retries + 1} — asking LLM to fix…")
        last_error = exec_result["error"]
        retries += 1

    printStat(
        "c",
        f"fetch_graph failed after {MAX_RETRIES} attempts. Last error: {last_error}",
    )
    return _error_dict(
        f"Failed after {MAX_RETRIES} attempts. Last error: {last_error}",
        model,
        retries,
    )
