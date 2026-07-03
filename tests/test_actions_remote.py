"""Collection of tests for actions_remote.py"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import invoke
import pytest
from pytest_mock import MockerFixture

from ropes.lib.actions_remote import _construct_path
from ropes.lib.actions_remote import _diff_local_cleanup
from ropes.lib.actions_remote import _get_file_type
from ropes.lib.actions_remote import _rsync
from ropes.lib.actions_remote import compress
from ropes.lib.actions_remote import copy as remote_copy
from ropes.lib.actions_remote import delete_file
from ropes.lib.actions_remote import diff
from ropes.lib.actions_remote import find
from ropes.lib.actions_remote import ls
from ropes.lib.actions_remote import mkdir
from ropes.lib.actions_remote import realpath
from ropes.lib.actions_remote import remote_fetch
from ropes.lib.actions_remote import remote_put
from ropes.lib.actions_remote import run as remote_run
from ropes.lib.actions_remote import sync_cwd
from ropes.lib.actions_remote import tail


class TestConstructPath:
    """Tests for _construct_path: local-to-remote path translation."""

    def test_path_equals_local_base(self, host_conf: dict[str, str]) -> None:
        """Path matching local_base exactly maps to remote_base."""
        assert _construct_path("/home/user/project", host_conf) == "/remote/home/user/project"

    def test_path_inside_local_base(self, host_conf: dict[str, str]) -> None:
        """Child of local_base maps its remote_base counterpart."""
        result = _construct_path("/home/user/project/sub/file.txt", host_conf)
        assert result == "/remote/home/user/project/sub/file.txt"

    def test_path_outside_local_base(self, host_conf: dict[str, str]) -> None:
        """Path outside local_base is returned unchanged (absolute)."""
        assert _construct_path("/other/path", host_conf) == "/other/path"

    def test_trailing_slashes_in_config(self) -> None:
        """Trailing slashes in config keys are stripped before comparison."""
        conf: dict[str, str] = {
            "local_base_path": "/home/user/project/",
            "remote_base_path": "/remote/home/user/project/",
        }
        result = _construct_path("/home/user/project/sub/file.txt", conf)
        assert result == "/remote/home/user/project/sub/file.txt"

    def test_config_missing_keys(self) -> None:
        """Missing local_base_path/remote_base_path raises KeyError."""
        with pytest.raises(KeyError):
            _construct_path("/some/path", {})

    def test_relative_path_inside_base(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Relative path is resolved via realpath before mapping to remote_base."""
        monkeypatch.chdir(tmp_path)
        conf = {
            "local_base_path": str(tmp_path),
            "remote_base_path": "/remote/root",
        }
        result = _construct_path("sub/file.txt", conf)
        assert result == "/remote/root/sub/file.txt"

    def test_relative_path_with_dotdot(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The .. component is collapsed by realpath before prefix substitution."""
        monkeypatch.chdir(tmp_path)
        conf = {
            "local_base_path": str(tmp_path),
            "remote_base_path": "/remote/root",
        }
        result = _construct_path("sub/../file.txt", conf)
        assert result == "/remote/root/file.txt"

    def test_path_with_dot_component(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """The . component is collapsed by realpath before prefix substitution."""
        monkeypatch.chdir(tmp_path)
        conf = {
            "local_base_path": str(tmp_path),
            "remote_base_path": "/remote/root",
        }
        result = _construct_path("sub/./file.txt", conf)
        assert result == "/remote/root/sub/file.txt"

    def test_relative_path_outside_base(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Relative path resolving outside local_base is returned as-is."""
        monkeypatch.chdir(tmp_path)
        conf = {
            "local_base_path": str(tmp_path / "sub"),
            "remote_base_path": "/remote/sub",
        }
        result = _construct_path("..", conf)
        assert result == str(tmp_path.parent)


class TestRemoteFetch:
    """Tests for remote_fetch: downloading files from a remote host."""

    def test_successful_fetch(
        self,
        mocker: MockerFixture,
        mock_conn: Any,
        host_conf: dict[str, str],
        tmp_path: Path,
    ) -> None:
        """Successful download: path translation, conn.get call, and post-download check pass."""
        mocker.patch("ropes.lib.actions_remote.os.path.isfile", return_value=True)
        dest = tmp_path / "downloaded.txt"
        remote_fetch(mock_conn, host_conf, "/home/user/project/file.txt", dest)
        mock_conn.get.assert_called_once()

    def test_remote_file_not_found(
        self,
        mock_conn: Any,
        host_conf: dict[str, str],
        tmp_path: Path,
    ) -> None:
        """conn.get raises FileNotFoundError; remote_fetch re-raises with host info."""
        mock_conn.get.side_effect = FileNotFoundError
        dest = tmp_path / "missing.txt"
        with pytest.raises(FileNotFoundError, match="Could not find file"):
            remote_fetch(mock_conn, host_conf, "/home/user/project/missing.txt", dest)

    def test_temp_file_not_created(
        self,
        mocker: MockerFixture,
        mock_conn: Any,
        host_conf: dict[str, str],
        tmp_path: Path,
    ) -> None:
        """conn.get succeeds but temp file is missing raises FileNotFoundError."""
        mocker.patch("ropes.lib.actions_remote.os.path.isfile", return_value=False)
        dest = tmp_path / "not_created.txt"
        with pytest.raises(FileNotFoundError, match="Temporary file not found"):
            remote_fetch(mock_conn, host_conf, "/home/user/project/file.txt", dest)


class TestRemotePut:
    """Tests for remote_put: uploading files to a remote host."""

    def test_successful_put(
        self,
        mock_conn: Any,
        host_conf: dict[str, str],
        tmp_path: Path,
    ) -> None:
        """Successful upload: path translation and conn.put call."""
        src = tmp_path / "local.txt"
        remote_put(mock_conn, host_conf, "/home/user/project/remote.txt", src)
        mock_conn.put.assert_called_once()

    def test_local_file_not_found(
        self,
        mock_conn: Any,
        host_conf: dict[str, str],
        tmp_path: Path,
    ) -> None:
        """conn.put raises FileNotFoundError; remote_put re-raises with local path info."""
        mock_conn.put.side_effect = FileNotFoundError
        src = tmp_path / "missing.txt"
        with pytest.raises(FileNotFoundError, match="Could not find file"):
            remote_put(mock_conn, host_conf, "/home/user/project/remote.txt", src)


class TestLs:
    """Tests for ls: listing remote directory contents."""

    def test_ls_success(self, mock_conn: Any, host_conf: dict[str, str]) -> None:
        """ls builds the correct command string with translated remote path."""
        ls(mock_conn, "/home/user/project", host_conf, "-lAh")
        mock_conn.run.assert_called_once()
        args, _ = mock_conn.run.call_args
        assert "ls -lAh" in args[0]
        assert "/remote/home/user/project" in args[0]

    def test_ls_unexpected_exit(
        self,
        mock_conn: Any,
        host_conf: dict[str, str],
        mocker: MockerFixture,
    ) -> None:
        """ls handles conn.run failure gracefully without crashing."""
        mock_conn.run.side_effect = invoke.exceptions.UnexpectedExit(None)
        mocker.patch("builtins.print")
        ls(mock_conn, "/home/user/project", host_conf, "-lAh")
        mock_conn.run.assert_called_once()


class TestMkdir:
    """Tests for mkdir: creating remote directories."""

    def test_mkdir_normal(self, mock_conn: Any, host_conf: dict[str, str]) -> None:
        """Absolute path is translated and passed to mkdir -p."""
        mkdir(mock_conn, host_conf, "/home/user/project/newdir")
        mock_conn.run.assert_called_once_with("mkdir -p /remote/home/user/project/newdir")

    def test_mkdir_dot(
        self,
        mocker: MockerFixture,
        mock_conn: Any,
        host_conf: dict[str, str],
    ) -> None:
        """The '.' special case uses basename(CWD) as the directory name and chdirs to parent."""
        mocker.patch("ropes.lib.actions_remote.os.getcwd", return_value="/home/user/project/sub")
        mocker.patch("ropes.lib.actions_remote.os.chdir")
        mocker.patch(
            "ropes.lib.actions_remote._construct_path",
            return_value="/remote/home/user/project/sub",
        )
        mkdir(mock_conn, host_conf, ".")
        mock_conn.run.assert_called_once_with("mkdir -p /remote/home/user/project/sub")

    def test_mkdir_unexpected_exit(
        self,
        mock_conn: Any,
        host_conf: dict[str, str],
        mocker: MockerFixture,
    ) -> None:
        """mkdir handles conn.run failure gracefully and prints an error message."""
        mock_conn.run.side_effect = invoke.exceptions.UnexpectedExit(None)
        mock_print = mocker.patch("builtins.print")
        mkdir(mock_conn, host_conf, "/home/user/project/newdir")
        mock_conn.run.assert_called_once()
        mock_print.assert_called_once_with("ERROR: cannot create directory!")


class TestRsync:
    """Tests for _rsync: file synchronization via rsync."""

    def test_rsync_push(self, mocker: MockerFixture) -> None:
        """Push mode: hostname: is prepended to the destination path."""
        mock_subprocess = mocker.patch("ropes.lib.actions_remote.subprocess.run")
        _rsync("myhost", "/local/path", "/remote/path", "-auvz")
        cmd = mock_subprocess.call_args[0][0]
        assert cmd[:2] == ["rsync", "-auvz"]
        assert cmd[-2] == "/local/path/"
        assert cmd[-1] == "myhost:/remote/path/"

    def test_rsync_pull(self, mocker: MockerFixture) -> None:
        """Pull mode: hostname: is prepended to the source path."""
        mock_subprocess = mocker.patch("ropes.lib.actions_remote.subprocess.run")
        _rsync("myhost", "/remote/path", "/local/path", "-auvz", src_is_remote=True)
        cmd = mock_subprocess.call_args[0][0]
        assert cmd[-2] == "myhost:/remote/path/"
        assert cmd[-1] == "/local/path/"

    def test_rsync_subprocess_failure(self, mocker: MockerFixture) -> None:
        """subprocess.run failure (check=True) raises CalledProcessError."""
        import subprocess  # pylint: disable=import-outside-toplevel

        mock_subprocess = mocker.patch("ropes.lib.actions_remote.subprocess.run")
        mock_subprocess.side_effect = subprocess.CalledProcessError(1, ["rsync"])
        with pytest.raises(subprocess.CalledProcessError):
            _rsync("myhost", "/local/path", "/remote/path", "-auvz")


class TestSyncCwd:
    """Tests for sync_cwd: syncing the current working directory."""

    def test_sync_push(
        self,
        mocker: MockerFixture,
        mock_conn: Any,
        host_conf: dict[str, str],
    ) -> None:
        """Push from local_base: CWD equals local_base, uses remote_base directly."""
        mocker.patch("ropes.lib.actions_remote.os.getcwd", return_value="/home/user/project")
        mocker.patch("ropes.lib.actions_remote.mkdir")
        mock_rsync = mocker.patch("ropes.lib.actions_remote._rsync")
        sync_cwd(mock_conn, host_conf, "-auvz", from_remote=False)
        mock_rsync.assert_called_once_with(
            "testhost", "/home/user/project", "/remote/home/user/project", "-auvz"
        )

    def test_sync_pull(
        self,
        mocker: MockerFixture,
        mock_conn: Any,
        host_conf: dict[str, str],
    ) -> None:
        """Pull from remote_base: CWD equals local_base, uses remote_base with src_is_remote."""
        mocker.patch("ropes.lib.actions_remote.os.getcwd", return_value="/home/user/project")
        mock_rsync = mocker.patch("ropes.lib.actions_remote._rsync")
        sync_cwd(mock_conn, host_conf, "-auvz", from_remote=True)
        mock_rsync.assert_called_once_with(
            "testhost",
            "/remote/home/user/project",
            "/home/user/project",
            "-auvz",
            src_is_remote=True,
        )

    def test_sync_nested_dir(
        self,
        mocker: MockerFixture,
        mock_conn: Any,
        host_conf: dict[str, str],
    ) -> None:
        """Push from a subdirectory: _construct_path translates '.' to the remote equivalent."""
        mocker.patch("ropes.lib.actions_remote.os.getcwd", return_value="/home/user/project/sub")
        mock_rsync = mocker.patch("ropes.lib.actions_remote._rsync")
        mocker.patch("ropes.lib.actions_remote.mkdir")
        mocker.patch(
            "ropes.lib.actions_remote._construct_path",
            return_value="/remote/home/user/project/sub",
        )
        sync_cwd(mock_conn, host_conf, "-auvz", from_remote=False)
        mock_rsync.assert_called_once_with(
            "testhost", "/home/user/project/sub", "/remote/home/user/project/sub", "-auvz"
        )


class TestFind:
    """Tests for find: searching for files on a remote host."""

    def test_find_with_results(
        self,
        mocker: MockerFixture,
        mock_conn: Any,
        host_conf: dict[str, str],
    ) -> None:
        """find backend returns results split by newline."""
        mocker.patch("ropes.lib.actions_remote._construct_path", return_value="/remote/root")
        mock_conn.run.return_value.stdout = "file1.py\nfile2.py\n"
        result = find(mock_conn, host_conf, "find", "-name '*.py'")
        assert result == ["file1.py", "file2.py", ""]
        mock_conn.run.assert_called_once_with("find . -name '*.py'", hide=True)

    def test_find_with_fd(
        self,
        mocker: MockerFixture,
        mock_conn: Any,
        host_conf: dict[str, str],
    ) -> None:
        """fd backend returns results split by newline."""
        mocker.patch("ropes.lib.actions_remote._construct_path", return_value="/remote/root")
        mock_conn.run.return_value.stdout = "a.py\nb.py\n"
        result = find(mock_conn, host_conf, "fd", "-e py", expr=".")
        assert result == ["a.py", "b.py", ""]
        mock_conn.run.assert_called_once_with("fd -e py . .", hide=True)

    def test_find_no_results(
        self,
        mocker: MockerFixture,
        mock_conn: Any,
        host_conf: dict[str, str],
    ) -> None:
        """Empty stdout from conn.run returns None."""
        mocker.patch("ropes.lib.actions_remote._construct_path", return_value="/remote/root")
        mock_conn.run.return_value.stdout = ""
        result = find(mock_conn, host_conf, "find", "")
        assert result is None
        mock_conn.run.assert_called_once_with("find . ", hide=True)

    def test_find_not_implemented(
        self,
        mock_conn: Any,
        host_conf: dict[str, str],
    ) -> None:
        """Unsupported backend raises NotImplementedError."""
        with pytest.raises(NotImplementedError, match="Functionality for ripgrep not yet"):
            find(mock_conn, host_conf, "ripgrep", "")

    def test_find_remote_failure(
        self,
        mocker: MockerFixture,
        mock_conn: Any,
        host_conf: dict[str, str],
    ) -> None:
        """UnexpectedExit from conn.run is propagated."""
        mocker.patch("ropes.lib.actions_remote._construct_path", return_value="/remote/root")
        mock_conn.run.side_effect = invoke.exceptions.UnexpectedExit(None)
        with pytest.raises(invoke.exceptions.UnexpectedExit):
            find(mock_conn, host_conf, "find", "")


class TestRealpath:
    """Tests for realpath: resolving remote paths."""

    def test_realpath_without_type(
        self,
        mock_conn: Any,
        host_conf: dict[str, str],
    ) -> None:
        """Path is translated without the file-type prefix."""
        result = realpath(mock_conn, host_conf, "/home/user/project/file.txt", show_type=False)
        assert result == "/remote/home/user/project/file.txt"

    def test_realpath_with_type(
        self,
        mock_conn: Any,
        host_conf: dict[str, str],
        mocker: MockerFixture,
    ) -> None:
        """Path is translated with the file-type prefix prepended."""
        mocker.patch.object(
            mock_conn, "run", return_value=mocker.MagicMock(stdout="regular file\n")
        )
        result = realpath(mock_conn, host_conf, "/home/user/project/file.txt", show_type=True)
        assert "regular file" in result
        assert "/remote/home/user/project/file.txt" in result

    def test_realpath_with_type_unknown(
        self,
        mock_conn: Any,
        host_conf: dict[str, str],
        mocker: MockerFixture,
    ) -> None:
        """show_type with 'unknown' file type still returns the path."""
        mocker.patch("ropes.lib.actions_remote._construct_path", return_value="/remote/path")
        mocker.patch("ropes.lib.actions_remote._get_file_type", return_value="unknown")
        result = realpath(mock_conn, host_conf, "/local/path", show_type=True)
        assert result == f"{'unknown':15} /remote/path"


class TestGetFileType:
    """Tests for _get_file_type: determining remote file types via stat."""

    def test_regular_file(self, mock_conn: Any) -> None:
        """stat output 'regular file' is parsed correctly."""
        mock_conn.run.return_value.stdout = "regular file\n"
        assert _get_file_type(mock_conn, "/some/path") == "regular file"

    def test_directory(self, mock_conn: Any) -> None:
        """stat output 'directory' is parsed correctly."""
        mock_conn.run.return_value.stdout = "directory\n"
        assert _get_file_type(mock_conn, "/some/dir") == "directory"

    def test_unknown_on_failure(self, mock_conn: Any) -> None:
        """UnexpectedExit from conn.run returns 'unknown'."""
        mock_conn.run.side_effect = invoke.exceptions.UnexpectedExit(None)
        assert _get_file_type(mock_conn, "/bad/path") == "unknown"


class TestCompress:
    """Tests for compress: running compression commands on a remote host."""

    def test_compress_files(
        self,
        mock_conn: Any,
        host_conf: dict[str, str],
    ) -> None:
        """compress forwards the command and file list to conn.run."""
        compress(mock_conn, host_conf, "bzip2", "-v", ["file1.dat", "file2.dat"])
        mock_conn.run.assert_called_once_with("bzip2 -v file1.dat file2.dat")

    def test_compress_remote_failure(
        self,
        mock_conn: Any,
        host_conf: dict[str, str],
    ) -> None:
        """UnexpectedExit from conn.run is propagated."""
        mock_conn.run.side_effect = invoke.exceptions.UnexpectedExit(None)
        with pytest.raises(invoke.exceptions.UnexpectedExit):
            compress(mock_conn, host_conf, "gzip", "-k", ["file.dat"])


class TestDeleteFile:
    """Tests for delete_file: deleting remote files."""

    def test_delete_confirmed(
        self,
        mocker: MockerFixture,
        mock_conn: Any,
        host_conf: dict[str, str],
    ) -> None:
        """Regular file is confirmed and deleted: stat then rm."""
        mock_conn.run.return_value.stdout = "regular file\n"
        mocker.patch("builtins.input", return_value="y")
        mocker.patch("builtins.print")
        delete_file(mock_conn, host_conf, "/home/user/project/file.txt")
        assert mock_conn.run.mock_calls == [
            mocker.call("stat -c %F /remote/home/user/project/file.txt", hide=True),
            mocker.call("rm /remote/home/user/project/file.txt"),
        ]

    def test_delete_confirmed_symlink(
        self,
        mocker: MockerFixture,
        mock_conn: Any,
        host_conf: dict[str, str],
    ) -> None:
        """Symbolic link is allowed for deletion."""
        mock_conn.run.return_value.stdout = "symbolic link\n"
        mocker.patch("builtins.input", return_value="y")
        mocker.patch("builtins.print")
        delete_file(mock_conn, host_conf, "/home/user/project/file.txt")
        assert mock_conn.run.mock_calls == [
            mocker.call("stat -c %F /remote/home/user/project/file.txt", hide=True),
            mocker.call("rm /remote/home/user/project/file.txt"),
        ]

    def test_delete_confirmed_empty_file(
        self,
        mocker: MockerFixture,
        mock_conn: Any,
        host_conf: dict[str, str],
    ) -> None:
        """Regular empty file is allowed for deletion."""
        mock_conn.run.return_value.stdout = "regular empty file\n"
        mocker.patch("builtins.input", return_value="y")
        mocker.patch("builtins.print")
        delete_file(mock_conn, host_conf, "/home/user/project/file.txt")
        assert mock_conn.run.mock_calls == [
            mocker.call("stat -c %F /remote/home/user/project/file.txt", hide=True),
            mocker.call("rm /remote/home/user/project/file.txt"),
        ]

    def test_delete_declined(
        self,
        mocker: MockerFixture,
        mock_conn: Any,
        host_conf: dict[str, str],
    ) -> None:
        """User declines deletion: only stat is called, no rm."""
        mock_conn.run.return_value.stdout = "regular file\n"
        mocker.patch("builtins.input", return_value="n")
        mocker.patch("builtins.print")
        delete_file(mock_conn, host_conf, "/home/user/project/file.txt")
        mock_conn.run.assert_called_once_with(
            "stat -c %F /remote/home/user/project/file.txt", hide=True
        )

    def test_delete_directory_raises(
        self,
        mock_conn: Any,
        host_conf: dict[str, str],
    ) -> None:
        """Directory type raises ValueError instead of deleting."""
        mock_conn.run.return_value.stdout = "directory\n"
        with pytest.raises(ValueError, match="Path is not a file or link"):
            delete_file(mock_conn, host_conf, "/home/user/project")

    def test_delete_rm_failure(
        self,
        mocker: MockerFixture,
        mock_conn: Any,
        host_conf: dict[str, str],
    ) -> None:
        """rm command failure raises UnexpectedExit."""
        mock_conn.run.return_value.stdout = "regular file\n"
        mocker.patch("builtins.input", return_value="y")
        mocker.patch("builtins.print")
        mock_conn.run.side_effect = [mocker.DEFAULT, invoke.exceptions.UnexpectedExit(None)]
        with pytest.raises(invoke.exceptions.UnexpectedExit):
            delete_file(mock_conn, host_conf, "/home/user/project/file.txt")


class TestTail:
    """Tests for tail: displaying the end of remote files."""

    def test_tail_normal(
        self,
        mock_conn: Any,
        host_conf: dict[str, str],
    ) -> None:
        """tail without -f reads the file and exits."""
        tail(mock_conn, host_conf, False, "/home/user/project/log.txt")
        mock_conn.run.assert_called_once_with("tail /remote/home/user/project/log.txt")

    def test_tail_follow(
        self,
        mock_conn: Any,
        host_conf: dict[str, str],
    ) -> None:
        """tail -f follows the file and streams new content."""
        tail(mock_conn, host_conf, True, "/home/user/project/log.txt")
        mock_conn.run.assert_called_once_with("tail -f /remote/home/user/project/log.txt")

    def test_tail_remote_failure(
        self,
        mock_conn: Any,
        host_conf: dict[str, str],
    ) -> None:
        """UnexpectedExit from conn.run is propagated."""
        mock_conn.run.side_effect = invoke.exceptions.UnexpectedExit(None)
        with pytest.raises(invoke.exceptions.UnexpectedExit):
            tail(mock_conn, host_conf, False, "/nonexistent.log")


class TestCopy:
    """Tests for copy: copying files on a remote host."""

    def test_copy_file(
        self,
        mock_conn: Any,
        host_conf: dict[str, str],
        mocker: MockerFixture,
    ) -> None:
        """Both source and destination paths are translated before the cp call."""
        mocker.patch("builtins.print")
        remote_copy(
            mock_conn,
            host_conf,
            "/home/user/project/src.txt",
            "/home/user/project/dst.txt",
        )
        mock_conn.run.assert_called_once_with(
            "cp /remote/home/user/project/src.txt /remote/home/user/project/dst.txt"
        )

    def test_copy_remote_failure(
        self,
        mock_conn: Any,
        host_conf: dict[str, str],
        mocker: MockerFixture,
    ) -> None:
        """UnexpectedExit from conn.run is propagated."""
        mocker.patch("builtins.print")
        mock_conn.run.side_effect = invoke.exceptions.UnexpectedExit(None)
        with pytest.raises(invoke.exceptions.UnexpectedExit):
            remote_copy(
                mock_conn, host_conf, "/home/user/project/src.txt", "/home/user/project/dst.txt"
            )


class TestRun:
    """Tests for run: executing commands on a remote host."""

    def test_run_direct_command(
        self,
        mock_conn: Any,
        host_conf: dict[str, str],
    ) -> None:
        """A plain command is executed after the directory is verified."""
        mock_conn.run.return_value.stdout = "directory\n"
        remote_run(mock_conn, host_conf, "echo hello", "/home/user/project")
        mock_conn.run.assert_called_with("echo hello")

    def test_run_with_alias(self, mock_conn: Any) -> None:
        """An @-prefixed command is resolved from host_conf and executed."""
        conf: dict[str, str] = {
            "local_base_path": "/local",
            "remote_base_path": "/remote",
            "hostname": "h",
            "@build": "make && make install",
        }
        mock_conn.run.return_value.stdout = "directory\n"
        remote_run(mock_conn, conf, "@build", "/local")
        mock_conn.run.assert_called_with("make && make install")

    def test_run_unknown_alias(
        self,
        mock_conn: Any,
        host_conf: dict[str, str],
    ) -> None:
        """An undefined @-alias raises ValueError."""
        with pytest.raises(ValueError, match="Alias '@bad' not found"):
            remote_run(mock_conn, host_conf, "@bad", "/local")

    def test_run_invalid_directory(
        self,
        mock_conn: Any,
        host_conf: dict[str, str],
    ) -> None:
        """A non-directory remote path raises ValueError."""
        mock_conn.run.return_value.stdout = "regular file\n"
        with pytest.raises(ValueError, match="Directory .* does not exist"):
            remote_run(mock_conn, host_conf, "echo hi", "/home/user/project")

    def test_run_command_failure(
        self,
        mocker: MockerFixture,
        mock_conn: Any,
        host_conf: dict[str, str],
    ) -> None:
        """UnexpectedExit from command execution is propagated."""
        mock_conn.run.return_value.stdout = "directory\n"
        mock_conn.run.side_effect = [mocker.DEFAULT, invoke.exceptions.UnexpectedExit(None)]
        mocker.patch("builtins.print")
        with pytest.raises(invoke.exceptions.UnexpectedExit):
            remote_run(mock_conn, host_conf, "echo hello", "/home/user/project")


class TestDiffLocalCleanup:
    """Tests for _diff_local_cleanup: removing temporary diff files."""

    def test_cleanup_removes_each_file(self, mocker: MockerFixture) -> None:
        """Calls remove_tmp_file for each file in the list."""
        mock_remove = mocker.patch("ropes.lib.actions_remote.actions_local.remove_tmp_file")
        tmp_files = [Path("/tmp/foo"), Path("/tmp/bar")]
        _diff_local_cleanup(tmp_files)
        assert mock_remove.call_args_list == [
            mocker.call(Path("/tmp/foo")),
            mocker.call(Path("/tmp/bar")),
        ]

    def test_cleanup_empty_list(self, mocker: MockerFixture) -> None:
        """Empty list does not call remove_tmp_file."""
        mock_remove = mocker.patch("ropes.lib.actions_remote.actions_local.remove_tmp_file")
        _diff_local_cleanup([])
        mock_remove.assert_not_called()


class TestDiff:
    """Tests for diff: comparing two remote files."""

    # --- Remote mode (default) ---

    def test_diff_remote_identical(
        self,
        mocker: MockerFixture,
        mock_conn: Any,
        host_conf: dict[str, str],
    ) -> None:
        """Identical remote files: diff exits 0."""
        mocker.patch(
            "ropes.lib.actions_remote._construct_path",
            side_effect=["/remote/a.txt", "/remote/b.txt"],
        )
        result = diff(mock_conn, host_conf, "path_a", "path_b", "diff", "", False)
        assert result == 0
        mock_conn.run.assert_called_once_with(
            "diff /remote/a.txt /remote/b.txt", pty=True, warn=True
        )

    def test_diff_remote_different(
        self,
        mocker: MockerFixture,
        mock_conn: Any,
        host_conf: dict[str, str],
    ) -> None:
        """Different remote files: diff exits 1, propagated as return value."""
        mocker.patch(
            "ropes.lib.actions_remote._construct_path",
            side_effect=["/remote/a.txt", "/remote/b.txt"],
        )
        mock_conn.run.return_value.exited = 1
        result = diff(mock_conn, host_conf, "path_a", "path_b", "diff", "", False)
        assert result == 1

    def test_diff_remote_custom_cmd(
        self,
        mocker: MockerFixture,
        mock_conn: Any,
        host_conf: dict[str, str],
    ) -> None:
        """Custom diff command (e.g. vimdiff) is used in the remote command string."""
        mocker.patch(
            "ropes.lib.actions_remote._construct_path",
            side_effect=["/remote/a.txt", "/remote/b.txt"],
        )
        diff(mock_conn, host_conf, "path_a", "path_b", "vimdiff", "", False)
        mock_conn.run.assert_called_once_with(
            "vimdiff /remote/a.txt /remote/b.txt", pty=True, warn=True
        )

    def test_diff_remote_custom_args(
        self,
        mocker: MockerFixture,
        mock_conn: Any,
        host_conf: dict[str, str],
    ) -> None:
        """Extra diff arguments (e.g. -u) appear in the remote command."""
        mocker.patch(
            "ropes.lib.actions_remote._construct_path",
            side_effect=["/remote/a.txt", "/remote/b.txt"],
        )
        diff(mock_conn, host_conf, "path_a", "path_b", "diff", "-u", False)
        mock_conn.run.assert_called_once_with(
            "diff -u /remote/a.txt /remote/b.txt", pty=True, warn=True
        )

    def test_diff_remote_path_translation(
        self,
        mocker: MockerFixture,
        mock_conn: Any,
        host_conf: dict[str, str],
    ) -> None:
        """Both paths are translated via _construct_path before diff."""
        mock_construct = mocker.patch(
            "ropes.lib.actions_remote._construct_path",
            side_effect=["/remote/x.txt", "/remote/y.txt"],
        )
        diff(mock_conn, host_conf, "local_a", "local_b", "diff", "", False)
        assert mock_construct.call_args_list == [
            mocker.call("local_a", host_conf),
            mocker.call("local_b", host_conf),
        ]

    # --- Local mode ---

    def test_diff_local_identical(
        self,
        mocker: MockerFixture,
        mock_conn: Any,
        host_conf: dict[str, str],
        tmp_path: Path,
    ) -> None:
        """Local mode: identical files, subprocess exits 0, temps cleaned."""
        tmp_a = tmp_path / "ropes_a.txt"
        tmp_b = tmp_path / "ropes_b.txt"
        mocker.patch("ropes.lib.actions_local.create_tmp_file", side_effect=[tmp_a, tmp_b])
        mock_fetch = mocker.patch("ropes.lib.actions_remote.remote_fetch")
        mock_remove = mocker.patch("ropes.lib.actions_local.remove_tmp_file")
        mock_subprocess = mocker.patch(
            "ropes.lib.actions_remote.subprocess.run",
            return_value=mocker.MagicMock(returncode=0),
        )
        result = diff(mock_conn, host_conf, "path_a", "path_b", "diff", "", True)
        assert result == 0
        assert mock_fetch.call_count == 2
        assert mock_remove.call_count == 2
        mock_subprocess.assert_called_once_with(["diff", tmp_a, tmp_b], check=False)

    def test_diff_local_different(
        self,
        mocker: MockerFixture,
        mock_conn: Any,
        host_conf: dict[str, str],
        tmp_path: Path,
    ) -> None:
        """Local mode: files differ, subprocess exits 1, return code propagated."""
        tmp_a = tmp_path / "ropes_a.txt"
        tmp_b = tmp_path / "ropes_b.txt"
        mocker.patch("ropes.lib.actions_local.create_tmp_file", side_effect=[tmp_a, tmp_b])
        mocker.patch("ropes.lib.actions_remote.remote_fetch")
        mock_remove = mocker.patch("ropes.lib.actions_local.remove_tmp_file")
        mocker.patch(
            "ropes.lib.actions_remote.subprocess.run",
            return_value=mocker.MagicMock(returncode=1),
        )
        result = diff(mock_conn, host_conf, "path_a", "path_b", "diff", "", True)
        assert result == 1
        assert mock_remove.call_count == 2

    def test_diff_local_custom_cmd_and_args(
        self,
        mocker: MockerFixture,
        mock_conn: Any,
        host_conf: dict[str, str],
        tmp_path: Path,
    ) -> None:
        """Local mode: custom diff cmd and args forwarded to subprocess."""
        tmp_a = tmp_path / "ropes_a.txt"
        tmp_b = tmp_path / "ropes_b.txt"
        mocker.patch("ropes.lib.actions_local.create_tmp_file", side_effect=[tmp_a, tmp_b])
        mocker.patch("ropes.lib.actions_remote.remote_fetch")
        mocker.patch("ropes.lib.actions_local.remove_tmp_file")
        mock_subprocess = mocker.patch(
            "ropes.lib.actions_remote.subprocess.run",
            return_value=mocker.MagicMock(returncode=0),
        )
        diff(
            mock_conn,
            host_conf,
            "path_a",
            "path_b",
            diff_cmd="meld",
            diff_args="-n",
            local=True,
        )
        mock_subprocess.assert_called_once_with(["meld", "-n", tmp_a, tmp_b], check=False)

    def test_diff_local_first_file_missing(
        self,
        mocker: MockerFixture,
        mock_conn: Any,
        host_conf: dict[str, str],
        tmp_path: Path,
    ) -> None:
        """Local mode: first fetch fails, both temps cleaned, error propagated."""
        tmp_a = tmp_path / "ropes_a.txt"
        tmp_b = tmp_path / "ropes_b.txt"
        mocker.patch("ropes.lib.actions_local.create_tmp_file", side_effect=[tmp_a, tmp_b])
        mocker.patch(
            "ropes.lib.actions_remote.remote_fetch",
            side_effect=FileNotFoundError,
        )
        mock_remove = mocker.patch("ropes.lib.actions_local.remove_tmp_file")
        with pytest.raises(FileNotFoundError):
            diff(mock_conn, host_conf, "path_a", "path_b", "diff", "", True)
        assert mock_remove.call_count == 2

    def test_diff_local_second_file_missing(
        self,
        mocker: MockerFixture,
        mock_conn: Any,
        host_conf: dict[str, str],
        tmp_path: Path,
    ) -> None:
        """Local mode: second fetch fails, both temps cleaned, error propagated."""
        tmp_a = tmp_path / "ropes_a.txt"
        tmp_b = tmp_path / "ropes_b.txt"
        mocker.patch("ropes.lib.actions_local.create_tmp_file", side_effect=[tmp_a, tmp_b])
        mocker.patch(
            "ropes.lib.actions_remote.remote_fetch",
            side_effect=[None, FileNotFoundError],
        )
        mock_remove = mocker.patch("ropes.lib.actions_local.remove_tmp_file")
        with pytest.raises(FileNotFoundError):
            diff(mock_conn, host_conf, "path_a", "path_b", "diff", "", True)
        assert mock_remove.call_count == 2

    def test_diff_local_diff_cmd_not_found(
        self,
        mocker: MockerFixture,
        mock_conn: Any,
        host_conf: dict[str, str],
        tmp_path: Path,
    ) -> None:
        """Local mode: subprocess.run raises, temps cleaned, error propagated."""
        tmp_a = tmp_path / "ropes_a.txt"
        tmp_b = tmp_path / "ropes_b.txt"
        mocker.patch("ropes.lib.actions_local.create_tmp_file", side_effect=[tmp_a, tmp_b])
        mocker.patch("ropes.lib.actions_remote.remote_fetch")
        mock_remove = mocker.patch("ropes.lib.actions_local.remove_tmp_file")
        mocker.patch(
            "ropes.lib.actions_remote.subprocess.run",
            side_effect=FileNotFoundError("diff: not found"),
        )
        with pytest.raises(FileNotFoundError):
            diff(mock_conn, host_conf, "path_a", "path_b", "diff", "", True)
        assert mock_remove.call_count == 2

    def test_diff_local_cleanup_on_any_error(
        self,
        mocker: MockerFixture,
        mock_conn: Any,
        host_conf: dict[str, str],
        tmp_path: Path,
    ) -> None:
        """Local mode: any exception triggers temp cleanup via finally blocks."""
        tmp_a = tmp_path / "ropes_a.txt"
        tmp_b = tmp_path / "ropes_b.txt"
        mocker.patch("ropes.lib.actions_local.create_tmp_file", side_effect=[tmp_a, tmp_b])
        mocker.patch("ropes.lib.actions_remote.remote_fetch")
        mock_remove = mocker.patch("ropes.lib.actions_local.remove_tmp_file")
        mocker.patch(
            "ropes.lib.actions_remote.subprocess.run",
            side_effect=RuntimeError("unexpected"),
        )
        with pytest.raises(RuntimeError):
            diff(mock_conn, host_conf, "path_a", "path_b", "diff", "", True)
        assert mock_remove.call_count == 2

    # --- Edge cases ---

    def test_diff_same_path(
        self,
        mocker: MockerFixture,
        mock_conn: Any,
        host_conf: dict[str, str],
    ) -> None:
        """Same path for both arguments: diff runs (returns 0 for identical)."""
        mocker.patch(
            "ropes.lib.actions_remote._construct_path",
            return_value="/remote/same.txt",
        )
        result = diff(mock_conn, host_conf, "same.txt", "same.txt", "diff", "", False)
        assert result == 0
        mock_conn.run.assert_called_once_with(
            "diff /remote/same.txt /remote/same.txt", pty=True, warn=True
        )
