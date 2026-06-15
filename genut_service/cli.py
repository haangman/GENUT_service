"""명령행 진입점 (Typer)."""

from __future__ import annotations

import typer

cli = typer.Typer(help="GENUT_service CLI")


@cli.command()
def serve(
    host: str = "127.0.0.1",
    port: int = 8000,
    reload: bool = False,
) -> None:
    """개발/운영용 uvicorn 서버를 띄운다."""
    import uvicorn

    uvicorn.run("genut_service.main:app", host=host, port=port, reload=reload)


def main() -> None:
    """[project.scripts] 진입점."""
    cli()


if __name__ == "__main__":
    main()
