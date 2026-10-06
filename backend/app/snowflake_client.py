import json
from functools import lru_cache
from typing import Any

import snowflake.connector
from snowflake.connector import DictCursor

from app.config import get_settings


@lru_cache(maxsize=1)
def get_connection():
    s = get_settings()
    kwargs = {
        "account": s.account,
        "user": s.user,
        "role": s.role,
        "warehouse": s.warehouse,
        "database": s.database,
        "client_session_keep_alive": True,
    }
    if s.private_key:
        from cryptography.hazmat.primitives import serialization

        key = serialization.load_pem_private_key(s.private_key.encode(), password=None)
        kwargs["private_key"] = key.private_bytes(
            serialization.Encoding.DER,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    else:
        kwargs["private_key_file"] = s.private_key_file
    return snowflake.connector.connect(**kwargs)


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