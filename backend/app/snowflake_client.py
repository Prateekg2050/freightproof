import json
from functools import lru_cache
from typing import Any

import snowflake.connector
from snowflake.connector import DictCursor

from app.config import get_settings


@lru_cache(maxsize=1)
def get_connection():
    s = get_settings()
    return snowflake.connector.connect(
        account=s.account,
        user=s.user,
        role=s.role,
        warehouse=s.warehouse,
        database=s.database,
        private_key_file=s.private_key_file,
        client_session_keep_alive=True,
    )


def query(sql: str, params: tuple | None = None) -> list[dict[str, Any]]:
    """Run a query with bound parameters and return rows as dicts."""
    with get_connection().cursor(DictCursor) as cur:
        cur.execute(sql, params or ())
        return cur.fetchall()


def parse_variant(value: Any) -> Any:
    """VARIANT, ARRAY and OBJECT columns arrive as JSON strings."""
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value