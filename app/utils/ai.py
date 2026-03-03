import json
import os
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Callable, Optional

import httpx

from ..cfg import settings
from .print_utils import printStat

BASE_URL = settings.llm_base_url
API_KEY = settings.llm_api_key
JINA_API_KEY = settings.tools_jina_api
MAX_ITERATIONS = settings.tools_iteration_count

_client = httpx.Client(timeout=120.0)

# Load system prompt once at import time — fails loudly if the file is missing
SYSTEM_PROMPT: str = (Path(__file__).parent / "prompts" / "system.md").read_text(
    encoding="utf-8"
)


# ── TOOL SCHEMAS ──────────────────────────────────────────────────────────────
CHART_TOOL = {
    "type": "function",
    "function": {
        "name": "execute_python_for_chart",
        "description": (
            "Write and execute Python code to fetch real historical data and produce ONE Plotly figure. "
            "Pre-injected globals — NEVER use import statements: "
            "pd, yf, px, go, np, datetime, timedelta, flatten_yf. "
            "For stocks/ETFs/crypto/commodities: use yf.download() then IMMEDIATELY call flatten_yf(df). "
            "For FRED macro data: use pd.read_csv('https://fred.stlouisfed.org/graph/fredgraph.csv?id=SERIES_ID', "
            "parse_dates=['DATE'], index_col='DATE'). "
            "Code MUST end with all four: plot_html, data_html, sources, print('SUCCESS: plot ready')."
        ),
        "parameters": {
            "type": "object",
            "properties": {"code": {"type": "string"}},
            "required": ["code"],
        },
    },
}

SEARCH_TOOL = {
    "type": "function",
    "function": {
        "name": "search_web",
        "description": (
            "Search the web for current information, recent news, market events, analyst opinions, "
            "or any factual context needed before charting. "
            "Use this when the query involves recent news, company announcements, economic events, "
            "or any context not available in yfinance or FRED. "
            "After searching you MUST still call execute_python_for_chart — never stop after a search."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Specific search query including company names, dates, and relevant context.",
                }
            },
            "required": ["query"],
        },
    },
}


# ── JINA SEARCH ───────────────────────────────────────────────────────────────
def _jina_search(query: str) -> str:
    if not JINA_API_KEY:
        return "Web search unavailable — JINA_API_KEY is not configured."
    try:
        encoded = urllib.parse.quote_plus(query)
        req = urllib.request.Request(
            f"https://s.jina.ai/{encoded}",
            headers={
                "Authorization": f"Bearer {JINA_API_KEY}",
                "Accept": "application/json",
                "X-Budget-Tokens": "1500",
                "X-With-Generated-Alt": "true",
            },
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())

        results = data.get("data", [])
        if not results:
            return f"No results found for: {query}"

        lines = [f"Web search results for «{query}»:\n"]
        for i, r in enumerate(results[:5], 1):
            title = r.get("title", "No title")
            link = r.get("url", "")
            desc = (r.get("description") or r.get("content", ""))[:400]
            lines.append(f"[{i}] {title}\n    URL: {link}\n    {desc}\n")
        return "\n".join(lines)

    except Exception as e:
        return f"Web search failed: {e}"


# ── RAW HTTP CALL ─────────────────────────────────────────────────────────────
def _raw_call(messages: list, tools: list, model: str) -> dict:
    t0 = time.monotonic()
    try:
        resp = _client.post(
            f"{BASE_URL}/chat/completions",
            headers={
                "Authorization": f"Bearer {API_KEY}",
                "Content-Type": "application/json",
            },
            content=json.dumps(
                {
                    "model": model,
                    "messages": messages,
                    "tools": tools,
                    "tool_choice": "auto",
                    "temperature": 0.0,
                    "max_tokens": 4096,
                }
            ),
        )
    except Exception as e:
        printStat("c", f"LLM HTTP transport error: {type(e).__name__}: {e}")
        raise
    if resp.status_code != 200:
        printStat("c", f"LLM error body: {resp.text[:1000]}")
    resp.raise_for_status()
    data = resp.json()
    return data


# ── PUBLIC HELPERS ────────────────────────────────────────────────────────────
def make_tool_error(tc_id: str, error: str) -> dict:
    """
    Build a tool-result message that feeds a sandbox error back to the LLM.
    Append this to _working_msgs before retrying call_llm.
    """
    return {
        "role": "tool",
        "tool_call_id": tc_id,
        "content": json.dumps({"success": False, "error": error}),
    }


# ── MAIN PUBLIC API ───────────────────────────────────────────────────────────
def call_llm(
    messages: list,
    opt_web: bool = False,
    model: str = "gpt-oss-120b",
    on_status: Optional[Callable] = None,
) -> dict:
    """
    Run one full LLM agent pass. Handles web search internally.
    Returns when the model produces chart code or a plain-text reply.

    Return dict keys:
        code          str | None   — Python code to execute; None for plain-text replies
        message       str          — model's text content
        tools_called  list         — [{name, summary, response}] for DB storage
        _tc_id        str          — tool_call id of the code call (internal, for error feedback)
        _working_msgs list         — accumulated message list (internal, for error feedback)
    """

    def push(text: str):
        if on_status:
            on_status(text)

    tools = [CHART_TOOL, SEARCH_TOOL] if opt_web else [CHART_TOOL]
    working_msgs = list(messages)  # local copy — never mutate caller's list
    tools_called: list = []

    for iteration in range(MAX_ITERATIONS):
        push(f"Calling LLM (pass {iteration + 1} of {MAX_ITERATIONS})…")

        try:
            raw = _raw_call(working_msgs, tools, model)
        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            if status in (401, 403):
                printStat(
                    "c",
                    f"LLM auth failed (HTTP {status}) — check LLM_API_KEY and LLM_BASE_URL",
                )
                raise RuntimeError(f"LLM authentication failed (HTTP {status}).") from e
            printStat("c", f"LLM HTTP {status} error on iteration {iteration + 1}")
            raise

        choice = raw["choices"][0]
        msg = choice["message"]
        text = msg.get("content") or ""
        tcs = msg.get("tool_calls") or []

        # Only append the assistant message if it has content or tool_calls.
        # An empty assistant message (finish_reason=stop, no content, no tool_calls)
        # causes a 400 "assistant message must include content or tool_calls" on the
        # next request. Skip it entirely — there's nothing useful to preserve.
        if text or tcs:
            working_msgs.append(msg)

        # ── No tool call → plain text final reply ─────────────────────────
        if not tcs:
            push("Done.")
            return {
                "code": None,
                "message": text,
                "tools_called": tools_called,
                "_tc_id": None,
                "_working_msgs": working_msgs,
            }

        for tc in tcs:
            fn_name = tc["function"]["name"]
            try:
                args = json.loads(tc["function"]["arguments"])
            except json.JSONDecodeError, KeyError:
                args = {}

            # ── Search branch ──────────────────────────────────────────────
            if fn_name == "search_web":
                query = args.get("query", "").strip()
                push(f"Searching the web: {query[:70]}…")
                result = _jina_search(query)
                tools_called.append(
                    {
                        "name": "search_web",
                        "summary": query,
                        "response": result[:600],  # truncated for DB storage only
                    }
                )
                working_msgs.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": result,  # full result goes to the LLM
                    }
                )

            # ── Chart code branch ──────────────────────────────────────────
            elif fn_name == "execute_python_for_chart":
                code = args.get("code", "").strip()

                if not code:
                    # Feed empty-code error back and continue the loop
                    working_msgs.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc["id"],
                            "content": json.dumps(
                                {
                                    "success": False,
                                    "error": "Empty code block returned. Write the full Python code.",
                                }
                            ),
                        }
                    )
                    continue

                push("Code received — handing off to sandbox…")
                return {
                    "code": code,
                    "message": text or "Here's your interactive chart:",
                    "tools_called": tools_called,
                    "_tc_id": tc["id"],
                    "_working_msgs": working_msgs,
                }

    # Exhausted all iterations without producing code
    return {
        "code": None,
        "message": f"Could not produce chart code after {MAX_ITERATIONS} LLM passes.",
        "tools_called": tools_called,
        "_tc_id": None,
        "_working_msgs": working_msgs,
    }
