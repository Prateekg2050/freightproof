import json
import re

from app.config import get_settings
from app.snowflake_client import query

_MODEL_NAME = re.compile(r"^[a-z0-9.\-]+$")


def complete(prompt: str) -> str:
    """Call Snowflake Cortex AI_COMPLETE. Data and inference stay in Snowflake."""
    model = get_settings().llm_model
    if not _MODEL_NAME.match(model):
        raise ValueError(f"Invalid model name: {model}")

    rows = query(f"SELECT AI_COMPLETE('{model}', %s) AS RESPONSE", (prompt,))
    text = rows[0]["RESPONSE"] or ""

    # Some responses come back JSON-quoted
    if text.startswith('"'):
        try:
            text = json.loads(text)
        except json.JSONDecodeError:
            pass
    return text.strip()