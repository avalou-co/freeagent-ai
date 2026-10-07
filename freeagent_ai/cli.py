import typer

from .client import call, login as client_login, token_expiry

app = typer.Typer(help="FreeAgent API helper.", no_args_is_help=True, add_completion=False)


def _expiry_text():
    exp = token_expiry()
    return f"access token expires {exp.isoformat(timespec='seconds')}" if exp else "access token expiry unknown"


@app.command()
def login():
    """Open the approve page in the browser; the user logs in and clicks Approve."""
    if not client_login():
        typer.echo("Login did not complete.", err=True)
        raise typer.Exit(1)
    typer.echo(f"Logged in; credentials saved ({_expiry_text()}).")


@app.command()
def status():
    """Check the stored credentials work. Prints nothing secret."""
    user = call("GET", "users/me")["user"]["url"]
    typer.echo(f"ok: {user} ({_expiry_text()})")


def main():
    app()


if __name__ == "__main__":
    main()
