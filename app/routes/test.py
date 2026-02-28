import asyncio
import json
from fastapi import APIRouter
from fastapi.responses import JSONResponse, StreamingResponse, HTMLResponse

from ..utils.sandbox.sandbox import fetch_graph
from ..cfg import settings

router = APIRouter()


@router.get("/test/get-graph")
async def get_graph(
    query:   str,
    opt_web: bool = False,
    model:   str  = f"{settings.llm_model_id}",
):
    user_messages: list = []
    bot_messages:  list = []

    result = await asyncio.to_thread(
        fetch_graph,
        query         = query,
        user_messages = user_messages,
        bot_messages  = bot_messages,
        opt_web       = opt_web,
        model         = model,
        timeout       = 300,
        on_status     = lambda msg: print(f"[STATUS] {msg}"),
    )
    return JSONResponse({
        "is_render":        result["is_render"],
        "message":          result["message"],
        "model":            result["model"],
        "message_retries":  result["message_retries"],
        "tools_called":     result["tools_called"],
        "sources":          result["sources"],
        "render_python":    result["render_python"],
        "render_plot_html": result["render_plot_html"],
        "render_html_data": f"[{len(result['render_html_data'] or '')} chars]",
    })
