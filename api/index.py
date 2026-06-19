"""Vercel serverless entrypoint.

Vercel's Python runtime detects the ASGI ``app`` exported here and serves it.
All routes are defined on the FastAPI app in ``app.main``; ``vercel.json``
rewrites every path to this function so the app handles its own routing.
"""

from app.main import app  # noqa: F401  (re-exported for the Vercel runtime)
