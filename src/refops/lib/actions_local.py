#  actions_local.py
#
#  Copyright 2026 Berni <berni@sciencemachine>
#
#  This program is free software; you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation; either version 2 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software
#  Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston,
#  MA 02110-1301, USA.
#
#

"""This module provides helper functions for common local file operations"""

import json
import os
import pathlib
import subprocess
import tempfile
from typing import Any

from .default import HOST_CONFIG


def load_host(host: str, host_file: str | None = None) -> dict[str, Any]:
    """Load the configuration for a remote host.

    Reads the JSON hosts file and returns the entry for the given host.
    Defaults to the path stored in defaults.HOST_CONFIG (default: ``~/.config/refops/hosts.json``)
    when no file is specified.

    Args:
        host: Name of the host to load. Must match a key in the hosts
            file.
        host_file: Optional path to a custom hosts JSON file. If not
            provided, the default path is used.

    Returns:
        Dictionary containing the host configuration entries (e.g.
        ``local_base_path``, ``remote_base_path``, ``@alias`` commands).

    Raises:
        KeyError: If ``host`` is not found in the hosts file.
    """
    if host_file is None:
        path = pathlib.Path(HOST_CONFIG)
    else:
        path = pathlib.Path(host_file)

    with open(path.absolute(), "rt", encoding="utf-8") as hosts_file:
        hosts = json.load(hosts_file)

    if host not in hosts:
        raise KeyError(f"Host {host} not found in hosts file: {path}")

    return hosts[host]


def determine_suffix(path: str) -> str:
    """Determine the file extension of a given path.

    Args:
        path: Filesystem path to extract the suffix from.

    Returns:
        The file extension including the leading dot (e.g. ``.txt``),
        or an empty string if the path has no extension.
    """
    return pathlib.Path(path).suffix


def create_tmp_file(suffix: str) -> pathlib.Path:
    """Create a temporary file with the given suffix.

    The file is not deleted when the temporary file object is closed
    (``delete=False``), allowing the caller to use it beyond this
    function's scope.

    Args:
        suffix: The file extension to append (e.g. ``.txt``).

    Returns:
        A ``pathlib.Path`` pointing to the created temporary file.
    """
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp_file:
        temp_path = tmp_file.name
    return pathlib.Path(temp_path)


def remove_tmp_file(temp_path: pathlib.Path):
    """Safely remove a temporary file.

    Checks whether the file exists before attempting deletion to avoid
    raising ``FileNotFoundError``.

    Args:
        temp_path: Path to the temporary file to remove.
    """
    if os.path.exists(temp_path):
        os.remove(temp_path)


def edit_file(path: pathlib.Path, editor: str | None = None):
    """Open a file in an external text editor.

    The editor defaults to the ``VISUAL`` environment variable, falling
    back to ``EDITOR``, then to ``vim``.

    Args:
        path: The file to edit.
        editor: The editor command (and any flags) to use.
            If ``None``, the editor is resolved from environment
            variables as described above.

    Raises:
        subprocess.CalledProcessError: If the editor exits with a
            non-zero return code.
    """

    if editor is None:
        editor = (
            os.environ.get("VISUAL") or os.environ.get("EDITOR") or "vim -c 'set backupcopy=yes'"
        )

    subprocess.run([editor, str(path.absolute())], check=True)


def construct_local_path(path: str, host_conf: dict[str, Any]) -> pathlib.Path:
    """Convert a filesystem path to its local equivalent for the given host.

    If ``path`` is absolute, its remote base prefix is replaced with the
    corresponding local base path. If it is relative, it is joined with
    the current working directory.

    Args:
        path: The path to convert (may be absolute or relative).
        host_conf: Host configuration dictionary that must contain the
            keys ``"remote_base_path"`` and ``"local_base_path"``.

    Returns:
        A ``pathlib.Path`` representing the local equivalent of the
        input path.
    """

    if os.path.isabs(path):
        remote_base = host_conf["remote_base_path"].rstrip("/")
        local_base = host_conf["local_base_path"].rstrip("/")
        if path == remote_base:
            return pathlib.Path(local_base)
        if path.startswith(remote_base + "/"):
            return pathlib.Path(local_base + path[len(remote_base) :])
        return pathlib.Path(path)

    cwd = os.getcwd()
    return pathlib.Path(os.path.join(cwd, path))
