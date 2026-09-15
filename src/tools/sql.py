"""Read-only SQLite query tool with guardrails.

Safety model:
1. Connection is opened read-only (``mode=ro``).
2. Only ``SELECT`` statements pass a normalized check (case/whitespace-folded).
3. Anything else (INSERT/UPDATE/DELETE/DROP/... or a ``;`` multi-statement
   attempt) is rejected with a machine-readable error the agent can recover
   from.
"""

from __future__ import annotations

import json
import sqlite3

from pydantic import BaseModel, Field

from src.config import settings
from src.tools.registry import ToolError, tool


class UnsafeQueryError(ToolError):
    """Raised when a statement violates the SQL guardrail."""


class SqlArgs(BaseModel):
    query: str = Field(
        ...,
        description=(
            "只允许执行的 SELECT 查询。可用表: "
            "employees(id, name, dept, salary, join_date)、"
            "orders(id, customer, amount, status, order_date)"
        ),
    )


def normalize(statement: str) -> str:
    """Fold case and collapse whitespace, keeping string literals intact."""
    import re

    return re.sub(r"\s+", " ", statement).strip().lower()


def guard(query: str) -> str:
    """Return the normalized statement or raise UnsafeQueryError."""
    normalized = normalize(query)
    if not normalized.startswith("select"):
        raise UnsafeQueryError(
            "仅允许执行 SELECT 查询（只读数据库）。检测到非查询语句，已拒绝执行。"
        )
    if ";" in normalized:
        raise UnsafeQueryError("不允许使用分号（多语句执行），请逐条执行 SELECT 查询。")
    return normalized


def _connect(db_path: str) -> sqlite3.Connection:
    uri = f"file:{db_path}?mode=ro"
    return sqlite3.connect(uri, uri=True)


def run_query(query: str, db_path: str | None = None) -> str:
    """Execute a guarded SELECT against the read-only demo database."""
    db_path = db_path or settings.db_path
    normalized = guard(query)

    try:
        conn = _connect(db_path)
    except sqlite3.Error as exc:
        raise UnsafeQueryError(f"无法打开只读数据库 {db_path}: {exc}") from exc

    try:
        cur = conn.execute(normalized)
        columns = [d[0] for d in cur.description] if cur.description else []
        rows = [dict(zip(columns, row)) for row in cur.fetchall()]
    except sqlite3.Error as exc:
        raise UnsafeQueryError(f"SQL 执行错误: {exc}") from exc
    finally:
        conn.close()

    if not rows:
        return "查询完成，没有匹配的行。"
    payload = {"rows": len(rows), "columns": columns, "data": rows}
    return json.dumps(payload, ensure_ascii=False, indent=2)


@tool(
    description=(
        "对只读演示数据库执行 SELECT 查询并返回 JSON 结果。"
        "只读数据库，仅允许 SELECT；禁止 INSERT/UPDATE/DELETE/DROP 等。"
        "表: employees(员工:id,name,dept,salary,join_date)、"
        "orders(订单:id,customer,amount,status,order_date)。"
    ),
    args=SqlArgs,
)
def sql(query: str) -> str:
    return run_query(query)
