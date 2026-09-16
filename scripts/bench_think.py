#!/usr/bin/env python3
"""对比 loop 层 think 开关性能(qwen3:8b,真身仓库内直调)。

四指标,think=None(=settings 默认,关) vs think=True 各 3 轮取中位:
  TTFT    首 chunk 墙钟(流式才可拆;非流=首包等价)
  tok/s   输出 token / 生成段墙钟(仅流式精确)
  总墙钟  整轮秒
  总token reply 的 token 数(Ollama message 无计数,用 content 切词近似)

跑法: .venv/bin/python scripts/bench_think.py [--stream|--once] [--turns 3]
默认 --stream --turns 3。
"""
from __future__ import annotations

import argparse
import statistics
import time
from datetime import UTC, datetime

from src.agent import loop
from src.config import settings

MESSAGES = [
    {"role": "user", "content": "用一段话解释 SQL 索引为什么要 B+ 树而不是哈希表。"},
]
TOOLS: list = []


def _approx_tokens(text: str) -> int:
    return len(text.split()) + len(text) // 40


def _run_stream(think: bool | None) -> dict:
    t0 = time.perf_counter()
    ttft = None
    n_chunks = 0
    full = []
    for kind, payload in loop._chat_stream_once(MESSAGES, TOOLS, None, think=think):
        if ttft is None:
            ttft = time.perf_counter() - t0
        if kind == "message":
            full.append(payload.get("content", ""))
        n_chunks += 1
    wall = time.perf_counter() - t0
    text = "".join(full)
    toks = _approx_tokens(text)
    gen_time = max(wall - ttft, 1e-6)
    return {
        "ttft": ttft,
        "tps": toks / gen_time,
        "wall": wall,
        "tokens": toks,
        "n_chunks": n_chunks,
    }


def _run_once(think: bool | None) -> dict:
    t0 = time.perf_counter()
    msg = loop._chat_once(MESSAGES, TOOLS, None, think=think)
    wall = time.perf_counter() - t0
    text = msg.get("content", "")
    toks = _approx_tokens(text)
    return {"ttft": wall, "tps": toks / wall, "wall": wall, "tokens": toks, "n_chunks": 1}


def _med(vals: list[float]) -> float:
    return statistics.median(vals)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stream", action="store_true")
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--turns", type=int, default=3)
    a = ap.parse_args()
    mode = _run_stream if (a.stream or not a.once) else _run_once
    tag = "stream" if (a.stream or not a.once) else "once"

    print(f"模型: {settings.ollama_model}   keep_alive={settings.ollama_keep_alive}")
    print(f"提示: {MESSAGES[0]['content'][:34]}…")
    print(f"层: loop._chat_{tag}(直打 /api/chat)    轮数×2 分支 = {a.turns}×2")

    rows: dict[bool | None, list[dict]] = {None: [], True: []}
    for think in (None, True):
        for _ in range(a.turns):
            try:
                rows[think].append(mode(think))
            except Exception as e:  # noqa: BLE001
                print(f"  分支 think={think} 第{_+1}轮失败: {e}")
                rows[think].append(None)
        rows[think] = [r for r in rows[think] if r]

    def _fmt(rows, key):
        return [round(r[key], 1) for r in rows]

    def _row(think_label, data):
        if not data:
            return f"{think_label:>8}: (无有效轮)"
        return (
            f"{think_label:>8}: "
            f"TTFT {_med([r['ttft'] for r in data]):6.2f}s "
            f"tok/s {_med([r['tps'] for r in data]):6.1f} "
            f"{'总'}{_med([r['wall'] for r in data]):6.2f}s "
            f"tok {int(_med([r['tokens'] for r in data]))}"
        )

    print("-" * 78)
    print(_row("关(默认)", rows[None]))
    print(_row("开(think)", rows[True]))
    print("-" * 78)
    for label, off, on in (
        ("TTFT 中位(s)", _med([r["ttft"] for r in rows[None]]), _med([r["ttft"] for r in rows[True]])),
        ("tok/s 中位", _med([r["tps"] for r in rows[None]]), _med([r["tps"] for r in rows[True]])),
        ("总墙钟中位(s)", _med([r["wall"] for r in rows[None]]), _med([r["wall"] for r in rows[True]])),
        ("总token中位", _med([r["tokens"] for r in rows[None]]), _med([r["tokens"] for r in rows[True]])),
    ):
        delta = f"{on - off:+.1f}"
        print(f"  {label:<14} 关={off:7.1f}  开={on:7.1f}  Δ={delta:>7}")


if __name__ == "__main__":
    main()
