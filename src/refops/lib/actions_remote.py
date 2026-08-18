#
#  actions_remote.py
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

"""Remote file operations over SSH via Fabric.

This module implements the remote-side actions for refops CLI commands.
Each public function wraps one or more Fabric / invoke calls to perform
a file operation (list, copy, compress, tail, etc.) on a remote host.

Paths are translated between local and remote using the host
configuration's ``local_base_path`` and ``remote_base_path`` mappings.
"""

import os
import pathlib
import shlex
import subprocess
from typing import Any

import fabric
import invoke
from rich_click import style

from refops.lib import actions_local


def _construct_path(path: str, host_conf: dict[str, Any]) -> str:
    """Convert a local path to its remote equivalent.

    Resolves the local path to an absolute canonical form via
    `os.path.realpath`, then substitutes the local base path
    prefix with the remote base path prefix.

    Args:
        path: Local filesystem path to convert.
        host_conf: Host configuration dictionary containing the keys
            ``"local_base_path"`` and ``"remote_base_path"``.

    Returns:
        The corresponding remote path string.
    """

    full_path = os.path.realpath(path)
    local_base = host_conf["local_base_path"].rstrip("/")
    remote_base = host_conf["remote_base_path"].rstrip("/")

    if full_path == local_base:
        return remote_base
    if full_path.startswith(local_base + "/"):
        return remote_base + full_path[len(local_base) :]
    return full_path


def remote_fetch(
    conn: fabric.Connection,
    host_conf: dict[str, Any],
    path: str,
    temp_path: pathlib.Path,
    *,
    confirm_overwrite: bool = True,
):
    """Download a remote file to a local path.

    Translates the given path to an absolute remote path using the host
    configuration, then downloads the file via the Fabric connection.

    Args:
        conn: Active Fabric SSH connection to the remote host.
        host_conf: Host configuration dict containing ``local_base_path``
            and ``remote_base_path``.
        path: Source path on the remote host (absolute or relative).
        temp_path: Local destination path for the downloaded file.
        confirm_overwrite: If ``True`` (default), prompt the user before
            overwriting an existing local file.

    Raises:
        FileNotFoundError: The remote file does not exist, or the local
            temporary file was not created after the download.
    """
    remote_path = _construct_path(path, host_conf)

    if confirm_overwrite and temp_path.exists():
        print(
            style(
                f"WARNING: local file {temp_path} exists!",
                fg="red",
                bg="white",
            )
        )
        print(f"Overwrite local file: '{temp_path}'? [y/n]")
        resp = input()
        if resp.lower() not in ["y", "yes"]:
            return

    try:
        conn.get(remote_path, str(temp_path.absolute()))
    except FileNotFoundError as exc:
        raise FileNotFoundError(
            f"ERROR: Could not find file {remote_path} on host {host_conf["hostname"]}"
        ) from exc

    if not os.path.isfile(temp_path):
        raise FileNotFoundError(f"Temporary file not found: {temp_path}!")


def remote_put(
    conn: fabric.Connection,
    host_conf: dict[str, Any],
    path: str,
    local_path: pathlib.Path,
    *,
    confirm_overwrite: bool = True,
):
    """Upload a local file to a remote path.

    Translates the given destination path to an absolute remote path using
    the host configuration, then uploads the file via the Fabric connection.

    Args:
        conn: Active Fabric SSH connection to the remote host.
        host_conf: Host configuration dict containing ``local_base_path``
            and ``remote_base_path``.
        path: Destination path on the remote host (absolute or relative).
        local_path: Path of the local file to upload.
        confirm_overwrite: If ``True`` (default), prompt the user before
            overwriting an existing remote file.

    Raises:
        FileNotFoundError: The local file does not exist.
    """
    remote_path = _construct_path(path, host_conf)

    if confirm_overwrite and _file_exists(conn, remote_path):
        print(
            style(
                f"WARNING: file {remote_path} exists on {host_conf["hostname"]}",
                fg="red",
                bg="white",
            )
        )
        print(f"Overwrite remote file: '{remote_path}'? [y/n]")
        resp = input()
        if resp.lower() not in ["y", "yes"]:
            return
    try:
        conn.put(local_path.absolute(), remote_path)
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"Could not find file {local_path} on local computer!") from exc


def ls(conn: fabric.Connection, path: str, host_conf: dict[str, Any], ls_args: str):
    """List the contents of a remote directory.

    Translates the given path to an absolute remote path using the host
    configuration, then runs ``ls`` with the specified arguments on the
    remote host.

    Args:
        conn: Active Fabric SSH connection to the remote host.
        path: Remote directory path (absolute or relative).
        host_conf: Host configuration dict containing ``local_base_path``
            and ``remote_base_path``.
        ls_args: Arguments to pass to the remote ``ls`` command
            (e.g. ``"-lAh --color=auto"``).
    """
    path_abs = _construct_path(path, host_conf)

    _run_cmd(conn, f"ls {ls_args} {shlex.quote(path_abs)}", pty=True)


def mkdir(conn: fabric.Connection, host_conf: dict[str, Any], path: str):
    """Create a directory on the remote host.

    Translates the given path to an absolute remote path using the host
    configuration, then runs ``mkdir -p`` to create the directory and any
    missing parent directories.

    When ``path`` is ``"."``, the basename of the current working directory
    is used as the directory name and the local working directory is changed
    to the parent.

    Args:
        conn: Active Fabric SSH connection to the remote host.
        host_conf: Host configuration dict containing ``local_base_path``
            and ``remote_base_path``.
        path: Remote directory path (absolute or relative). Use ``"."`` to
            create a directory with the same name as the current local
            directory.
    """
    if path == ".":
        path = os.path.basename(os.getcwd())
        os.chdir("../")

    path_abs = _construct_path(path, host_conf)
    _run_cmd(conn, f"mkdir -p {shlex.quote(path_abs)}")


def sync_cwd(
    conn: fabric.Connection,
    host_conf: dict[str, Any],
    rsync_args: str,
    from_remote: bool,
):
    """Synchronize the current local directory with a remote directory.

    Uses ``rsync`` over SSH to bidirectionally sync the current working
    directory with its counterpart on the remote host. Path translation
    uses the host configuration's ``local_base_path`` and
    ``remote_base_path``.

    By default the sync is push (local -> remote).  Set
    ``from_remote`` to reverse the direction.

    The remote directory is created automatically if it does not exist
    (only for local -> remote syncs).

    Args:
        conn: Active Fabric SSH connection to the remote host.
        host_conf: Host configuration dict containing ``local_base_path``
            and ``remote_base_path``.
        rsync_args: Arguments forwarded to the ``rsync`` command
            (e.g. ``"-auvzPh --stats"``).
        from_remote: If ``True``, sync from remote to local instead of
            local to remote.
    """
    local_path = os.getcwd()
    if local_path.rstrip("/") == host_conf["local_base_path"].rstrip("/"):
        remote_path = host_conf["remote_base_path"]
    else:
        remote_path = _construct_path(".", host_conf)

    print(local_path, remote_path)
    local_path = str(pathlib.Path(local_path).absolute())
    if not from_remote:
        mkdir(conn, host_conf, remote_path)
        _rsync(host_conf["hostname"], local_path, remote_path, rsync_args)
    else:
        _rsync(host_conf["hostname"], remote_path, local_path, rsync_args, src_is_remote=True)


def _rsync(hostname: str, src: str, dest: str, args: str, src_is_remote: bool = False):
    """Synchronize files between local and remote hosts via ``rsync``.

    Normalizes the source and destination paths by ensuring trailing
    slashes, then prepends ``hostname:`` to the remote side based on
    the ``src_is_remote`` flag.

    Args:
        hostname: Remote hostname (or SSH alias) to use.
        src: Source path (local or remote file/directory).
        dest: Destination path (local or remote file/directory).
        args: Extra arguments passed to the ``rsync`` command
            (default: ``"-auvzPh --stats"``).
        src_is_remote: If ``True``, treat ``src`` as a remote path;
            otherwise treat ``dest`` as remote (default: ``False``).
    """

    src = f"{src.rstrip("/")}/"
    dest = f"{dest.rstrip("/")}/"

    if src_is_remote:
        src = f"{hostname}:{src}"
    else:
        dest = f"{hostname}:{dest}"

    subprocess.run(
        ["rsync"] + shlex.split(args) + ["--", src, dest], check=True
    )  # "--" prevents src/dest from being interpreted as rsync flags


def find(
    conn: fabric.Connection,
    host_conf: dict[str, Any],
    find_cmd: str,
    find_args: str,
    expr: str | None = None,
) -> list[str] | None:
    """Search for files on the remote host.

    Changes to the resolved remote working directory and runs a file
    search command, returning matching paths as a list.

    The available backends must be installed on the remote host:

    * ``"find"`` - the standard POSIX ``find`` utility
    * ``"fd"`` / ``"rust_find"`` - `fd <https://github.com/sharkdp/fd>`

    Args:
        conn: Active Fabric SSH connection to the remote host.
        host_conf: Host configuration dict containing ``local_base_path``
            and ``remote_base_path``.
        find_cmd: Name of the search backend to use. One of ``"find"``,
            ``"fd"``, or ``"rust_find"``.
        find_args: Arguments forwarded to the search backend
            (e.g. ``"-maxdepth 2 -name '*.py'"``).
        expr: Optional search expression or pattern. Appended to the
            command for backends that support it.

    Returns:
        List of matching file paths, or ``None`` if no results.

    Raises:
        NotImplementedError: If ``find_cmd`` is not a supported backend.
    """
    remote_path = _construct_path(".", host_conf)

    if expr is None:
        expr = ""

    with conn.cd(remote_path):
        match find_cmd:
            case "find":
                if expr:
                    print(
                        style(
                            "WARNING: EXPR argument not used with 'find'! Use --args instead!",
                            fg="red",
                            bg="white",
                        )
                    )
                results = conn.run(f"find . {find_args}", hide=True)
            case "fd" | "rust_find":
                results = conn.run(f"fd {find_args} {expr} .", hide=True)
            case _:
                raise NotImplementedError(f"Functionality for {find_cmd} not yet implemented!")

    if results.stdout == "":
        return None
    return results.stdout.split("\n")


def realpath(conn: fabric.Connection, host_conf: dict[str, Any], path: str, show_type: bool) -> str:
    """Resolve the absolute remote path of a file or directory.

    Translates the given path using the host configuration and optionally
    prefixes the result with the file type (e.g. ``"regular file"``,
    ``"directory"``).

    Args:
        conn: Active Fabric SSH connection to the remote host.
        host_conf: Host configuration dict containing ``local_base_path``
            and ``remote_base_path``.
        path: Remote path to resolve (absolute or relative).
        show_type: If ``True``, prepend the file type (padded to 15
            characters) to the returned path.

    Returns:
        The resolved absolute remote path as a string.  When
        ``show_type`` is ``True`` the format is
        ``"<type>          <path>"``.
    """
    remote_path = _construct_path(path, host_conf)

    if show_type:
        file_type = _get_file_type(conn, remote_path)
        return f"{file_type:15} {remote_path}"
    return remote_path


def _get_file_type(conn: fabric.Connection, path: str) -> str:
    """Determine the remote file type of a path via ``stat``.

    Runs ``stat -c %F`` on the remote host to obtain the file type
    (e.g. ``"regular file"``, ``"directory"``, ``"symbolic link"``).
    If the path does not exist or the command fails, returns
    ``"unknown"``.

    Args:
        conn: An active Fabric connection to the remote host.
        path: Remote path to query.

    Returns:
        A string describing the file type as reported by ``stat``, or
        ``"unknown"`` if the path cannot be stat'ed.
    """
    try:
        result = conn.run(f"stat -c %F {shlex.quote(path)}", hide=True)
        file_type = result.stdout.strip()
    except invoke.exceptions.UnexpectedExit:
        file_type = "unknown"
    return file_type


def compress(
    conn: fabric.Connection,
    host_conf: dict[str, Any],
    cmp_cmd: str,
    cmp_args: str,
    files: list[str],
):
    """Compress files on the remote host using a command-line tool.

    Changes to the resolved remote working directory and runs the
    specified compression command on the given list of files.

    Args:
        conn: Active Fabric SSH connection to the remote host.
        host_conf: Host configuration dict containing ``local_base_path``
            and ``remote_base_path``.
        cmp_cmd: Compression program to use (e.g. ``"bzip2"``, ``"gzip"``).
            Must be available on the remote host.
        cmp_args: Additional arguments to pass to the compression program
            (e.g. ``"-v"``).
        files: List of file paths (relative to the remote working
            directory) to compress.
    """
    remote_path = _construct_path(".", host_conf)
    with conn.cd(remote_path):
        cmd = f"{cmp_cmd} {cmp_args} {" ".join(files)}"
        _run_cmd(conn, cmd)


def delete_file(conn: fabric.Connection, host_conf: dict[str, Any], path: str):
    """Delete a file on the remote host with interactive confirmation.

    Resolves the remote path, verifies it is a regular file (not a
    directory or unknown type), and prompts the user to confirm before
    running ``rm``.

    Args:
        conn: Active Fabric SSH connection to the remote host.
        host_conf: Host configuration dict containing ``local_base_path``
            and ``remote_base_path``.
        path: Remote path to delete (absolute or relative).

    Raises:
        ValueError: If the resolved path is a directory or its type
            cannot be determined.
    """
    remote_path = _construct_path(path, host_conf)
    file_type = _get_file_type(conn, remote_path)
    if file_type not in ["regular file", "symbolic link", "regular empty file"]:
        raise ValueError("ERROR: Path is not a file or link! Cannot delete it!")

    print(f"Delete remote file: '{remote_path}'? [y/n]")
    resp = input()
    if resp.lower() in ["y", "yes"]:
        print(f"Deleting file {remote_path}")
        _run_cmd(conn, f"rm {shlex.quote(remote_path)}")


def tail(conn: fabric.Connection, host_conf: dict[str, Any], tail_f: bool, filename: str):
    """Display the last part of a remote file.

    Resolves the remote path and runs ``tail`` on the remote host.
    Output is streamed directly to the terminal.

    Args:
        conn: Active Fabric SSH connection to the remote host.
        host_conf: Host configuration dict containing ``local_base_path``
            and ``remote_base_path``.
        tail_f: If ``True``, pass ``-f`` to ``tail`` for continuous
            follow-mode monitoring.
        filename: Path to the remote file (absolute or relative).
    """
    remote_file = _construct_path(filename, host_conf)

    if tail_f:
        cmd = f"tail -f {shlex.quote(remote_file)}"
    else:
        cmd = f"tail {shlex.quote(remote_file)}"

    _run_cmd(conn, cmd)


def copy(conn: fabric.Connection, host_conf: dict[str, Any], src: str, dest: str):
    """Copy a file or directory on the remote host.

    Resolves both source and destination paths using the host
    configuration, then runs ``cp`` on the remote host.

    Args:
        conn: Active Fabric SSH connection to the remote host.
        host_conf: Host configuration dict containing ``local_base_path``
            and ``remote_base_path``.
        src: Source path on the remote host (absolute or relative).
        dest: Destination path on the remote host (absolute or relative).
    """
    remote_src = _construct_path(src, host_conf)
    remote_dest = _construct_path(dest, host_conf)
    print(f"Copy {remote_src} to {remote_dest}")
    _run_cmd(conn, f"cp {shlex.quote(remote_src)} {shlex.quote(remote_dest)}")


def run(conn: fabric.Connection, host_conf: dict[str, Any], cmd: str, directory: str):
    """Run a command on a remote host in the specified directory.

    If ``cmd`` starts with ``@``, it is treated as an alias key and
    looked up in the host configuration (e.g. ``@build`` → the build
    command defined for that host).  The remote directory is resolved
    via :func:`_construct_path` and verified to exist before execution.

    Args:
        conn: An active Fabric connection to the remote host.
        host_conf: Host configuration dictionary.
        cmd: The shell command to execute, or an ``@alias`` defined in
            ``host_conf``.
        directory: The remote working directory in which to run the
            command.

    Raises:
        ValueError: If the remote directory does not exist or is not a
            directory.
    """
    fg_dir = "green"
    if cmd.startswith("@"):
        if cmd not in host_conf:
            raise ValueError(f"Alias '{cmd}' not found in host configuration!")
        cmd = host_conf[cmd]
        if isinstance(cmd, list):
            cmd, directory = cmd[0], cmd[1]
            fg_dir = "red"

    remote_path = _construct_path(directory, host_conf)
    remote_path_type = _get_file_type(conn, remote_path)

    if remote_path_type != "directory":
        raise ValueError(
            f"ERROR: Directory {remote_path} does not exist on remote host! Cannot run: {cmd}!"
        )

    with conn.cd(remote_path):
        # print(f"Running command on host {host_conf["hostname"]} in {remote_path}: {cmd} ")
        print(
            """Running command on host """
            f"""{style(host_conf["hostname"], bold=True, fg="blue")}"""
            f""" in {style(remote_path, bold=True, fg=fg_dir)}: {cmd} """
        )

        _run_cmd(conn, cmd)


def _run_cmd(conn: fabric.Connection, cmd: str, pty: bool = False):
    """Execute a shell command on the remote host.

    Runs the given command string via the Fabric connection with
    ``warn=True`` so that non-zero exit codes do not raise an exception automatically.

    Args:
        conn: Active Fabric SSH connection to the remote host.
        cmd: Shell command string to execute.

    Raises:
        ValueError: If the command exits with a non-zero exit code.
    """

    if (exit_code := conn.run(cmd, warn=True, pty=pty).exited) != 0:
        msg = f"WARNING: command '{cmd}' terminated with exit code {exit_code}!"
        msg += " Please check output of command carefully!"
        raise ValueError(msg)


def diff(
    conn: fabric.Connection,
    host_conf: dict[str, Any],
    path_1: str,
    path_2: str,
    diff_cmd: str,
    diff_args: str,
    local: bool,
) -> int:
    # pylint: disable=too-many-arguments,too-many-positional-arguments
    """Compare two remote files.

    By default runs the diff command directly on the remote host.  When
    ``local`` is ``True``, downloads both files to temporary local paths
    and runs the diff command locally.

    When ``diff_cmd`` is anything other than ``"diff"``, the files are
    always downloaded and diffed locally regardless of the ``local``
    flag, since proper remote execution cannot be guaranteed.

    Args:
        conn: Active SSH connection.
        host_conf: Host configuration from hosts.json.
        path_1: First remote path.
        path_2: Second remote path.
        diff_cmd: Diff program to use (e.g. "diff", "vimdiff").
        diff_args: Extra arguments for the diff command.
        local: If True, download files and diff locally; otherwise run
            remotely.

    Returns:
        Exit code of the diff command (0 = identical, 1 = different).
    """
    if diff_cmd.strip() != "diff":
        print(
            f"""INFO: Running {diff_cmd} locally, as proper remote function cannot be guaranteed"""
            """for anything other than 'diff'!"""
        )
        local = (
            True  # at this point, it cannot be guaranteed that anything else runs properly remotely
        )
    remote_path_1 = _construct_path(path_1, host_conf)
    remote_path_2 = _construct_path(path_2, host_conf)
    exit_code = -1

    run_diff = [diff_cmd]
    if diff_args:
        run_diff.append(diff_args)

    if local:
        tmp_1 = actions_local.create_tmp_file(pathlib.Path(remote_path_1).suffix)
        tmp_2 = actions_local.create_tmp_file(pathlib.Path(remote_path_2).suffix)

        try:
            remote_fetch(conn, host_conf, remote_path_1, tmp_1)
            remote_fetch(conn, host_conf, remote_path_2, tmp_2)

            try:
                res = subprocess.run(run_diff + [tmp_1, tmp_2], check=False)
            except FileNotFoundError as exc:
                raise FileNotFoundError(f"{diff_cmd} not found!") from exc
            exit_code = res.returncode
        finally:
            _diff_local_cleanup([tmp_1, tmp_2])

    else:
        run_diff = shlex.join(run_diff + [remote_path_1, remote_path_2])  # type: ignore
        res = conn.run(run_diff, pty=True, warn=True)
        exit_code = res.exited
    return exit_code


def _diff_local_cleanup(tmp_files: list[pathlib.Path]):
    """Remove temporary files created during a local diff.

    Args:
        tmp_files: List of temporary file paths to remove.
    """
    for tmp in tmp_files:
        actions_local.remove_tmp_file(tmp)


def _file_exists(conn, remote_path) -> bool:
    """Check whether a file exists on the remote host.

    Runs ``test -f`` on the remote host to determine if the given path
    points to an existing regular file.

    Args:
        conn: Active Fabric SSH connection to the remote host.
        remote_path: Absolute path to check on the remote host.

    Returns:
        ``True`` if the remote path exists and is a regular file,
        ``False`` otherwise.
    """
    res = conn.run(f"test -f {shlex.quote(remote_path)}", warn=True)
    return res.ok
