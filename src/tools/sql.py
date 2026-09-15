"""Read-only SQLite query tool with guardrails.

Safety model:
1. Connection is opened read-only (``mode=ro``).
2. Only ``SELECT`` statements pass a normalized check (case/whitespace-folded).
3. Anything else (INSERT/UPDATE/DELETE/DROP/... or the DB name) is rejected
   with a machine-readable error the agent can recover from.

TODO(milestone 2): implement ``run_query`` + ``sql_guardrail`` and expose as a tool.
"""


class UnsafeQueryError(ValueError):
    """Raised when a statement violates the SQL guardrail."""