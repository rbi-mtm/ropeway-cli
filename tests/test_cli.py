#
# Copyright (c) 2026 bernik86.
#
# This file is part of ropeway-cli
# (see https://github.com/bernik86/ropeway-cli).
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.
#

from __future__ import annotations

from pathlib import Path
from typing import Any

from click.testing import CliRunner
from click.testing import Result
from pytest_mock import MockerFixture

import ropeway_cli.lib.cli
from ropeway_cli.lib.cli import cli

# --- Helper to reduce boilerplate ---


def _invoke(
    mocker: MockerFixture,
    mock_conn: Any,
    args: list[str],
    host_conf: dict[str, str] | None = None,
) -> Result:
    """Invoke the CLI with mocked connection and host config."""
    mocker.patch("ropeway_cli.lib.cli.pathlib.Path")
    ropeway_cli.lib.cli.pathlib.Path.return_value.exists.return_value = True
    mocker.patch("ropeway_cli.lib.cli.fabric.Connection", return_value=mock_conn)
    if host_conf is None:
        host_conf = {
            "local_base_path": "/local",
            "remote_base_path": "/remote",
            "hostname": "myhost",
        }
    mocker.patch("ropeway_cli.lib.cli.actions_local.load_host", return_value=host_conf)
    runner = CliRunner()
    return runner.invoke(cli, ["-H", "myhost", *args])


class TestCliHelp:
    def test_no_subcommand_shows_help(self, mocker: MockerFixture) -> None:
        mocker.patch("ropeway_cli.lib.cli.pathlib.Path")
        ropeway_cli.lib.cli.pathlib.Path.return_value.exists.return_value = True
        mocker.patch("ropeway_cli.lib.cli.actions_local.load_host")
        mocker.patch("ropeway_cli.lib.cli.fabric.Connection")
        runner = CliRunner()
        result: Result = runner.invoke(cli, ["-H", "myhost"])
        assert result.exit_code == 0
        assert "ropeway-cli: Remote file operations over SSH" in result.output

    def test_missing_hosts_file(self, mocker: MockerFixture) -> None:
        """When HOST_CONFIG does not exist, an error is shown and the CLI returns early."""
        mocker.patch("ropeway_cli.lib.cli.pathlib.Path")
        ropeway_cli.lib.cli.pathlib.Path.return_value.exists.return_value = False
        mock_load = mocker.patch("ropeway_cli.lib.cli.actions_local.load_host")
        mock_conn_cls = mocker.patch("ropeway_cli.lib.cli.fabric.Connection")
        runner = CliRunner()
        result: Result = runner.invoke(cli, ["-H", "myhost"])
        assert result.exit_code == 0
        assert "does not exist" in result.output
        mock_load.assert_not_called()
        mock_conn_cls.assert_not_called()


class TestLsCommand:
    def test_ls_command(self, mocker: MockerFixture, mock_conn: Any) -> None:
        mocker.patch("ropeway_cli.lib.cli.pathlib.Path")
        ropeway_cli.lib.cli.pathlib.Path.return_value.exists.return_value = True
        mocker.patch("ropeway_cli.lib.cli.fabric.Connection", return_value=mock_conn)
        mocker.patch(
            "ropeway_cli.lib.cli.actions_local.load_host",
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

    def test_ls_custom_args(self, mocker: MockerFixture, mock_conn: Any) -> None:
        """ls --args forwards custom arguments."""
        mock_ls = mocker.patch("ropeway_cli.lib.cli.actions_remote.ls")
        result = _invoke(mocker, mock_conn, ["ls", "--args", "-lt", "."])
        assert result.exit_code == 0
        assert mock_ls.call_args[0][3] == "-lt"  # ls_args

    def test_ls_default_path(self, mocker: MockerFixture, mock_conn: Any) -> None:
        """ls with no path argument defaults to '.'."""
        mock_ls = mocker.patch("ropeway_cli.lib.cli.actions_remote.ls")
        result = _invoke(mocker, mock_conn, ["ls"])
        assert result.exit_code == 0
        assert mock_ls.call_args[0][1] == "."  # path

    def test_ls_value_error(self, mocker: MockerFixture, mock_conn: Any) -> None:
        """ls catches ValueError and prints styled error."""
        mocker.patch(
            "ropeway_cli.lib.cli.actions_remote.ls",
            side_effect=ValueError(
                "WARNING: command 'ls -lAh /bad/path' terminated with exit code 2!"
                " Please check output of command carefully!"
            ),
        )
        result = _invoke(mocker, mock_conn, ["ls", "/bad/path"])
        assert result.exit_code == 0
        assert "terminated with exit code 2" in result.output


class TestPutCommand:
    def test_put_command(self, mocker: MockerFixture, mock_conn: Any, tmp_path: Path) -> None:
        mocker.patch("ropeway_cli.lib.cli.pathlib.Path")
        ropeway_cli.lib.cli.pathlib.Path.return_value.exists.return_value = True
        mocker.patch("ropeway_cli.lib.cli.fabric.Connection", return_value=mock_conn)
        mocker.patch(
            "ropeway_cli.lib.cli.actions_local.load_host",
            return_value={
                "local_base_path": "/local",
                "remote_base_path": "/remote",
                "hostname": "myhost",
            },
        )
        src = tmp_path / "test.txt"
        src.write_text("content")
        mocker.patch(
            "ropeway_cli.lib.cli.actions_local.construct_local_path",
            return_value=src,
        )
        mock_remote_put = mocker.patch("ropeway_cli.lib.cli.actions_remote.remote_put")
        runner = CliRunner()
        result = runner.invoke(cli, ["-H", "myhost", "put", "test.txt"])
        assert result.exit_code == 0
        mock_remote_put.assert_called_once()

    def test_put_without_overwrite_prompts(self, mocker: MockerFixture, mock_conn: Any) -> None:
        """put without --overwrite passes confirm_overwrite=True."""
        mocker.patch(
            "ropeway_cli.lib.cli.actions_local.construct_local_path", return_value="/local/file.txt"
        )
        mock_put = mocker.patch("ropeway_cli.lib.cli.actions_remote.remote_put")
        result = _invoke(mocker, mock_conn, ["put", "file.txt"])
        assert result.exit_code == 0
        assert mock_put.call_args.kwargs["confirm_overwrite"] is True

    def test_put_with_overwrite_skips_prompt(self, mocker: MockerFixture, mock_conn: Any) -> None:
        """put --overwrite passes confirm_overwrite=False."""
        mocker.patch(
            "ropeway_cli.lib.cli.actions_local.construct_local_path", return_value="/local/file.txt"
        )
        mock_put = mocker.patch("ropeway_cli.lib.cli.actions_remote.remote_put")
        result = _invoke(mocker, mock_conn, ["put", "--overwrite", "file.txt"])
        assert result.exit_code == 0
        assert mock_put.call_args.kwargs["confirm_overwrite"] is False


class TestFindCommand:
    def test_find_command(self, mocker: MockerFixture, mock_conn: Any) -> None:
        mock_find = mocker.patch(
            "ropeway_cli.lib.cli.actions_remote.find",
            return_value=["file1.py", "file2.py"],
        )
        result = _invoke(mocker, mock_conn, ["find", "*.py"])
        assert result.exit_code == 0
        mock_find.assert_called_once_with(mock_conn, mock_find.call_args[0][1], "fd", "", "*.py")

    def test_find_no_results(self, mocker: MockerFixture, mock_conn: Any) -> None:
        mocker.patch("ropeway_cli.lib.cli.actions_remote.find", return_value=None)
        result = _invoke(mocker, mock_conn, ["find", "*.py"])
        assert result.exit_code == 0
        assert "No files found!" in result.output

    def test_find_full_path(self, mocker: MockerFixture, mock_conn: Any) -> None:
        """find --full-path resolves each result via realpath."""
        mocker.patch(
            "ropeway_cli.lib.cli.actions_remote.find",
            return_value=["file1.py", "file2.py"],
        )
        mock_realpath = mocker.patch(
            "ropeway_cli.lib.cli.actions_remote.realpath",
            side_effect=["/remote/file1.py", "/remote/file2.py"],
        )
        result = _invoke(mocker, mock_conn, ["find", "--full-path", "*.py"])
        assert result.exit_code == 0
        assert mock_realpath.call_count == 2
        assert "/remote/file1.py" in result.output

    def test_find_show_type(self, mocker: MockerFixture, mock_conn: Any) -> None:
        """find --show-type prefixes each result with file type."""
        mocker.patch(
            "ropeway_cli.lib.cli.actions_remote.find",
            return_value=["file1.py"],
        )
        mocker.patch(
            "ropeway_cli.lib.cli.actions_remote._get_file_type",
            return_value="regular file",
        )
        mocker.patch(
            "ropeway_cli.lib.cli.actions_remote._construct_path", return_value="/remote/file1.py"
        )
        result = _invoke(mocker, mock_conn, ["find", "--show-type", "*.py"])
        assert result.exit_code == 0
        assert "regular file" in result.output
        assert "file1.py" in result.output

    def test_find_skips_empty_strings(self, mocker: MockerFixture, mock_conn: Any) -> None:
        """find skips empty strings in results list."""
        mocker.patch(
            "ropeway_cli.lib.cli.actions_remote.find",
            return_value=["file1.py", "", "file2.py"],
        )
        result = _invoke(mocker, mock_conn, ["find", "*.py"])
        assert result.exit_code == 0
        lines = [l for l in result.output.splitlines() if l.strip()]
        assert len(lines) == 2

    def test_find_full_path_and_show_type(self, mocker: MockerFixture, mock_conn: Any) -> None:
        """find --full-path --show-type uses realpath (full-path takes precedence)."""
        mocker.patch(
            "ropeway_cli.lib.cli.actions_remote.find",
            return_value=["file1.py"],
        )
        mock_realpath = mocker.patch(
            "ropeway_cli.lib.cli.actions_remote.realpath",
            return_value="/remote/file1.py",
        )
        mocker.patch("ropeway_cli.lib.cli.actions_remote._get_file_type", return_value="regular file")
        mocker.patch(
            "ropeway_cli.lib.cli.actions_remote._construct_path", return_value="/remote/file1.py"
        )
        result = _invoke(mocker, mock_conn, ["find", "--full-path", "--show-type", "*.py"])
        assert result.exit_code == 0
        mock_realpath.assert_called_once()
        assert "/remote/file1.py" in result.output

    def test_find_custom_use_and_args(self, mocker: MockerFixture, mock_conn: Any) -> None:
        """find --use and --args are forwarded."""
        mock_find = mocker.patch(
            "ropeway_cli.lib.cli.actions_remote.find",
            return_value=None,
        )
        result = _invoke(mocker, mock_conn, ["find", "--use", "find", "--args", "-name", "*.py"])
        assert result.exit_code == 0
        mock_find.assert_called_once_with(
            mock_conn, mock_find.call_args[0][1], "find", "-name", "*.py"
        )


class TestMkdirCommand:
    def test_mkdir_command(self, mocker: MockerFixture, mock_conn: Any) -> None:
        mock_mkdir = mocker.patch("ropeway_cli.lib.cli.actions_remote.mkdir")
        result = _invoke(mocker, mock_conn, ["mkdir", "/remote/path"])
        assert result.exit_code == 0
        mock_mkdir.assert_called_once_with(mock_conn, mock_mkdir.call_args[0][1], "/remote/path")

    def test_mkdir_value_error(self, mocker: MockerFixture, mock_conn: Any) -> None:
        """mkdir catches ValueError and prints styled error."""
        mocker.patch(
            "ropeway_cli.lib.cli.actions_remote.mkdir",
            side_effect=ValueError(
                "WARNING: command 'mkdir -p /restricted/path' terminated with exit code 1!"
                " Please check output of command carefully!"
            ),
        )
        result = _invoke(mocker, mock_conn, ["mkdir", "/restricted/path"])
        assert result.exit_code == 0
        assert "terminated with exit code 1" in result.output


class TestRealpathCommand:
    def test_realpath_command(self, mocker: MockerFixture, mock_conn: Any) -> None:
        mocker.patch("ropeway_cli.lib.cli.pathlib.Path")
        ropeway_cli.lib.cli.pathlib.Path.return_value.exists.return_value = True
        mocker.patch("ropeway_cli.lib.cli.fabric.Connection", return_value=mock_conn)
        mocker.patch(
            "ropeway_cli.lib.cli.actions_local.load_host",
            return_value={
                "local_base_path": "/local/path",
                "remote_base_path": "/remote/path",
                "hostname": "myhost",
            },
        )
        mocker.patch("ropeway_cli.lib.actions_remote.os.path.realpath", side_effect=lambda x: x)
        runner = CliRunner()
        result: Result = runner.invoke(cli, ["-H", "myhost", "realpath", "/local/path"])
        assert result.exit_code == 0
        assert "/remote/path" in result.output

    def test_realpath_show_type(self, mocker: MockerFixture, mock_conn: Any) -> None:
        """realpath --show-type includes file type in output."""
        mocker.patch("ropeway_cli.lib.cli.pathlib.Path")
        ropeway_cli.lib.cli.pathlib.Path.return_value.exists.return_value = True
        mocker.patch(
            "ropeway_cli.lib.actions_remote.os.path.realpath",
            side_effect=lambda x: x,
        )
        result = _invoke(mocker, mock_conn, ["realpath", "--show-type", "/local/path"])
        assert result.exit_code == 0


class TestDeleteCommand:
    def test_delete_command(self, mocker: MockerFixture, mock_conn: Any) -> None:
        mocker.patch("ropeway_cli.lib.cli.pathlib.Path")
        ropeway_cli.lib.cli.pathlib.Path.return_value.exists.return_value = True
        mocker.patch("ropeway_cli.lib.cli.fabric.Connection", return_value=mock_conn)
        mocker.patch(
            "ropeway_cli.lib.cli.actions_local.load_host",
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

    def test_delete_value_error(self, mocker: MockerFixture, mock_conn: Any) -> None:
        """delete catches ValueError and prints styled error."""
        mocker.patch(
            "ropeway_cli.lib.cli.actions_remote.delete_file",
            side_effect=ValueError("ERROR: Path is not a file or link! Cannot delete it!"),
        )
        result = _invoke(mocker, mock_conn, ["delete", "/remote/dir"])
        assert result.exit_code == 0
        assert "Path is not a file or link! Cannot delete it!" in result.output


class TestRunCommand:
    def test_run_command(self, mocker: MockerFixture, mock_conn: Any) -> None:
        mock_run = mocker.patch("ropeway_cli.lib.cli.actions_remote.run")
        result = _invoke(mocker, mock_conn, ["run", "echo hello"])
        assert result.exit_code == 0
        mock_run.assert_called_once_with(mock_conn, mock_run.call_args[0][1], "echo hello", ".")

    def test_run_list_aliases(self, mocker: MockerFixture, mock_conn: Any) -> None:
        mocker.patch("ropeway_cli.lib.cli.pathlib.Path")
        ropeway_cli.lib.cli.pathlib.Path.return_value.exists.return_value = True
        mocker.patch("ropeway_cli.lib.cli.fabric.Connection", return_value=mock_conn)
        mocker.patch(
            "ropeway_cli.lib.cli.actions_local.load_host",
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

    def test_run_value_error(self, mocker: MockerFixture, mock_conn: Any) -> None:
        """run catches ValueError and prints styled error."""
        mock_conn.run.return_value.stdout = "directory\n"
        mocker.patch(
            "ropeway_cli.lib.cli.actions_remote.run",
            side_effect=ValueError(
                "ERROR: Directory /bad does not exist on remote host! Cannot run: echo hi!"
            ),
        )
        result = _invoke(mocker, mock_conn, ["run", "echo hi"])
        assert result.exit_code == 0
        assert "Directory /bad does not exist on remote host" in result.output

    def test_run_with_directory(self, mocker: MockerFixture, mock_conn: Any) -> None:
        """run -D specifies the remote working directory."""
        mock_conn.run.return_value.stdout = "directory\n"
        mock_run = mocker.patch("ropeway_cli.lib.cli.actions_remote.run")
        result = _invoke(mocker, mock_conn, ["run", "-D", "/custom/dir", "echo hi"])
        assert result.exit_code == 0
        assert mock_run.call_args[0][3] == "/custom/dir"  # directory

    def test_run_no_aliases(self, mocker: MockerFixture, mock_conn: Any) -> None:
        """run with no command and no @-prefixed keys prints nothing."""
        mocker.patch("ropeway_cli.lib.cli.pathlib.Path")
        ropeway_cli.lib.cli.pathlib.Path.return_value.exists.return_value = True
        mocker.patch(
            "ropeway_cli.lib.cli.actions_local.load_host",
            return_value={
                "local_base_path": "/local",
                "remote_base_path": "/remote",
                "hostname": "myhost",
            },
        )
        mocker.patch("ropeway_cli.lib.cli.fabric.Connection", return_value=mock_conn)
        runner = CliRunner()
        result: Result = runner.invoke(cli, ["-H", "myhost", "run"])
        assert result.exit_code == 0
        assert result.output.strip() == ""

    def test_run_list_multiple_aliases(self, mocker: MockerFixture, mock_conn: Any) -> None:
        """run with no cmd lists all @-prefixed aliases, skipping non-alias keys."""
        mocker.patch("ropeway_cli.lib.cli.pathlib.Path")
        ropeway_cli.lib.cli.pathlib.Path.return_value.exists.return_value = True
        mocker.patch(
            "ropeway_cli.lib.cli.actions_local.load_host",
            return_value={
                "local_base_path": "/local",
                "remote_base_path": "/remote",
                "hostname": "myhost",
                "@build": "make",
                "@test": "pytest",
                "regular_key": "val",
            },
        )
        mocker.patch("ropeway_cli.lib.cli.fabric.Connection", return_value=mock_conn)
        runner = CliRunner()
        result: Result = runner.invoke(cli, ["-H", "myhost", "run"])
        assert result.exit_code == 0
        assert "@build" in result.output
        assert "@test" in result.output
        assert "regular_key" not in result.output


class TestViewCommand:
    def test_view_no_flags(self, mocker: MockerFixture, mock_conn: Any, tmp_path: Path) -> None:
        """Default view: fetches, edits, does not write back."""
        tmp = tmp_path / "view_tmp.txt"
        mocker.patch("ropeway_cli.lib.cli.actions_local.determine_suffix", return_value=".txt")
        mocker.patch("ropeway_cli.lib.cli.actions_local.create_tmp_file", return_value=tmp)
        mock_edit = mocker.patch("ropeway_cli.lib.cli.actions_local.edit_file")
        mock_fetch = mocker.patch("ropeway_cli.lib.cli.actions_remote.remote_fetch")
        mock_put = mocker.patch("ropeway_cli.lib.cli.actions_remote.remote_put")
        mock_remove = mocker.patch("ropeway_cli.lib.cli.actions_local.remove_tmp_file")
        result = _invoke(mocker, mock_conn, ["view", "file.txt"])
        assert result.exit_code == 0
        mock_fetch.assert_called_once()
        mock_edit.assert_called_once_with(tmp, None)
        mock_put.assert_not_called()
        mock_remove.assert_called_once_with(tmp)

    def test_view_with_write(self, mocker: MockerFixture, mock_conn: Any, tmp_path: Path) -> None:
        """--write flag: fetches, edits, writes back."""
        tmp = tmp_path / "view_tmp.txt"
        mocker.patch("ropeway_cli.lib.cli.actions_local.determine_suffix", return_value=".txt")
        mocker.patch("ropeway_cli.lib.cli.actions_local.create_tmp_file", return_value=tmp)
        mocker.patch("ropeway_cli.lib.cli.actions_local.edit_file")
        mocker.patch("ropeway_cli.lib.cli.actions_remote.remote_fetch")
        mock_put = mocker.patch("ropeway_cli.lib.cli.actions_remote.remote_put")
        mock_remove = mocker.patch("ropeway_cli.lib.cli.actions_local.remove_tmp_file")
        result = _invoke(mocker, mock_conn, ["view", "--write", "file.txt"])
        assert result.exit_code == 0
        mock_put.assert_called_once()
        mock_remove.assert_called_once_with(tmp)

    def test_view_with_new(self, mocker: MockerFixture, mock_conn: Any, tmp_path: Path) -> None:
        """--new flag: skips fetch, edits, writes back."""
        tmp = tmp_path / "view_tmp.txt"
        mocker.patch("ropeway_cli.lib.cli.actions_local.determine_suffix", return_value=".txt")
        mocker.patch("ropeway_cli.lib.cli.actions_local.create_tmp_file", return_value=tmp)
        mocker.patch("ropeway_cli.lib.cli.actions_local.edit_file")
        mock_fetch = mocker.patch("ropeway_cli.lib.cli.actions_remote.remote_fetch")
        mock_put = mocker.patch("ropeway_cli.lib.cli.actions_remote.remote_put")
        mock_remove = mocker.patch("ropeway_cli.lib.cli.actions_local.remove_tmp_file")
        result = _invoke(mocker, mock_conn, ["view", "--new", "file.txt"])
        assert result.exit_code == 0
        mock_fetch.assert_not_called()
        mock_put.assert_called_once()
        mock_remove.assert_called_once_with(tmp)

    def test_view_file_not_found(
        self, mocker: MockerFixture, mock_conn: Any, tmp_path: Path
    ) -> None:
        """FileNotFoundError on fetch prints error and returns early."""
        tmp = tmp_path / "view_tmp.txt"
        mocker.patch("ropeway_cli.lib.cli.actions_local.determine_suffix", return_value=".txt")
        mocker.patch("ropeway_cli.lib.cli.actions_local.create_tmp_file", return_value=tmp)
        mocker.patch("ropeway_cli.lib.cli.actions_local.edit_file")
        mocker.patch(
            "ropeway_cli.lib.cli.actions_remote.remote_fetch",
            side_effect=FileNotFoundError("No such file: remote.txt"),
        )
        mock_put = mocker.patch("ropeway_cli.lib.cli.actions_remote.remote_put")
        mock_remove = mocker.patch("ropeway_cli.lib.cli.actions_local.remove_tmp_file")
        result = _invoke(mocker, mock_conn, ["view", "remote.txt"])
        assert result.exit_code == 0
        assert "No such file: remote.txt" in result.output
        mock_put.assert_not_called()
        mock_remove.assert_called_once()

    def test_view_with_editor(self, mocker: MockerFixture, mock_conn: Any, tmp_path: Path) -> None:
        """--editor option is forwarded to edit_file."""
        tmp = tmp_path / "view_tmp.txt"
        mocker.patch("ropeway_cli.lib.cli.actions_local.determine_suffix", return_value=".txt")
        mocker.patch("ropeway_cli.lib.cli.actions_local.create_tmp_file", return_value=tmp)
        mock_edit = mocker.patch("ropeway_cli.lib.cli.actions_local.edit_file")
        mocker.patch("ropeway_cli.lib.cli.actions_remote.remote_fetch")
        mocker.patch("ropeway_cli.lib.cli.actions_local.remove_tmp_file")
        result = _invoke(mocker, mock_conn, ["view", "--editor", "vim", "file.txt"])
        assert result.exit_code == 0
        mock_edit.assert_called_once_with(tmp, "vim")


class TestGetCommand:
    def test_get_command(self, mocker: MockerFixture, mock_conn: Any) -> None:
        """get downloads a remote file to a local path."""
        mocker.patch(
            "ropeway_cli.lib.cli.actions_local.construct_local_path", return_value="/local/file.txt"
        )
        mock_fetch = mocker.patch("ropeway_cli.lib.cli.actions_remote.remote_fetch")
        result = _invoke(mocker, mock_conn, ["get", "file.txt"])
        assert result.exit_code == 0
        mock_fetch.assert_called_once()

    def test_get_without_overwrite_prompts(self, mocker: MockerFixture, mock_conn: Any) -> None:
        """get without --overwrite passes confirm_overwrite=True."""
        mocker.patch(
            "ropeway_cli.lib.cli.actions_local.construct_local_path", return_value="/local/file.txt"
        )
        mock_fetch = mocker.patch("ropeway_cli.lib.cli.actions_remote.remote_fetch")
        result = _invoke(mocker, mock_conn, ["get", "file.txt"])
        assert result.exit_code == 0
        assert mock_fetch.call_args.kwargs["confirm_overwrite"] is True

    def test_get_with_overwrite_skips_prompt(self, mocker: MockerFixture, mock_conn: Any) -> None:
        """get --overwrite passes confirm_overwrite=False."""
        mocker.patch(
            "ropeway_cli.lib.cli.actions_local.construct_local_path", return_value="/local/file.txt"
        )
        mock_fetch = mocker.patch("ropeway_cli.lib.cli.actions_remote.remote_fetch")
        result = _invoke(mocker, mock_conn, ["get", "--overwrite", "file.txt"])
        assert result.exit_code == 0
        assert mock_fetch.call_args.kwargs["confirm_overwrite"] is False


class TestCpCommand:
    def test_cp_command(self, mocker: MockerFixture, mock_conn: Any) -> None:
        """cp copies a file on the remote host."""
        mock_copy = mocker.patch("ropeway_cli.lib.cli.actions_remote.copy")
        result = _invoke(mocker, mock_conn, ["cp", "src.txt", "dst.txt"])
        assert result.exit_code == 0
        mock_copy.assert_called_once()

    def test_cp_value_error(self, mocker: MockerFixture, mock_conn: Any) -> None:
        """cp catches ValueError and prints styled error."""
        mocker.patch(
            "ropeway_cli.lib.cli.actions_remote.copy",
            side_effect=ValueError(
                "WARNING: command 'cp /remote/missing.txt /remote/dst.txt'"
                " terminated with exit code 1! Please check output of command carefully!"
            ),
        )
        result = _invoke(mocker, mock_conn, ["cp", "missing.txt", "dst.txt"])
        assert result.exit_code == 0
        assert "terminated with exit code 1" in result.output


class TestTailCommand:
    def test_tail_normal(self, mocker: MockerFixture, mock_conn: Any) -> None:
        """tail without -f."""
        mock_tail = mocker.patch("ropeway_cli.lib.cli.actions_remote.tail")
        result = _invoke(mocker, mock_conn, ["tail", "log.txt"])
        assert result.exit_code == 0
        mock_tail.assert_called_once()

    def test_tail_follow(self, mocker: MockerFixture, mock_conn: Any) -> None:
        """tail -f for continuous monitoring."""
        mock_tail = mocker.patch("ropeway_cli.lib.cli.actions_remote.tail")
        result = _invoke(mocker, mock_conn, ["tail", "-f", "log.txt"])
        assert result.exit_code == 0
        args = mock_tail.call_args
        assert args[0][2] is True  # tail_f=True

    def test_tail_value_error(self, mocker: MockerFixture, mock_conn: Any) -> None:
        """tail catches ValueError and prints styled error."""
        mocker.patch(
            "ropeway_cli.lib.cli.actions_remote.tail",
            side_effect=ValueError(
                "WARNING: command 'tail /remote/missing.txt'"
                " terminated with exit code 1! Please check output of command carefully!"
            ),
        )
        result = _invoke(mocker, mock_conn, ["tail", "missing.txt"])
        assert result.exit_code == 0
        assert "terminated with exit code 1" in result.output


class TestDiffCommand:
    def test_diff_identical(self, mocker: MockerFixture, mock_conn: Any) -> None:
        """Exit code 0: files are identical."""
        mocker.patch("ropeway_cli.lib.cli.actions_remote.diff", return_value=0)
        result = _invoke(mocker, mock_conn, ["diff", "a.txt", "b.txt"])
        assert result.exit_code == 0
        assert "Files are identical!" in result.output

    def test_diff_different(self, mocker: MockerFixture, mock_conn: Any) -> None:
        """Exit code 1: files are different."""
        mocker.patch("ropeway_cli.lib.cli.actions_remote.diff", return_value=1)
        result = _invoke(mocker, mock_conn, ["diff", "a.txt", "b.txt"])
        assert result.exit_code == 0
        assert "Files are different!" in result.output

    def test_diff_error(self, mocker: MockerFixture, mock_conn: Any) -> None:
        """Other exit code: error occurred."""
        mocker.patch("ropeway_cli.lib.cli.actions_remote.diff", return_value=2)
        result = _invoke(mocker, mock_conn, ["diff", "a.txt", "b.txt"])
        assert result.exit_code == 0
        assert "Some error occurred!" in result.output

    def test_diff_local_flag(self, mocker: MockerFixture, mock_conn: Any) -> None:
        """--local flag is forwarded to actions_remote.diff."""
        mock_diff = mocker.patch("ropeway_cli.lib.cli.actions_remote.diff", return_value=0)
        result = _invoke(mocker, mock_conn, ["diff", "--local", "a.txt", "b.txt"])
        assert result.exit_code == 0
        assert mock_diff.call_args[0][6] is True  # local=True

    def test_diff_custom_cmd(self, mocker: MockerFixture, mock_conn: Any) -> None:
        """--use flag selects a custom diff command."""
        mock_diff = mocker.patch("ropeway_cli.lib.cli.actions_remote.diff", return_value=0)
        result = _invoke(mocker, mock_conn, ["diff", "--use", "vimdiff", "a.txt", "b.txt"])
        assert result.exit_code == 0
        assert mock_diff.call_args[0][4] == "vimdiff"  # diff_cmd

    def test_diff_custom_args(self, mocker: MockerFixture, mock_conn: Any) -> None:
        """--args flag forwards extra diff arguments."""
        mock_diff = mocker.patch("ropeway_cli.lib.cli.actions_remote.diff", return_value=0)
        result = _invoke(mocker, mock_conn, ["diff", "--args", "-u", "a.txt", "b.txt"])
        assert result.exit_code == 0
        assert mock_diff.call_args[0][5] == "-u"  # diff_args


class TestSyncCwdCommand:
    def test_sync_push(self, mocker: MockerFixture, mock_conn: Any) -> None:
        """Default push: local to remote."""
        mock_sync = mocker.patch("ropeway_cli.lib.cli.actions_remote.sync_cwd")
        result = _invoke(mocker, mock_conn, ["sync-cwd"])
        assert result.exit_code == 0
        mock_sync.assert_called_once()
        assert mock_sync.call_args[0][3] is False  # from_remote=False

    def test_sync_pull(self, mocker: MockerFixture, mock_conn: Any) -> None:
        """--from flag: pull from remote."""
        mock_sync = mocker.patch("ropeway_cli.lib.cli.actions_remote.sync_cwd")
        result = _invoke(mocker, mock_conn, ["sync-cwd", "--from"])
        assert result.exit_code == 0
        assert mock_sync.call_args[0][3] is True  # from_remote=True

    def test_sync_custom_args(self, mocker: MockerFixture, mock_conn: Any) -> None:
        """Custom --args are forwarded to sync_cwd."""
        mock_sync = mocker.patch("ropeway_cli.lib.cli.actions_remote.sync_cwd")
        result = _invoke(mocker, mock_conn, ["sync-cwd", "--args", "-avz"])
        assert result.exit_code == 0
        assert mock_sync.call_args[0][2] == "-avz"  # rsync_args


class TestCompressCommand:
    def test_compress_basic(self, mocker: MockerFixture, mock_conn: Any) -> None:
        """Basic compress finds files and calls compress."""
        mocker.patch(
            "ropeway_cli.lib.cli.actions_remote.find",
            return_value=["file1.dat", "file2.dat"],
        )
        mock_compress = mocker.patch("ropeway_cli.lib.cli.actions_remote.compress")
        result = _invoke(mocker, mock_conn, ["compress"])
        assert result.exit_code == 0
        mock_compress.assert_called_once()

    def test_compress_only_cwd(self, mocker: MockerFixture, mock_conn: Any) -> None:
        """--only-cwd adds -maxdepth 1 to find args."""
        mock_find = mocker.patch("ropeway_cli.lib.cli.actions_remote.find", return_value=None)
        result = _invoke(mocker, mock_conn, ["compress", "--only-cwd"])
        assert result.exit_code == 0
        find_args = mock_find.call_args[0][3]
        assert "-maxdepth 1" in find_args

    def test_compress_no_files(self, mocker: MockerFixture, mock_conn: Any) -> None:
        """No files found: compress is not called."""
        mocker.patch("ropeway_cli.lib.cli.actions_remote.find", return_value=None)
        mock_compress = mocker.patch("ropeway_cli.lib.cli.actions_remote.compress")
        result = _invoke(mocker, mock_conn, ["compress"])
        assert result.exit_code == 0
        mock_compress.assert_not_called()

    def test_compress_exclude_files_in_dir(self, mocker: MockerFixture, mock_conn: Any) -> None:
        """Exclude patterns ending with '/' use -wholename instead of -name."""
        mock_find = mocker.patch("ropeway_cli.lib.cli.actions_remote.find", return_value=None)
        result = _invoke(mocker, mock_conn, ["compress", "--exclude", "*/Input/*"])
        assert result.exit_code == 0
        find_args = mock_find.call_args[0][3]
        assert "-wholename" in find_args

    def test_compress_custom_use(self, mocker: MockerFixture, mock_conn: Any) -> None:
        """--use flag selects a custom compressor."""
        mocker.patch(
            "ropeway_cli.lib.cli.actions_remote.find",
            return_value=["file1.dat"],
        )
        mock_compress = mocker.patch("ropeway_cli.lib.cli.actions_remote.compress")
        result = _invoke(mocker, mock_conn, ["compress", "--use", "gzip"])
        assert result.exit_code == 0
        mock_compress.assert_called_once()
        assert mock_compress.call_args[0][2] == "gzip"  # use

    def test_compress_empty_exclude(self, mocker: MockerFixture, mock_conn: Any) -> None:
        """Empty --exclude produces no exclusion flags."""
        mock_find = mocker.patch("ropeway_cli.lib.cli.actions_remote.find", return_value=None)
        result = _invoke(mocker, mock_conn, ["compress", "--exclude", ""])
        assert result.exit_code == 0
        find_args = mock_find.call_args[0][3]
        assert "-name" not in find_args
        assert "-wholename" not in find_args

    def test_compress_deduplicates_files(self, mocker: MockerFixture, mock_conn: Any) -> None:
        """Duplicate filenames from find are deduplicated via set()."""
        mocker.patch(
            "ropeway_cli.lib.cli.actions_remote.find",
            return_value=["file.dat", "file.dat", "other.dat"],
        )
        mock_compress = mocker.patch("ropeway_cli.lib.cli.actions_remote.compress")
        result = _invoke(mocker, mock_conn, ["compress"])
        assert result.exit_code == 0
        passed_files = mock_compress.call_args[0][3]
        assert len(passed_files) == 2

    def test_compress_mixed_exclude_patterns(self, mocker: MockerFixture, mock_conn: Any) -> None:
        """Mix of file and directory exclude patterns produces correct -name and -wholename flags."""
        mock_find = mocker.patch("ropeway_cli.lib.cli.actions_remote.find", return_value=None)
        result = _invoke(mocker, mock_conn, ["compress", "--exclude", "*png */Input/* *jpg"])
        assert result.exit_code == 0
        find_args = mock_find.call_args[0][3]
        assert "-name '*png'" in find_args
        assert "-wholename " in find_args
        assert "'*/Input/*'" in find_args
        assert "-name '*jpg'" in find_args

    def test_compress_value_error(self, mocker: MockerFixture, mock_conn: Any) -> None:
        """compress catches ValueError and prints styled error."""
        mocker.patch(
            "ropeway_cli.lib.cli.actions_remote.find",
            return_value=["file1.dat"],
        )
        mocker.patch(
            "ropeway_cli.lib.cli.actions_remote.compress",
            side_effect=ValueError(
                "WARNING: command 'bzip2 -v file1.dat'"
                " terminated with exit code 1! Please check output of command carefully!"
            ),
        )
        result = _invoke(mocker, mock_conn, ["compress"])
        assert result.exit_code == 0
        assert "terminated with exit code 1" in result.output
