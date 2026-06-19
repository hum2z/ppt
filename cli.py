#!/usr/bin/env python3
"""Command-line entry point for the deck replicator.

Usage:
    export ANTHROPIC_API_KEY=sk-...
    python cli.py reference.pptx "Introduction to Photosynthesis" -o out.pptx \
        --audience "high-school students"
"""

from __future__ import annotations

import argparse
import sys

from app.deck import apply_translations, extract_blueprint
from app.generate import GenerationError, generate_content


def main() -> int:
    parser = argparse.ArgumentParser(description="Replicate a reference .pptx for a new topic.")
    parser.add_argument("reference", help="Path to the reference .pptx")
    parser.add_argument("topic", help="New topic/subject for the generated deck")
    parser.add_argument("-o", "--out", default="replicated.pptx", help="Output .pptx path")
    parser.add_argument("--audience", default=None, help="Target audience (optional)")
    parser.add_argument("--extra", default=None, help="Extra guidance (optional)")
    parser.add_argument("--model", default=None, help="Override the Claude model id")
    args = parser.parse_args()

    print(f"Reading reference: {args.reference}")
    blueprint = extract_blueprint(args.reference)
    print(f"  {len(blueprint.slides)} slides, {blueprint.element_count} text blocks")

    print(f"Generating content for: {args.topic!r} …")
    try:
        translations = generate_content(
            blueprint,
            topic=args.topic,
            audience=args.audience,
            extra=args.extra,
            model=args.model,
        )
    except GenerationError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    replaced = apply_translations(args.reference, args.out, translations)
    print(f"Wrote {args.out} ({replaced} text blocks rewritten)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
