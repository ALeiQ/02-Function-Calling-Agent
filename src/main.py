from __future__ import annotations

import typer
from rich.console import Console
from rich.panel import Panel

app = typer.Typer(help="Function-Calling Agent")
console = Console()


def _print_answer(result: dict, show_trace: bool = True) -> None:
    if show_trace and result.get("trace"):
        calls = [
            f"[cyan]{entry['tool']}[/cyan] {entry['arguments']} → "
            f"{entry['result'][:300]}{'…' if len(entry['result']) > 300 else ''}"
            for entry in result["trace"]
        ]
        console.print(
            Panel(
                "\n".join(f"  {i + 1}. {call}" for i, call in enumerate(calls)),
                title="工具调用轨迹",
                border_style="dim",
            )
        )
    console.print(f"[bold]回答:[/bold] {result.get('answer', '')}")


@app.command()
def chat(message: str = typer.Argument(..., help="Question to ask the agent")):
    """Ask the agent once (full multi-turn tool loop)."""
    from src.agent.loop import chat as run

    with console.status("[bold blue]Agent 正在思考..."):
        result = run(message)
    _print_answer(result)


@app.command()
def repl():
    """Start an interactive chat session."""
    from src.agent.loop import chat as run
    from src.agent.session import SessionStore

    store = SessionStore()
    session_id = "cli"
    console.print("[bold green]会话开始，输入 /exit 退出，/clear 清空历史。[/bold green]")
    while True:
        try:
            line = input("[bold]you>[/bold] ")
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]再见[/dim]")
            raise typer.Exit(0)
        message = line.strip()
        if not message:
            continue
        if message == "/exit":
            raise typer.Exit(0)
        if message == "/clear":
            store.clear(session_id)
            console.print("[dim]已清空会话历史[/dim]")
            continue
        with console.status("[bold blue]Agent 正在思考..."):
            result = run(message, session_id=session_id, store=store)
        _print_answer(result, show_trace=True)


@app.command()
def serve(
    host: str = "127.0.0.1",
    port: int = 8000,
    reload: bool = False,
):
    """Start the FastAPI server + web UI at http://127.0.0.1:8000."""
    import uvicorn

    uvicorn.run("src.api.app:app", host=host, port=port, reload=reload)


@app.command()
def tools():
    """List all registered tools and their schemas."""
    from src.tools.registry import registry as tools_registry

    for tool in tools_registry():
        console.print(f"[bold green]{tool['function']['name']}[/bold green]")
        console.print(tool["function"]["description"])
        console.print("")


@app.command()
def seed():
    """Create and populate the demo SQLite database."""
    from scripts.seed_db import main as seed_main

    seed_main()


if __name__ == "__main__":
    app()
