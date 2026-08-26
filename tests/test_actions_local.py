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

"""Collection of tests for actions_local.py"""

import os
import pathlib
from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from ropeway_cli.lib.actions_local import construct_local_path
from ropeway_cli.lib.actions_local import create_tmp_file
from ropeway_cli.lib.actions_local import determine_suffix
from ropeway_cli.lib.actions_local import edit_file
from ropeway_cli.lib.actions_local import load_host
from ropeway_cli.lib.actions_local import remove_tmp_file


class TestDetermineSuffix:
    """Tests for determine_suffix: extracting file extensions."""

    def test_file_with_extension(self) -> None:
        """Simple extension returns the suffix including the dot."""
        assert determine_suffix("data.txt") == ".txt"

    def test_file_with_multiple_extensions(self) -> None:
        """Only the last extension is returned."""
        assert determine_suffix("archive.tar.gz") == ".gz"

    def test_file_with_no_extension(self) -> None:
        """File without a dot returns empty string."""
        assert determine_suffix("Makefile") == ""

    def test_dot_in_directory_name(self) -> None:
        """A dot in a parent directory is not treated as the file extension."""
        assert determine_suffix("/some.dir/file") == ""

    def test_hidden_file(self) -> None:
        """Hidden files (dot at start of basename) have no extension."""
        assert determine_suffix(".hidden") == ""


class TestLoadHost:
    """Tests for load_host: loading host configurations."""

    def test_host_found(self, mock_hosts_file: str) -> None:
        """Host present in the JSON file is returned."""
        result = load_host("myhost", mock_hosts_file)
        assert result == {"local_base_path": "/local/path", "remote_base_path": "/remote/path"}

    def test_host_not_found(self, mock_hosts_file: str) -> None:
        """Missing host name raises KeyError."""
        with pytest.raises(KeyError, match="Host unknown not found in hosts file"):
            load_host("unknown", mock_hosts_file)

    def test_custom_path_used(self, tmp_path: Path) -> None:
        """A custom config file path is used instead of the default."""
        f = tmp_path / "custom.json"
        f.write_text('{"custom": {"key": "val"}}')
        result = load_host("custom", str(f))
        assert result == {"key": "val"}

    def test_default_host_file(self, mocker: MockerFixture, tmp_path: Path) -> None:
        """When no path is given, the default HOST_CONFIG location is used."""
        f = tmp_path / "hosts.json"
        f.write_text('{"defaulthost": {"key": "val"}}')
        mocker.patch("ropeway_cli.lib.actions_local.HOST_CONFIG", str(f))
        result = load_host("defaulthost")
        assert result == {"key": "val"}

    def test_malformed_json(self, tmp_path: Path) -> None:
        """Malformed JSON in the host file raises an exception."""
        f = tmp_path / "bad.json"
        f.write_text("{invalid json}")
        with pytest.raises(Exception):
            load_host("any", str(f))


class TestCreateTmpFile:
    """Tests for create_tmp_file: creating temporary files."""

    def test_creates_file_with_suffix(self) -> None:
        """File is created with the requested suffix."""
        path = create_tmp_file(".txt")
        try:
            assert path.exists()
            assert path.suffix == ".txt"
        finally:
            path.unlink(missing_ok=True)

    def test_creates_file_with_empty_suffix(self) -> None:
        """File is created without a suffix when empty string is given."""
        path = create_tmp_file("")
        try:
            assert path.exists()
            assert path.suffix == ""
        finally:
            path.unlink(missing_ok=True)


class TestRemoveTmpFile:
    """Tests for remove_tmp_file: deleting temporary files."""

    def test_removes_existing_file(self, tmp_path: Path) -> None:
        """Existing file is deleted."""
        f = tmp_path / "to_delete.txt"
        f.write_text("content")
        remove_tmp_file(f)
        assert not f.exists()

    def test_skips_non_existing_file(self) -> None:
        """Non-existing file is silently skipped without error."""
        remove_tmp_file(pathlib.Path("/nonexistent/file.txt"))


class TestEditFile:
    """Tests for edit_file: opening files in an editor."""

    def test_editor_from_parameter(self, mocker: MockerFixture) -> None:
        """Explicit editor parameter is used."""
        mock_run = mocker.patch("ropeway_cli.lib.actions_local.subprocess.run")
        path = pathlib.Path("/tmp/test.txt")
        edit_file(path, editor="cat")
        mock_run.assert_called_once_with(["cat", str(path.absolute())], check=True)

    def test_editor_from_visual_env(self, mocker: MockerFixture) -> None:
        """VISUAL environment variable is preferred when editor is None."""
        mocker.patch.dict(os.environ, {"VISUAL": "nano"}, clear=True)
        mock_run = mocker.patch("ropeway_cli.lib.actions_local.subprocess.run")
        path = pathlib.Path("/tmp/test.txt")
        edit_file(path, editor=None)
        mock_run.assert_called_once_with(["nano", str(path.absolute())], check=True)

    def test_editor_from_editor_fallback(self, mocker: MockerFixture) -> None:
        """EDITOR environment variable is used when VISUAL is not set."""
        mocker.patch.dict(os.environ, {"EDITOR": "emacs"}, clear=True)
        mock_run = mocker.patch("ropeway_cli.lib.actions_local.subprocess.run")
        path = pathlib.Path("/tmp/test.txt")
        edit_file(path, editor=None)
        mock_run.assert_called_once_with(["emacs", str(path.absolute())], check=True)

    def test_default_editor_fallback(self, mocker: MockerFixture) -> None:
        """'vim' is used as the default when neither VISUAL nor EDITOR are set."""
        mocker.patch.dict(os.environ, {}, clear=True)
        mock_run = mocker.patch("ropeway_cli.lib.actions_local.subprocess.run")
        path = pathlib.Path("/tmp/test.txt")
        edit_file(path, editor=None)
        call_args = mock_run.call_args[0][0]
        assert "vim" in call_args[0]
        assert str(path.absolute()) in call_args


class TestConstructLocalPath:
    """Tests for construct_local_path: remote-to-local path translation."""

    def test_absolute_path_inside_remote_base(self, mocker: MockerFixture) -> None:
        """Child of remote_base maps to its local_base counterpart."""
        host_conf: dict[str, str] = {
            "remote_base_path": "/remote/proj",
            "local_base_path": "/home/user/proj",
        }
        mocker.patch("ropeway_cli.lib.actions_local.os.getcwd", return_value="/home/user")
        result = construct_local_path("/remote/proj/sub/file.txt", host_conf)
        assert result == pathlib.Path("/home/user/proj/sub/file.txt")

    def test_absolute_path_equals_remote_base(self) -> None:
        """Path matching remote_base exactly maps to local_base."""
        host_conf: dict[str, str] = {
            "remote_base_path": "/remote/proj",
            "local_base_path": "/home/user/proj",
        }
        result = construct_local_path("/remote/proj", host_conf)
        assert result == pathlib.Path("/home/user/proj")

    def test_absolute_path_outside_remote_base(self) -> None:
        """Path outside remote_base is returned unchanged."""
        host_conf: dict[str, str] = {
            "remote_base_path": "/remote/proj",
            "local_base_path": "/home/user/proj",
        }
        result = construct_local_path("/other/path", host_conf)
        assert result == pathlib.Path("/other/path")

    def test_relative_path(self, mocker: MockerFixture) -> None:
        """Relative path is resolved against CWD via realpath before mapping."""
        host_conf: dict[str, str] = {
            "remote_base_path": "/remote/proj",
            "local_base_path": "/home/user/proj",
        }
        mocker.patch("ropeway_cli.lib.actions_local.os.getcwd", return_value="/home/user")
        result = construct_local_path("relative/file.txt", host_conf)
        assert result == pathlib.Path(
            "/home/user/relative/file.txt"
        )  # NOTE: this points towards possibly unintuitive behavior of construct_local_path!

    def test_absolute_path_with_trailing_slashes(self) -> None:
        """Trailing slashes in config keys are stripped before comparison."""
        host_conf: dict[str, str] = {
            "remote_base_path": "/remote/proj/",
            "local_base_path": "/home/user/proj/",
        }
        result = construct_local_path("/remote/proj/file.txt", host_conf)
        assert result == pathlib.Path("/home/user/proj/file.txt")


class TestDefaultConfig:
    """Tests for default.py: verifying configuration constants."""

    def test_host_config_is_absolute_expanded_path(self) -> None:
        """HOST_CONFIG is an absolute path with ~ fully expanded."""
        from ropeway_cli.lib.default import HOST_CONFIG

        assert os.path.isabs(HOST_CONFIG)
        assert "~" not in HOST_CONFIG
