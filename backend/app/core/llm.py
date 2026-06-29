import json
from functools import lru_cache
from typing import Any

from openai import OpenAI

from app.core.config import get_settings

settings = get_settings()


@lru_cache
def groq_client() -> OpenAI:
    # OpenAI-compatible client pointed at Groq (see memory.md D7).
    return OpenAI(api_key=settings.GROQ_API_KEY, base_url=settings.GROQ_BASE_URL)


def groq_json(system: str, user: str, model: str | None = None) -> dict[str, Any]:
    """Call Groq with JSON mode and parse the JSON object response."""
    resp = groq_client().chat.completions.create(
        model=model or settings.INTAKE_MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        response_format={"type": "json_object"},
        temperature=0,
    )
    return json.loads(resp.choices[0].message.content or "{}")
