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

        # bool
        "is_render":        result["is_render"],

        # str
        "message":          result["message"],

        # str
        "model":            result["model"],

        # int
        "message_retries":  result["message_retries"],

        # List
        "tools_called":     result["tools_called"],

        # List[Dict]
        "sources":          result["sources"],

        # str
        "render_python":    result["render_python"],

        # str
        "render_plot_html": result["render_plot_html"],

        # str
        "render_html_data": result['render_html_data'],
    })
