import asyncio

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from ..utils.jobs import get_job, remove_job

router = APIRouter(prefix="/chat")


@router.get("/events/{job_id}")
async def chat_events(job_id: str):
    """
    Server-Sent Events stream for a background AI job.

    Emits three event types:
      - status : forwarded to #status-bar-text (innerHTML)
      - done   : rendered message_group.html (replaces #sse-listener outerHTML)
      - error  : rendered error_bubble.html  (replaces #sse-listener outerHTML)

    The job queue is owned by this generator: remove_job is called here after
    the terminal event is consumed, not inside the background task.
    """

    async def event_generator():
        queue = get_job(job_id)
        if queue is None:
            # Job already finished or never existed — emit an error and close.
            yield "event: error\ndata: <div class='alert alert-error'>Job not found or already completed.</div>\n\n"
            return

        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=310.0)
                except asyncio.TimeoutError:
                    timeout_html = "<div class='alert alert-error'>Request timed out. Please try again.</div>"
                    yield f"event: error\ndata: {timeout_html}\n\n"
                    remove_job(job_id)
                    return

                event_type = event["type"]
                # Collapse to a single line — htmx SSE extension joins multi-data: lines
                # with newlines which can cause parse issues in the DOM.
                safe_data = event["data"].replace("\n", " ")
                yield f"event: {event_type}\ndata: {safe_data}\n\n"

                if event_type in ("done", "error"):
                    remove_job(job_id)
                    return

        except asyncio.CancelledError:
            # Client disconnected — clean up and exit silently.
            remove_job(job_id)
            return

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
