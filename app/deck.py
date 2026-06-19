"""Reference-deck parsing and rewriting.

The replication strategy is "reuse the real template": we open the reference
``.pptx`` itself, walk every text-bearing element in a deterministic order, and
assign each a stable positional id.  Content generation produces new text keyed
by those same ids, which we then write back into a *clone* of the reference
file.  Because we only swap the characters inside existing runs, every bit of
visual styling (theme, fonts, colours, sizes, images, charts, layout) is
preserved exactly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE


@dataclass
class TextElement:
    """A single editable paragraph in the deck."""

    id: str
    text: str
    role: str  # "title" | "subtitle" | "body" | "table-cell"
    level: int  # outline/indent level for bullets


@dataclass
class SlideBlueprint:
    index: int
    layout: str
    elements: List[TextElement] = field(default_factory=list)


@dataclass
class DeckBlueprint:
    slides: List[SlideBlueprint] = field(default_factory=list)

    @property
    def element_count(self) -> int:
        return sum(len(s.elements) for s in self.slides)

    def to_prompt_json(self) -> List[dict]:
        """Compact, ordered structure handed to the content model."""
        return [
            {
                "slide": s.index + 1,
                "layout": s.layout,
                "elements": [
                    {
                        "id": e.id,
                        "role": e.role,
                        "level": e.level,
                        "text": e.text,
                    }
                    for e in s.elements
                ],
            }
            for s in self.slides
        ]


def _placeholder_role(shape) -> Optional[str]:
    """Best-effort semantic role for a placeholder shape."""
    try:
        if not shape.is_placeholder:
            return None
        ph_type = shape.placeholder_format.type
    except (AttributeError, ValueError):
        return None
    name = str(ph_type)
    if "TITLE" in name or "CENTER_TITLE" in name:
        return "title"
    if "SUBTITLE" in name:
        return "subtitle"
    return None


def _iter_text_frames(slide):
    """Yield ``(shape_idx, kind_hint, table_pos, text_frame)`` tuples.

    ``table_pos`` is ``None`` for plain shapes or ``(row, col)`` for table
    cells.  ``kind_hint`` carries a placeholder role when one is detectable.
    """
    for shape_idx, shape in enumerate(slide.shapes):
        if shape.has_text_frame:
            yield shape_idx, _placeholder_role(shape), None, shape.text_frame
        elif shape.shape_type == MSO_SHAPE_TYPE.TABLE or shape.has_table:
            table = shape.table
            for r, row in enumerate(table.rows):
                for c, cell in enumerate(row.cells):
                    yield shape_idx, "table-cell", (r, c), cell.text_frame


def _layout_name(slide) -> str:
    try:
        return slide.slide_layout.name or "slide"
    except Exception:
        return "slide"


def extract_blueprint(path: str) -> DeckBlueprint:
    """Parse a reference deck into an ordered, id-stamped blueprint."""
    prs = Presentation(path)
    deck = DeckBlueprint()

    for s_idx, slide in enumerate(prs.slides):
        blueprint = SlideBlueprint(index=s_idx, layout=_layout_name(slide))
        for shape_idx, role_hint, table_pos, tf in _iter_text_frames(slide):
            for p_idx, para in enumerate(tf.paragraphs):
                text = para.text.strip()
                if not text:
                    continue
                if table_pos is None:
                    eid = f"s{s_idx}_sh{shape_idx}_p{p_idx}"
                    # Trust an explicit placeholder role; otherwise treat as body.
                    role = role_hint or "body"
                else:
                    r, c = table_pos
                    eid = f"s{s_idx}_sh{shape_idx}_t{r}-{c}_p{p_idx}"
                    role = "table-cell"
                blueprint.elements.append(
                    TextElement(
                        id=eid,
                        text=text,
                        role=role,
                        level=para.level or 0,
                    )
                )
        deck.slides.append(blueprint)

    return deck


def _set_paragraph_text(para, new_text: str) -> None:
    """Replace a paragraph's text while keeping the first run's formatting.

    python-pptx exposes no public "set text, keep style" helper, so we keep the
    first run (carrying font/colour/size), overwrite its characters, and drop
    any remaining runs in the paragraph.
    """
    runs = para.runs
    if not runs:
        # Paragraph had text via the frame but no runs we can target; skip
        # rather than risk losing the originating XML.
        return
    runs[0].text = new_text
    for extra in runs[1:]:
        extra._r.getparent().remove(extra._r)


def apply_translations(src_path: str, dst_path: str, translations: Dict[str, str]) -> int:
    """Write ``translations`` (id -> new text) into a clone of the reference.

    Returns the number of paragraphs actually replaced.  Any element id absent
    from ``translations`` keeps its original text, so partial results still
    yield a valid deck.
    """
    prs = Presentation(src_path)
    replaced = 0

    for s_idx, slide in enumerate(prs.slides):
        for shape_idx, _role, table_pos, tf in _iter_text_frames(slide):
            for p_idx, para in enumerate(tf.paragraphs):
                if not para.text.strip():
                    continue
                if table_pos is None:
                    eid = f"s{s_idx}_sh{shape_idx}_p{p_idx}"
                else:
                    r, c = table_pos
                    eid = f"s{s_idx}_sh{shape_idx}_t{r}-{c}_p{p_idx}"
                new_text = translations.get(eid)
                if new_text is None or new_text == para.text.strip():
                    continue
                _set_paragraph_text(para, new_text)
                replaced += 1

    prs.save(dst_path)
    return replaced
