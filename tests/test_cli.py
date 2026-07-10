from __future__ import annotations

from pathlib import Path
from typing import Any

from click.testing import CliRunner
from click.testing import Result
from pytest_mock import MockerFixture

from ropes.lib.cli import cli


# --- Helper to reduce boilerplate ---


def _invoke(
    mocker: MockerFixture,
    mock_conn: Any,
    args: list[str],
    host_conf: dict[str, str] | None = None,
) -> Result:
    """Invoke the CLI with mocked connection and host config."""
    mocker.patch("ropes.lib.cli.fabric.Connection", return_value=mock_conn)
    if host_conf is None:
        host_conf = {
            "local_base_path": "/local",
            "remote_base_path": "/remote",
            "hostname": "myhost",
        }
    mocker.patch("ropes.lib.cli.actions_local.load_host", return_value=host_conf)
    runner = CliRunner()
    return runner.invoke(cli, ["-H", "myhost", *args])


class TestCliHelp:
    def test_no_subcommand_shows_help(self, mocker: MockerFixture) -> None:
        mocker.patch("ropes.lib.cli.actions_local.load_host")
        mocker.patch("ropes.lib.cli.fabric.Connection")
        runner = CliRunner()
        result: Result = runner.invoke(cli, ["-H", "myhost"])
        assert result.exit_code == 0
        assert "ROPES: Remote file OPErations via Ssh" in result.output


class TestLsCommand:
    def test_ls_command(self, mocker: MockerFixture, mock_conn: Any) -> None:
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

    def test_ls_custom_args(self, mocker: MockerFixture, mock_conn: Any) -> None:
        """ls --args forwards custom arguments."""
        mock_ls = mocker.patch("ropes.lib.cli.actions_remote.ls")
        result = _invoke(mocker, mock_conn, ["ls", "--args", "-lt", "."])
        assert result.exit_code == 0
        assert mock_ls.call_args[0][3] == "-lt"  # ls_args

    def test_ls_default_path(self, mocker: MockerFixture, mock_conn: Any) -> None:
        """ls with no path argument defaults to '.'."""
        mock_ls = mocker.patch("ropes.lib.cli.actions_remote.ls")
        result = _invoke(mocker, mock_conn, ["ls"])
        assert result.exit_code == 0
        assert mock_ls.call_args[0][1] == "."  # path


class TestPutCommand:
    def test_put_command(
        self, mocker: MockerFixture, mock_conn: Any, tmp_path: Path
    ) -> None:
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
        mock_remote_put = mocker.patch("ropes.lib.cli.actions_remote.remote_put")
        runner = CliRunner()
        result = runner.invoke(cli, ["-H", "myhost", "put", "test.txt"])
        assert result.exit_code == 0
        mock_remote_put.assert_called_once()


class TestFindCommand:
    def test_find_command(self, mocker: MockerFixture, mock_conn: Any) -> None:
        mock_find = mocker.patch(
            "ropes.lib.cli.actions_remote.find",
            return_value=["file1.py", "file2.py"],
        )
        result = _invoke(mocker, mock_conn, ["find", "*.py"])
        assert result.exit_code == 0
        mock_find.assert_called_once_with(mock_conn, mock_find.call_args[0][1], "fd", "", "*.py")

    def test_find_no_results(self, mocker: MockerFixture, mock_conn: Any) -> None:
        mocker.patch("ropes.lib.cli.actions_remote.find", return_value=None)
        result = _invoke(mocker, mock_conn, ["find", "*.py"])
        assert result.exit_code == 0
        assert "No files found!" in result.output

    def test_find_full_path(self, mocker: MockerFixture, mock_conn: Any) -> None:
        """find --full-path resolves each result via realpath."""
        mocker.patch(
            "ropes.lib.cli.actions_remote.find",
            return_value=["file1.py", "file2.py"],
        )
        mock_realpath = mocker.patch(
            "ropes.lib.cli.actions_remote.realpath",
            side_effect=["/remote/file1.py", "/remote/file2.py"],
        )
        result = _invoke(mocker, mock_conn, ["find", "--full-path", "*.py"])
        assert result.exit_code == 0
        assert mock_realpath.call_count == 2
        assert "/remote/file1.py" in result.output

    def test_find_show_type(self, mocker: MockerFixture, mock_conn: Any) -> None:
        """find --show-type prefixes each result with file type."""
        mocker.patch(
            "ropes.lib.cli.actions_remote.find",
            return_value=["file1.py"],
        )
        mocker.patch(
            "ropes.lib.cli.actions_remote._get_file_type",
            return_value="regular file",
        )
        mocker.patch("ropes.lib.cli.actions_remote._construct_path", return_value="/remote/file1.py")
        result = _invoke(mocker, mock_conn, ["find", "--show-type", "*.py"])
        assert result.exit_code == 0
        assert "regular file" in result.output
        assert "file1.py" in result.output

    def test_find_skips_empty_strings(self, mocker: MockerFixture, mock_conn: Any) -> None:
        """find skips empty strings in results list."""
        mocker.patch(
            "ropes.lib.cli.actions_remote.find",
            return_value=["file1.py", "", "file2.py"],
        )
        result = _invoke(mocker, mock_conn, ["find", "*.py"])
        assert result.exit_code == 0
        lines = [l for l in result.output.splitlines() if l.strip()]
        assert len(lines) == 2


class TestMkdirCommand:
    def test_mkdir_command(self, mocker: MockerFixture, mock_conn: Any) -> None:
        mock_mkdir = mocker.patch("ropes.lib.cli.actions_remote.mkdir")
        result = _invoke(mocker, mock_conn, ["mkdir", "/remote/path"])
        assert result.exit_code == 0
        mock_mkdir.assert_called_once_with(mock_conn, mock_mkdir.call_args[0][1], "/remote/path")


class TestRealpathCommand:
    def test_realpath_command(self, mocker: MockerFixture, mock_conn: Any) -> None:
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

    def test_realpath_show_type(self, mocker: MockerFixture, mock_conn: Any) -> None:
        """realpath --show-type includes file type in output."""
        mocker.patch(
            "ropes.lib.actions_remote.os.path.realpath",
            side_effect=lambda x: x,
        )
        result = _invoke(mocker, mock_conn, ["realpath", "--show-type", "/local/path"])
        assert result.exit_code == 0


class TestDeleteCommand:
    def test_delete_command(self, mocker: MockerFixture, mock_conn: Any) -> None:
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


class TestRunCommand:
    def test_run_command(self, mocker: MockerFixture, mock_conn: Any) -> None:
        mock_run = mocker.patch("ropes.lib.cli.actions_remote.run")
        result = _invoke(mocker, mock_conn, ["run", "echo hello"])
        assert result.exit_code == 0
        mock_run.assert_called_once_with(mock_conn, mock_run.call_args[0][1], "echo hello", ".")

    def test_run_list_aliases(self, mocker: MockerFixture, mock_conn: Any) -> None:
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

    def test_run_value_error(self, mocker: MockerFixture, mock_conn: Any) -> None:
        """run catches ValueError and prints styled error."""
        mock_conn.run.return_value.stdout = "directory\n"
        mocker.patch(
            "ropes.lib.cli.actions_remote.run",
            side_effect=ValueError("Directory /bad does not exist"),
        )
        result = _invoke(mocker, mock_conn, ["run", "echo hi"])
        assert result.exit_code == 0
        assert "Directory /bad does not exist" in result.output

    def test_run_with_directory(self, mocker: MockerFixture, mock_conn: Any) -> None:
        """run -D specifies the remote working directory."""
        mock_conn.run.return_value.stdout = "directory\n"
        mock_run = mocker.patch("ropes.lib.cli.actions_remote.run")
        result = _invoke(mocker, mock_conn, ["run", "-D", "/custom/dir", "echo hi"])
        assert result.exit_code == 0
        assert mock_run.call_args[0][3] == "/custom/dir"  # directory


class TestViewCommand:
    def test_view_no_flags(
        self, mocker: MockerFixture, mock_conn: Any, tmp_path: Path
    ) -> None:
        """Default view: fetches, edits, does not write back."""
        tmp = tmp_path / "view_tmp.txt"
        mocker.patch("ropes.lib.cli.actions_local.determine_suffix", return_value=".txt")
        mocker.patch("ropes.lib.cli.actions_local.create_tmp_file", return_value=tmp)
        mock_edit = mocker.patch("ropes.lib.cli.actions_local.edit_file")
        mock_fetch = mocker.patch("ropes.lib.cli.actions_remote.remote_fetch")
        mock_put = mocker.patch("ropes.lib.cli.actions_remote.remote_put")
        mock_remove = mocker.patch("ropes.lib.cli.actions_local.remove_tmp_file")
        result = _invoke(mocker, mock_conn, ["view", "file.txt"])
        assert result.exit_code == 0
        mock_fetch.assert_called_once()
        mock_edit.assert_called_once_with(tmp, None)
        mock_put.assert_not_called()
        mock_remove.assert_called_once_with(tmp)

    def test_view_with_write(
        self, mocker: MockerFixture, mock_conn: Any, tmp_path: Path
    ) -> None:
        """--write flag: fetches, edits, writes back."""
        tmp = tmp_path / "view_tmp.txt"
        mocker.patch("ropes.lib.cli.actions_local.determine_suffix", return_value=".txt")
        mocker.patch("ropes.lib.cli.actions_local.create_tmp_file", return_value=tmp)
        mocker.patch("ropes.lib.cli.actions_local.edit_file")
        mocker.patch("ropes.lib.cli.actions_remote.remote_fetch")
        mock_put = mocker.patch("ropes.lib.cli.actions_remote.remote_put")
        mock_remove = mocker.patch("ropes.lib.cli.actions_local.remove_tmp_file")
        result = _invoke(mocker, mock_conn, ["view", "--write", "file.txt"])
        assert result.exit_code == 0
        mock_put.assert_called_once()
        mock_remove.assert_called_once_with(tmp)

    def test_view_with_new(
        self, mocker: MockerFixture, mock_conn: Any, tmp_path: Path
    ) -> None:
        """--new flag: skips fetch, edits, writes back."""
        tmp = tmp_path / "view_tmp.txt"
        mocker.patch("ropes.lib.cli.actions_local.determine_suffix", return_value=".txt")
        mocker.patch("ropes.lib.cli.actions_local.create_tmp_file", return_value=tmp)
        mocker.patch("ropes.lib.cli.actions_local.edit_file")
        mock_fetch = mocker.patch("ropes.lib.cli.actions_remote.remote_fetch")
        mock_put = mocker.patch("ropes.lib.cli.actions_remote.remote_put")
        mock_remove = mocker.patch("ropes.lib.cli.actions_local.remove_tmp_file")
        result = _invoke(mocker, mock_conn, ["view", "--new", "file.txt"])
        assert result.exit_code == 0
        mock_fetch.assert_not_called()
        mock_put.assert_called_once()
        mock_remove.assert_called_once_with(tmp)


class TestGetCommand:
    def test_get_command(self, mocker: MockerFixture, mock_conn: Any) -> None:
        """get downloads a remote file to a local path."""
        mocker.patch("ropes.lib.cli.actions_local.construct_local_path", return_value="/local/file.txt")
        mock_fetch = mocker.patch("ropes.lib.cli.actions_remote.remote_fetch")
        result = _invoke(mocker, mock_conn, ["get", "file.txt"])
        assert result.exit_code == 0
        mock_fetch.assert_called_once()


class TestCpCommand:
    def test_cp_command(self, mocker: MockerFixture, mock_conn: Any) -> None:
        """cp copies a file on the remote host."""
        mock_copy = mocker.patch("ropes.lib.cli.actions_remote.copy")
        result = _invoke(mocker, mock_conn, ["cp", "src.txt", "dst.txt"])
        assert result.exit_code == 0
        mock_copy.assert_called_once()


class TestTailCommand:
    def test_tail_normal(self, mocker: MockerFixture, mock_conn: Any) -> None:
        """tail without -f."""
        mock_tail = mocker.patch("ropes.lib.cli.actions_remote.tail")
        result = _invoke(mocker, mock_conn, ["tail", "log.txt"])
        assert result.exit_code == 0
        mock_tail.assert_called_once()

    def test_tail_follow(self, mocker: MockerFixture, mock_conn: Any) -> None:
        """tail -f for continuous monitoring."""
        mock_tail = mocker.patch("ropes.lib.cli.actions_remote.tail")
        result = _invoke(mocker, mock_conn, ["tail", "-f", "log.txt"])
        assert result.exit_code == 0
        args = mock_tail.call_args
        assert args[0][2] is True  # tail_f=True

    def test_tail_value_error(self, mocker: MockerFixture, mock_conn: Any) -> None:
        """tail catches ValueError and prints styled error."""
        mocker.patch(
            "ropes.lib.cli.actions_remote.tail",
            side_effect=ValueError("File not found"),
        )
        result = _invoke(mocker, mock_conn, ["tail", "missing.txt"])
        assert result.exit_code == 0
        assert "File not found" in result.output


class TestDiffCommand:
    def test_diff_identical(self, mocker: MockerFixture, mock_conn: Any) -> None:
        """Exit code 0: files are identical."""
        mocker.patch("ropes.lib.cli.actions_remote.diff", return_value=0)
        result = _invoke(mocker, mock_conn, ["diff", "a.txt", "b.txt"])
        assert result.exit_code == 0
        assert "Files are identical!" in result.output

    def test_diff_different(self, mocker: MockerFixture, mock_conn: Any) -> None:
        """Exit code 1: files are different."""
        mocker.patch("ropes.lib.cli.actions_remote.diff", return_value=1)
        result = _invoke(mocker, mock_conn, ["diff", "a.txt", "b.txt"])
        assert result.exit_code == 0
        assert "Files are different!" in result.output

    def test_diff_error(self, mocker: MockerFixture, mock_conn: Any) -> None:
        """Other exit code: error occurred."""
        mocker.patch("ropes.lib.cli.actions_remote.diff", return_value=2)
        result = _invoke(mocker, mock_conn, ["diff", "a.txt", "b.txt"])
        assert result.exit_code == 0
        assert "Some error occurred!" in result.output

    def test_diff_local_flag(self, mocker: MockerFixture, mock_conn: Any) -> None:
        """--local flag is forwarded to actions_remote.diff."""
        mock_diff = mocker.patch("ropes.lib.cli.actions_remote.diff", return_value=0)
        result = _invoke(mocker, mock_conn, ["diff", "--local", "a.txt", "b.txt"])
        assert result.exit_code == 0
        assert mock_diff.call_args[0][6] is True  # local=True

    def test_diff_custom_cmd(self, mocker: MockerFixture, mock_conn: Any) -> None:
        """--use flag selects a custom diff command."""
        mock_diff = mocker.patch("ropes.lib.cli.actions_remote.diff", return_value=0)
        result = _invoke(mocker, mock_conn, ["diff", "--use", "vimdiff", "a.txt", "b.txt"])
        assert result.exit_code == 0
        assert mock_diff.call_args[0][4] == "vimdiff"  # diff_cmd


class TestSyncCwdCommand:
    def test_sync_push(self, mocker: MockerFixture, mock_conn: Any) -> None:
        """Default push: local to remote."""
        mock_sync = mocker.patch("ropes.lib.cli.actions_remote.sync_cwd")
        result = _invoke(mocker, mock_conn, ["sync-cwd"])
        assert result.exit_code == 0
        mock_sync.assert_called_once()
        assert mock_sync.call_args[0][3] is False  # from_remote=False

    def test_sync_pull(self, mocker: MockerFixture, mock_conn: Any) -> None:
        """--from flag: pull from remote."""
        mock_sync = mocker.patch("ropes.lib.cli.actions_remote.sync_cwd")
        result = _invoke(mocker, mock_conn, ["sync-cwd", "--from"])
        assert result.exit_code == 0
        assert mock_sync.call_args[0][3] is True  # from_remote=True


class TestCompressCommand:
    def test_compress_basic(self, mocker: MockerFixture, mock_conn: Any) -> None:
        """Basic compress finds files and calls compress."""
        mocker.patch(
            "ropes.lib.cli.actions_remote.find",
            return_value=["file1.dat", "file2.dat"],
        )
        mock_compress = mocker.patch("ropes.lib.cli.actions_remote.compress")
        result = _invoke(mocker, mock_conn, ["compress"])
        assert result.exit_code == 0
        mock_compress.assert_called_once()

    def test_compress_only_cwd(self, mocker: MockerFixture, mock_conn: Any) -> None:
        """--only-cwd adds -maxdepth 1 to find args."""
        mock_find = mocker.patch("ropes.lib.cli.actions_remote.find", return_value=None)
        result = _invoke(mocker, mock_conn, ["compress", "--only-cwd"])
        assert result.exit_code == 0
        find_args = mock_find.call_args[0][3]
        assert "-maxdepth 1" in find_args

    def test_compress_no_files(self, mocker: MockerFixture, mock_conn: Any) -> None:
        """No files found: compress is not called."""
        mocker.patch("ropes.lib.cli.actions_remote.find", return_value=None)
        mock_compress = mocker.patch("ropes.lib.cli.actions_remote.compress")
        result = _invoke(mocker, mock_conn, ["compress"])
        assert result.exit_code == 0
        mock_compress.assert_not_called()
