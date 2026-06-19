"""Topic-aware content generation via the Claude API.

Given the reference deck's blueprint, we ask Claude to produce parallel text
for a new topic: same slide count, same element ids, same structural role and
roughly the same length/bullet rhythm as the original.  Output is forced through
a tool schema so we always get well-formed, id-keyed JSON back.
"""

from __future__ import annotations

import json
import os
from typing import Dict, List, Optional

import anthropic

from .deck import DeckBlueprint

DEFAULT_MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-6")

SYSTEM_PROMPT = """You are a presentation ghost-writer. You are given the full \
text outline of a REFERENCE slide deck, element by element, each with a stable \
id, a role (title/subtitle/body/table-cell) and an outline level.

Your job: rewrite EVERY element so the deck is now about the user's NEW topic, \
while mirroring the reference's structure and tone.

Hard rules:
- Return new text for every id you are given. Do not invent or drop ids.
- Keep each element's role: a title stays a short title, a body bullet stays a \
bullet of comparable length, a table header stays a header.
- Match length and specificity: if the original bullet is ~8 words, the new one \
should be ~8 words. Mirror parallel phrasing across sibling bullets.
- Preserve any structural/numbering cues from the original (e.g. "Step 1", \
"Q1", "Pros:/Cons:", agenda numbering) but adapt them to the new topic.
- The new deck must be coherent end to end: respect the narrative arc implied by \
slide order (intro -> body -> summary, etc.).
- Plain text only. No markdown, no bullet glyphs, no surrounding quotes.
- Write in the same language as the reference unless the topic clearly implies \
otherwise."""

# Tool schema forces structured, id-keyed output.
SUBMIT_TOOL = {
    "name": "submit_deck",
    "description": "Return the rewritten text for every element of the new deck.",
    "input_schema": {
        "type": "object",
        "properties": {
            "elements": {
                "type": "array",
                "description": "One entry per element id from the reference deck.",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string", "description": "The element id, copied verbatim."},
                        "text": {"type": "string", "description": "New text for this element."},
                    },
                    "required": ["id", "text"],
                },
            }
        },
        "required": ["elements"],
    },
}


class GenerationError(RuntimeError):
    pass


def _build_user_prompt(blueprint: DeckBlueprint, topic: str, audience: Optional[str], extra: Optional[str]) -> str:
    parts = [
        f"NEW TOPIC: {topic}",
    ]
    if audience:
        parts.append(f"AUDIENCE: {audience}")
    if extra:
        parts.append(f"ADDITIONAL GUIDANCE: {extra}")
    parts.append(
        "REFERENCE DECK OUTLINE (rewrite every element for the new topic, "
        "returning the same ids via the submit_deck tool):"
    )
    parts.append(json.dumps(blueprint.to_prompt_json(), ensure_ascii=False, indent=2))
    return "\n\n".join(parts)


def generate_content(
    blueprint: DeckBlueprint,
    topic: str,
    audience: Optional[str] = None,
    extra: Optional[str] = None,
    model: Optional[str] = None,
    api_key: Optional[str] = None,
) -> Dict[str, str]:
    """Return a mapping of element id -> new text for the requested topic."""
    key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise GenerationError(
            "ANTHROPIC_API_KEY is not set. Add it to the environment so the app "
            "can call the Claude API."
        )
    if blueprint.element_count == 0:
        raise GenerationError(
            "No editable text was found in the reference deck. It may be image-only."
        )

    client = anthropic.Anthropic(api_key=key)
    user_prompt = _build_user_prompt(blueprint, topic, audience, extra)

    # Scale the output budget with deck size; clamp to a sane ceiling.
    max_tokens = min(16000, max(2048, blueprint.element_count * 80))

    try:
        response = client.messages.create(
            model=model or DEFAULT_MODEL,
            max_tokens=max_tokens,
            system=SYSTEM_PROMPT,
            tools=[SUBMIT_TOOL],
            tool_choice={"type": "tool", "name": "submit_deck"},
            messages=[{"role": "user", "content": user_prompt}],
        )
    except anthropic.APIError as exc:  # pragma: no cover - network dependent
        raise GenerationError(f"Claude API request failed: {exc}") from exc

    elements = _extract_tool_result(response)
    translations: Dict[str, str] = {}
    for item in elements:
        eid = item.get("id")
        text = item.get("text")
        if isinstance(eid, str) and isinstance(text, str) and text.strip():
            translations[eid] = text.strip()

    if not translations:
        raise GenerationError("The content model returned no usable text.")
    return translations


def _extract_tool_result(response) -> List[dict]:
    for block in response.content:
        if getattr(block, "type", None) == "tool_use" and block.name == "submit_deck":
            return block.input.get("elements", [])
    raise GenerationError("The content model did not return structured output.")
