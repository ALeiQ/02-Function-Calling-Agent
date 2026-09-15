"""SQL guardrails: SELECT-only, read-only, multi-statement injection."""

import json

import pytest

from scripts.seed_db import build
from src.tools import execute
from src.tools.sql import UnsafeQueryError, guard, run_query


@pytest.fixture(scope="module")
def demo_db(tmp_path_factory):
    return build(str(tmp_path_factory.mktemp("db") / "demo.db"))


def test_select_all_employees(demo_db: str) -> None:
    payload = json.loads(run_query("SELECT * FROM employees", demo_db))
    assert payload["rows"] == 12
    assert payload["columns"] == ["id", "name", "dept", "salary", "join_date"]


def test_aggregate_query(demo_db: str) -> None:
    payload = json.loads(run_query("SELECT COUNT(*) AS n FROM orders", demo_db))
    assert payload["rows"] == 1
    assert payload["data"][0]["n"] == 15


def test_case_insensitive_and_whitespace(demo_db: str) -> None:
    payload = json.loads(run_query("  select   count(*)   from   employees ", demo_db))
    assert payload["data"][0]["count(*)"] == 12


def test_no_rows(demo_db: str) -> None:
    result = run_query("SELECT * FROM orders WHERE amount > 99999", demo_db)
    assert "没有匹配" in result


@pytest.mark.parametrize(
    "query",
    [
        "DROP TABLE employees",
        "delete from employees",
        "INSERT INTO employees (name) VALUES ('x')",
        "UPDATE employees SET salary = 1",
        "PRAGMA journal_mode",
        "ATTACH DATABASE",
        "select * from employees; delete from employees",
        "SELECT * FROM employees;",
    ],
)
def test_unsafe_queries_rejected(query: str) -> None:
    with pytest.raises(UnsafeQueryError):
        guard(query)
    result = execute({"function": {"name": "sql", "arguments": {"query": query}}})
    assert result.startswith("ERROR:")


def test_guard_allows_valid() -> None:
    got = guard("  SELECT   name , salary  FROM employees ")
    assert got == "select name , salary from employees"


def test_dispatch_via_agent_tools(demo_db, monkeypatch) -> None:
    from src.config import settings

    monkeypatch.setattr(settings, "db_path", demo_db)
    query = (
        "SELECT dept, AVG(salary) AS avg_salary "
        "FROM employees GROUP BY dept"
    )
    call = {"function": {"name": "sql", "arguments": {"query": query}}}
    payload = json.loads(execute(call))
    assert payload["rows"] > 1


def test_missing_database_error(monkeypatch) -> None:
    from src.config import settings

    missing = "/nonexistent/path/db.sqlite"
    with pytest.raises(UnsafeQueryError):
        run_query("SELECT 1", missing)
    monkeypatch.setattr(settings, "db_path", missing)
    result = execute({"function": {"name": "sql", "arguments": {"query": "SELECT 1"}}})
    assert result.startswith("ERROR:")
    assert "无法打开只读数据库" in result


def test_bad_sql_error(demo_db: str) -> None:
    with pytest.raises(UnsafeQueryError):
        run_query("SELECT missing_column FROM employees", demo_db)
    result = execute(
        {"function": {"name": "sql", "arguments": {"query": "SELECT missing FROM employees"}}}
    )
    assert result.startswith("ERROR:")
    assert "SQL 执行错误" in result
