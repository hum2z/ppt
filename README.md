# Deck Replicator

Give it a reference PowerPoint, give it a new topic, and get back **the same
deck** — identical fonts, colours, layouts, and images — rewritten for your new
subject by the Claude API.

It works by *reusing the real template*: the app opens your reference `.pptx`,
swaps the **text** of every slide for new topic-appropriate content, and leaves
everything else (theme, formatting, charts, pictures, positioning) untouched.
The result is a faithful clone that looks hand-made to match the original.

## How it works

```
reference.pptx ──▶ extract blueprint ──▶ Claude writes parallel content
                   (ids + roles + text)   (same ids, new topic)
                                              │
output.pptx  ◀── write text back into a clone of the reference ◀───┘
```

1. **Extract** — every editable paragraph/table cell gets a stable positional
   id, its role (title / subtitle / body / table-cell) and outline level.
   (`app/deck.py`)
2. **Generate** — the blueprint is sent to Claude, which returns new text for
   each id, mirroring the original's structure, length and tone. Output is forced
   through a tool schema so it's always valid, id-keyed JSON. (`app/generate.py`)
3. **Rewrite** — new text is written into a *clone* of the reference, replacing
   only the characters inside existing runs so all styling survives.
   (`app/deck.py`)

## Quick start

```bash
pip install -r requirements.txt
cp .env.example .env          # then add your ANTHROPIC_API_KEY
./run.sh                      # → http://localhost:8000
```

Open the page, drop in a `.pptx`, type a topic (optionally an audience and extra
guidance), and click **Replicate deck**. Your browser downloads the new file.

## Deploy on Vercel

The repo is Vercel-ready: `api/index.py` exposes the FastAPI app to Vercel's
Python runtime and `vercel.json` rewrites all routes to it. Runtime files are
written to `/tmp` (the only writable path on serverless).

Because a public deployment shouldn't ship a shared secret, the app runs in
**bring-your-own-key** mode: visitors paste their own Anthropic API key into the
form (used only for that request, never stored). To run it as a private app with
a fixed key instead, set `ANTHROPIC_API_KEY` in the Vercel project's environment
variables — the key field then disappears and the server key is used.

## Command line

No browser needed:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
python cli.py reference.pptx "Introduction to Photosynthesis" \
    -o photosynthesis.pptx --audience "high-school students"
```

## Configuration

| Variable            | Default              | Purpose                              |
|---------------------|----------------------|--------------------------------------|
| `ANTHROPIC_API_KEY` | —                    | Required. Claude API key.            |
| `CLAUDE_MODEL`      | `claude-sonnet-4-6`  | Model used to write slide content.   |
| `HOST` / `PORT`     | `0.0.0.0` / `8000`   | Web server bind.                     |
| `MAX_UPLOAD_BYTES`  | `26214400` (25 MB)   | Upload size limit.                   |

## Tests

The core engine is tested offline (no API key needed) — it builds a styled
sample deck and asserts the extract→rewrite round-trip swaps text while
preserving font size, weight and colour:

```bash
python tests/test_deck.py
```

## Notes & limits

- Text inside **grouped shapes** and text rendered as part of an **image** can't
  be edited (PowerPoint stores it as pixels, not text). Everything else —
  placeholders, text boxes, and tables — is rewritten.
- Slide **count and structure are preserved** exactly; the app rewrites the deck
  you give it rather than inventing new slides. Use a reference with the shape
  you want the output to have.
- Charts/SmartArt keep their original data unless their labels happen to be
  editable text frames.
