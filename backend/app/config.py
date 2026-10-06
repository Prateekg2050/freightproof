import os
from dataclasses import dataclass
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()


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
    llm_model: str


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings(
        account=_required("SNOWFLAKE_ACCOUNT"),
        user=_required("SNOWFLAKE_USER"),
        role=_required("SNOWFLAKE_ROLE"),
        warehouse=_required("SNOWFLAKE_WAREHOUSE"),
        database=_required("SNOWFLAKE_DATABASE"),
        private_key_file=_required("SNOWFLAKE_PRIVATE_KEY_FILE"),
        llm_model=os.getenv("LLM_MODEL", "claude-opus-4-6"),
    )