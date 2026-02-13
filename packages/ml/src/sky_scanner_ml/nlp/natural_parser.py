"""Natural language parser for flight search queries using Claude."""

from __future__ import annotations

import json
import re
from datetime import UTC, date

import anthropic

from sky_scanner_ml.nlp.constraint_schema import NaturalSearchConstraints
from sky_scanner_ml.nlp.prompts import SYSTEM_PROMPT, build_user_prompt


def _extract_json(text: str) -> dict:
    """Extract JSON from a response that may contain markdown code fences."""
    # Strip markdown code fences if present
    match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if match:
        text = match.group(1)
    return json.loads(text.strip())


async def parse_natural_query(
    query: str,
    api_key: str,
    today: str | None = None,
) -> NaturalSearchConstraints:
    """Parse a natural language flight search query into structured constraints.

    Args:
        query: Natural language search query (Korean or English).
        api_key: Anthropic API key.
        today: Today's date as YYYY-MM-DD. Defaults to current UTC date.

    Returns:
        Parsed NaturalSearchConstraints.

    Raises:
        ValueError: If the query cannot be parsed after retries.
    """
    if today is None:
        today = date.today(UTC).isoformat()

    client = anthropic.AsyncAnthropic(api_key=api_key)
    user_prompt = build_user_prompt(query, today)

    last_error: Exception | None = None
    for _attempt in range(2):
        try:
            response = await client.messages.create(
                model="claude-haiku-4-5-20251001",
                temperature=0,
                max_tokens=1024,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_prompt}],
            )

            raw_text = response.content[0].text
            data = _extract_json(raw_text)
            return NaturalSearchConstraints(**data)
        except Exception as exc:
            last_error = exc
            continue

    msg = f"Failed to parse natural language query after 2 attempts: {last_error}"
    raise ValueError(msg)
