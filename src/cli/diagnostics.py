import json

import typer

from src.cli.common import production_safety_report


def doctor():
    """Run production-safety checks without changing investment data."""
    payload = production_safety_report()
    typer.echo(json.dumps(payload))
    if payload["failures"]:
        raise typer.Exit(code=1)
