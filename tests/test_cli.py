"""CLI: serve 서브커맨드가 인식되는지 확인."""

from __future__ import annotations

from typer.testing import CliRunner

from genut_service.cli import cli


def test_serve_is_recognized_subcommand() -> None:
    result = CliRunner().invoke(cli, ["serve", "--help"])
    assert result.exit_code == 0
    assert "host" in result.output.lower()
