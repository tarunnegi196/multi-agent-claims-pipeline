"""
API routes beyond the core claim submission.

  POST /api/files                   Upload a document file; returns file_id + file_path.
  GET  /api/claims/{id}/trace       SSE — live events while claim processes (subscribe before POST).
  GET  /api/claims/{id}/trace/replay SSE — replay stored trace events with pacing for the demo.
"""
import asyncio
import json
import uuid
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import Response, StreamingResponse

from app.config import settings
from app.db.bus import event_bus
from app.db.repositories import TraceRepository

router = APIRouter()

# Ensure upload directory exists at startup
Path(settings.upload_dir).mkdir(parents=True, exist_ok=True)

_ALLOWED_MIME = {
    "image/jpeg", "image/jpg", "image/png", "image/webp",
    "application/pdf",
}
_SUFFIX_MAP = {
    "image/jpeg": ".jpg", "image/jpg": ".jpg",
    "image/png": ".png", "image/webp": ".webp",
    "application/pdf": ".pdf",
}


# ── File upload ───────────────────────────────────────────────────────────────

@router.post("/api/files")
async def upload_file(file: UploadFile = File(...)) -> dict:
    """
    Upload a single document file.
    Returns {file_id, file_name, file_path, content_type} for use in
    the documents[] array of POST /api/claims.
    """
    content_type = file.content_type or "image/jpeg"
    if content_type not in _ALLOWED_MIME:
        raise HTTPException(
            status_code=415,
            detail=(
                f"Unsupported file type '{content_type}'. "
                f"Allowed: {', '.join(sorted(_ALLOWED_MIME))}"
            ),
        )

    file_id = str(uuid.uuid4())
    suffix = _SUFFIX_MAP.get(content_type, ".bin")
    file_path = Path(settings.upload_dir) / f"{file_id}{suffix}"

    content = await file.read()
    file_path.write_bytes(content)

    return {
        "file_id": file_id,
        "file_name": file.filename or f"{file_id}{suffix}",
        "file_path": str(file_path),
        "content_type": content_type,
        "size_bytes": len(content),
    }


_MIME_BY_SUFFIX = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".png": "image/png",  ".webp": "image/webp",
    ".pdf": "application/pdf",
}


# ── File serving ──────────────────────────────────────────────────────────────

@router.get("/api/files/{file_id}")
async def serve_file(file_id: str) -> Response:
    """Serve a previously uploaded file by its file_id (UUID)."""
    matches = list(Path(settings.upload_dir).glob(f"{file_id}.*"))
    if not matches:
        raise HTTPException(status_code=404, detail=f"File '{file_id}' not found")
    file_path = matches[0]
    media_type = _MIME_BY_SUFFIX.get(file_path.suffix.lower(), "application/octet-stream")
    return Response(content=file_path.read_bytes(), media_type=media_type)


# ── On-demand bounding-box regions ────────────────────────────────────────────
# Completely separate from the claim pipeline.
# Called only when the user clicks "View regions" in the UI.

@router.get("/api/files/{file_id}/regions")
async def get_document_regions(file_id: str, doc_type: str = "UNKNOWN") -> dict:
    """
    Detect and return field bounding boxes for a single uploaded document.

    Query param:
      doc_type — DocumentType hint (PRESCRIPTION, HOSPITAL_BILL, etc.)

    Response:
      {file_id, doc_type, regions: [{field, value, bbox:[y1,x1,y2,x2], category}]}
    """
    matches = list(Path(settings.upload_dir).glob(f"{file_id}.*"))
    if not matches:
        raise HTTPException(status_code=404, detail=f"File '{file_id}' not found")

    file_path = matches[0]
    mime_type = _MIME_BY_SUFFIX.get(file_path.suffix.lower(), "image/jpeg")
    file_bytes = file_path.read_bytes()

    from app.models.document import DocumentType
    from app.providers.gemini_vision import gemini_vision

    try:
        dtype = DocumentType(doc_type.upper())
    except ValueError:
        dtype = DocumentType.UNKNOWN

    regions = await gemini_vision.extract_with_bboxes(file_id, dtype, file_bytes, mime_type)
    return {"file_id": file_id, "doc_type": dtype.value, "regions": regions}


# ── SSE live trace stream ─────────────────────────────────────────────────────

@router.get("/api/claims/{claim_id}/trace")
async def trace_live(claim_id: str) -> StreamingResponse:
    """
    Server-Sent Events stream of TraceEvents for a claim.

    Connect BEFORE submitting the claim to receive live events as each
    agent completes. The stream closes automatically when the pipeline
    finishes (event_bus.close_stream is called by main.py after the graph).

    If the claim is already complete the stream closes immediately after
    a short timeout — use /trace/replay for completed claims.
    """
    queue = event_bus.subscribe(claim_id)

    async def generate():
        try:
            while True:
                try:
                    item = await asyncio.wait_for(queue.get(), timeout=120.0)
                except asyncio.TimeoutError:
                    yield "data: {\"error\": \"stream_timeout\"}\n\n"
                    break

                if event_bus.is_done(item):
                    yield "data: {\"done\": true}\n\n"
                    break

                yield f"data: {item.model_dump_json()}\n\n"
        finally:
            event_bus.unsubscribe(claim_id, queue)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # disable Nginx buffering
        },
    )


# ── SSE replay stream ─────────────────────────────────────────────────────────

@router.get("/api/claims/{claim_id}/trace/replay")
async def trace_replay(claim_id: str, speed: float = 1.0) -> StreamingResponse:
    """
    Re-stream stored trace events for a completed claim.

    Adds a 50 ms delay between events (adjusted by speed) to make the
    replay feel like live processing — this is the hero moment in the demo.
    speed=1.0 is normal pace; speed=2.0 plays at 2× speed.
    """
    repo = TraceRepository(settings.db_path)
    events = await repo.get_events(claim_id)

    if not events:
        raise HTTPException(
            status_code=404,
            detail=f"No trace events found for claim '{claim_id}'. "
                   f"Either the claim does not exist or is still processing.",
        )

    delay = max(0.02, 0.05 / max(speed, 0.1))

    async def generate():
        for event in events:
            yield f"data: {event.model_dump_json()}\n\n"
            await asyncio.sleep(delay)
        yield "data: {\"done\": true, \"total_events\": " + str(len(events)) + "}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
