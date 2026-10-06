import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BACKEND_DIR / ".env")  # does not override variables already set


def _required(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing environment variable: {name}")
    return value


@dataclass(frozen=True)
class Settings:
    account: str
    user: str
    role: str
    warehouse: str
    database: str
    private_key_file: str
    private_key: str
    llm_model: str


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    key_text = os.getenv("SNOWFLAKE_PRIVATE_KEY", "")
    key_file = os.getenv("SNOWFLAKE_PRIVATE_KEY_FILE", "")
    if not key_text and not key_file:
        raise RuntimeError("Set SNOWFLAKE_PRIVATE_KEY or SNOWFLAKE_PRIVATE_KEY_FILE")
    if key_file and not Path(key_file).is_absolute():
        key_file = str((BACKEND_DIR / key_file).resolve())

    return Settings(
        account=_required("SNOWFLAKE_ACCOUNT"),
        user=_required("SNOWFLAKE_USER"),
        role=_required("SNOWFLAKE_ROLE"),
        warehouse=_required("SNOWFLAKE_WAREHOUSE"),
        database=_required("SNOWFLAKE_DATABASE"),
        private_key_file=key_file,
        private_key=key_text,
        llm_model=os.getenv("LLM_MODEL", "claude-opus-4-6"),
    )