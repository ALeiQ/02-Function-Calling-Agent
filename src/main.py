from __future__ import annotations

import typer
from rich.console import Console

app = typer.Typer(help="Function-Calling Agent")
console = Console()


@app.command()
def chat(message: str = typer.Argument(..., help="Question to ask the agent")):
    """Ask the agent once (full multi-turn tool loop)."""
    from src.agent.loop import chat as run

    with console.status("[bold blue]Agent is thinking..."):
        result = run(message)
    console.print(result)


@app.command()
def repl():
    """Start an interactive chat session."""
    raise NotImplementedError("TODO(milestone 2): interactive REPL.")


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