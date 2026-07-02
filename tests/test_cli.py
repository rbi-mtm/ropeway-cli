from __future__ import annotations

from pathlib import Path
from typing import Any

from click.testing import CliRunner
from click.testing import Result
from pytest_mock import MockerFixture

from ropes.lib.cli import cli


def test_cli_no_subcommand_shows_help(mocker: MockerFixture) -> None:
    mocker.patch("ropes.lib.cli.actions_local.load_host")
    mocker.patch("ropes.lib.cli.fabric.Connection")
    runner = CliRunner()
    result: Result = runner.invoke(cli, ["-H", "myhost"])
    assert result.exit_code == 0
    assert "ROPES: Remote file OPErations via Ssh" in result.output


def test_ls_command(mocker: MockerFixture, mock_conn: Any) -> None:
    mocker.patch("ropes.lib.cli.fabric.Connection", return_value=mock_conn)
    mocker.patch(
        "ropes.lib.cli.actions_local.load_host",
        return_value={
            "local_base_path": "/local",
            "remote_base_path": "/remote",
            "hostname": "myhost",
        },
    )
    runner = CliRunner()
    result: Result = runner.invoke(cli, ["-H", "myhost", "ls", "."])
    assert result.exit_code == 0
    mock_conn.run.assert_called_once()


def test_put_command(mocker: MockerFixture, mock_conn: Any, tmp_path: Path) -> None:
    mocker.patch("ropes.lib.cli.fabric.Connection", return_value=mock_conn)
    mocker.patch(
        "ropes.lib.cli.actions_local.load_host",
        return_value={
            "local_base_path": "/local",
            "remote_base_path": "/remote",
            "hostname": "myhost",
        },
    )
    src = tmp_path / "test.txt"
    src.write_text("content")
    mocker.patch(
        "ropes.lib.cli.actions_local.construct_local_path",
        return_value=src,
    )
    runner = CliRunner()
    result: Result = runner.invoke(cli, ["-H", "myhost", "put", "."])
    assert result.exit_code == 0
    mock_conn.put.assert_called_once()


def test_find_command(mocker: MockerFixture, mock_conn: Any) -> None:
    mocker.patch("ropes.lib.cli.fabric.Connection", return_value=mock_conn)
    mocker.patch(
        "ropes.lib.cli.actions_local.load_host",
        return_value={
            "local_base_path": "/local",
            "remote_base_path": "/remote",
            "hostname": "myhost",
        },
    )
    mock_conn.run.return_value.stdout = "file1\nfile2\n"
    runner = CliRunner()
    result: Result = runner.invoke(cli, ["-H", "myhost", "find", "*.py"])
    assert result.exit_code == 0


def test_find_no_results(mocker: MockerFixture, mock_conn: Any) -> None:
    mocker.patch("ropes.lib.cli.fabric.Connection", return_value=mock_conn)
    mocker.patch(
        "ropes.lib.cli.actions_local.load_host",
        return_value={
            "local_base_path": "/local",
            "remote_base_path": "/remote",
            "hostname": "myhost",
        },
    )
    mock_conn.run.return_value.stdout = ""
    runner = CliRunner()
    result: Result = runner.invoke(cli, ["-H", "myhost", "find", "*.py"])
    assert result.exit_code == 0
    assert "No files found!" in result.output


def test_mkdir_command(mocker: MockerFixture, mock_conn: Any) -> None:
    mocker.patch("ropes.lib.cli.fabric.Connection", return_value=mock_conn)
    mocker.patch(
        "ropes.lib.cli.actions_local.load_host",
        return_value={
            "local_base_path": "/local",
            "remote_base_path": "/remote",
            "hostname": "myhost",
        },
    )
    runner = CliRunner()
    result: Result = runner.invoke(cli, ["-H", "myhost", "mkdir", "/remote/path"])
    assert result.exit_code == 0


def test_realpath_command(mocker: MockerFixture, mock_conn: Any) -> None:
    mocker.patch("ropes.lib.cli.fabric.Connection", return_value=mock_conn)
    mocker.patch(
        "ropes.lib.cli.actions_local.load_host",
        return_value={
            "local_base_path": "/local/path",
            "remote_base_path": "/remote/path",
            "hostname": "myhost",
        },
    )
    mocker.patch("ropes.lib.actions_remote.os.path.realpath", side_effect=lambda x: x)
    runner = CliRunner()
    result: Result = runner.invoke(cli, ["-H", "myhost", "realpath", "/local/path"])
    assert result.exit_code == 0
    assert "/remote/path" in result.output


def test_delete_command(mocker: MockerFixture, mock_conn: Any) -> None:
    mocker.patch("ropes.lib.cli.fabric.Connection", return_value=mock_conn)
    mocker.patch(
        "ropes.lib.cli.actions_local.load_host",
        return_value={
            "local_base_path": "/local",
            "remote_base_path": "/remote",
            "hostname": "myhost",
        },
    )
    mock_conn.run.return_value.stdout = "regular file\n"
    mocker.patch("builtins.input", return_value="y")
    runner = CliRunner()
    result: Result = runner.invoke(cli, ["-H", "myhost", "delete", "/remote/file.txt"])
    assert result.exit_code == 0


def test_run_command(mocker: MockerFixture, mock_conn: Any) -> None:
    mocker.patch("ropes.lib.cli.fabric.Connection", return_value=mock_conn)
    mocker.patch(
        "ropes.lib.cli.actions_local.load_host",
        return_value={
            "local_base_path": "/local",
            "remote_base_path": "/remote",
            "hostname": "myhost",
        },
    )
    mock_conn.run.return_value.stdout = "directory\n"
    runner = CliRunner()
    result: Result = runner.invoke(cli, ["-H", "myhost", "run", "echo hello"])
    assert result.exit_code == 0


def test_run_list_aliases(mocker: MockerFixture, mock_conn: Any) -> None:
    mocker.patch("ropes.lib.cli.fabric.Connection", return_value=mock_conn)
    mocker.patch(
        "ropes.lib.cli.actions_local.load_host",
        return_value={
            "local_base_path": "/local",
            "remote_base_path": "/remote",
            "hostname": "myhost",
            "@build": "make",
        },
    )
    runner = CliRunner()
    result: Result = runner.invoke(cli, ["-H", "myhost", "run"])
    assert result.exit_code == 0
    assert "@build" in result.output
