import typer
from dotenv import load_dotenv

from src.cli.analysis import analysis_app
from src.cli.data import data_app
from src.cli.diagnostics import doctor
from src.cli.valuation import valuation_app


load_dotenv()

app = typer.Typer()
app.add_typer(data_app, name="data")
app.add_typer(valuation_app, name="valuation")
app.add_typer(analysis_app, name="analysis")
app.command("doctor")(doctor)


if __name__ == "__main__":
    app()
