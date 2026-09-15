"""Create and populate the demo SQLite database (employees + orders).

Run:  python -m scripts.seed_db
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from src.config import settings


def build(db_path: str | None = None) -> str:
    db_path = db_path or settings.db_path
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()

    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(
            """
            CREATE TABLE employees (
                id        INTEGER PRIMARY KEY,
                name      TEXT NOT NULL,
                dept      TEXT NOT NULL,
                salary    INTEGER NOT NULL,
                join_date TEXT NOT NULL
            );

            CREATE TABLE orders (
                id         INTEGER PRIMARY KEY,
                customer   TEXT NOT NULL,
                amount     REAL NOT NULL,
                status     TEXT NOT NULL,
                order_date TEXT NOT NULL
            );

            INSERT INTO employees (name, dept, salary, join_date) VALUES
                ('张伟',   '工程部', 18000, '2021-03-15'),
                ('王芳',   '工程部', 22000, '2019-07-01'),
                ('李娜',   '产品部', 17000, '2020-11-23'),
                ('刘洋',   '产品部', 15500, '2022-02-10'),
                ('陈静',   '设计部', 16500, '2021-08-30'),
                ('杨帆',   '设计部', 14200, '2023-01-12'),
                ('赵磊',   '销售部', 12800, '2020-05-18'),
                ('孙悦',   '销售部', 13500, '2022-09-06'),
                ('周杰',   '销售部', 15000, '2018-12-24'),
                ('吴敏',   '人力',   12500, '2021-04-02'),
                ('郑强',   '人力',   11800, '2023-03-19'),
                ('冯雪',   '财务部', 16000, '2019-10-11');

            INSERT INTO orders (customer, amount, status, order_date) VALUES
                ('京东',   1280.00, '已完成', '2025-01-05'),
                ('美团',    456.50, '已完成', '2025-01-07'),
                ('快手',   3200.00, '处理中', '2025-01-09'),
                ('字节跳动', 989.99, '已完成', '2025-01-12'),
                ('腾讯',    2150.00, '已完成', '2025-01-15'),
                ('网易',     780.25, '已取消', '2025-01-18'),
                ('阿里',   5600.00, '处理中', '2025-01-20'),
                ('滴滴',    1235.00, '已完成', '2025-01-22'),
                ('拼多多',   900.00, '已完成', '2025-01-25'),
                ('小米',    1888.88, '处理中', '2025-01-28'),
                ('百度',    3450.00, '已完成', '2025-02-01'),
                ('哔哩哔哩', 1299.00, '已完成', '2025-02-03'),
                ('饿了么',   329.90, '已取消', '2025-02-05'),
                ('携程',    2780.00, '处理中', '2025-02-08'),
                ('比亚迪',  4200.00, '已完成', '2025-02-10');
            """
        )
        conn.commit()
    finally:
        conn.close()

    return db_path


def main() -> None:
    db_path = build()
    print(f"demo db created: {db_path}")


if __name__ == "__main__":
    main()
