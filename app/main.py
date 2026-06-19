"""FastAPI web app: upload a reference .pptx, get back a topic-swapped clone."""

from __future__ import annotations

import os
import re
import tempfile
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from .deck import apply_translations, extract_blueprint
from .generate import DEFAULT_MODEL, GenerationError, generate_content

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"
# Runtime artifacts live in a writable temp dir (required on serverless hosts
# like Vercel, where the deployment filesystem is read-only except for /tmp).
WORK_DIR = Path(os.environ.get("DECK_WORK_DIR", tempfile.gettempdir()))
UPLOAD_DIR = WORK_DIR / "deck_uploads"
OUTPUT_DIR = WORK_DIR / "deck_outputs"
for d in (UPLOAD_DIR, OUTPUT_DIR):
    d.mkdir(parents=True, exist_ok=True)

MAX_UPLOAD_BYTES = int(os.environ.get("MAX_UPLOAD_BYTES", 25 * 1024 * 1024))

app = FastAPI(title="Deck Replicator", version="1.0.0")


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()
    return (slug or "deck")[:50]


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    return HTMLResponse((STATIC_DIR / "index.html").read_text(encoding="utf-8"))


@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "model": DEFAULT_MODEL,
        "api_key_configured": bool(os.environ.get("ANTHROPIC_API_KEY")),
    }


@app.post("/api/replicate")
async def replicate(
    file: UploadFile = File(...),
    topic: str = Form(...),
    audience: str = Form(""),
    extra: str = Form(""),
    api_key: str = Form(""),
):
    if not file.filename or not file.filename.lower().endswith(".pptx"):
        raise HTTPException(400, "Please upload a .pptx PowerPoint file.")
    if not topic.strip():
        raise HTTPException(400, "Please provide a topic for the new deck.")

    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, f"File exceeds the {MAX_UPLOAD_BYTES // (1024*1024)} MB limit.")

    job_id = uuid.uuid4().hex[:12]
    src_path = UPLOAD_DIR / f"{job_id}.pptx"
    src_path.write_bytes(data)

    try:
        blueprint = extract_blueprint(str(src_path))
    except Exception as exc:  # corrupt/non-pptx
        src_path.unlink(missing_ok=True)
        raise HTTPException(400, f"Could not read the presentation: {exc}") from exc

    try:
        translations = generate_content(
            blueprint,
            topic=topic.strip(),
            audience=audience.strip() or None,
            extra=extra.strip() or None,
            api_key=api_key.strip() or None,
        )
    except GenerationError as exc:
        raise HTTPException(502, str(exc)) from exc

    out_name = f"{_slugify(topic)}-{job_id}.pptx"
    out_path = OUTPUT_DIR / out_name
    replaced = apply_translations(str(src_path), str(out_path), translations)
    src_path.unlink(missing_ok=True)

    if replaced == 0:
        out_path.unlink(missing_ok=True)
        raise HTTPException(502, "No slide text could be replaced; the deck was left unchanged.")

    return FileResponse(
        out_path,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        filename=out_name,
        headers={
            "X-Slides": str(len(blueprint.slides)),
            "X-Elements-Replaced": str(replaced),
        },
    )


# Serve any static assets (kept last so it doesn't shadow API routes).
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
