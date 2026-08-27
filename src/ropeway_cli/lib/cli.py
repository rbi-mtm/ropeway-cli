#
# Copyright (c) 2026 bernik86.
#
# This file is part of ropeway-cli
# (see https://github.com/rbi-mtm/ropeway-cli).
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

"""CLI definitions for ropeway-cli using rich-click."""

import pathlib
import shlex

import fabric
import rich_click as click

from . import actions_local
from . import actions_remote
from .default import HELP_MAX_WIDTH
from .default import HOST_CONFIG
from .default import THEME


@click.group(
    "cli",
    context_settings={"help_option_names": ["-h", "--help"], "show_default": True},
    invoke_without_command=True,
)
@click.pass_context
@click.rich_config(help_config={"theme": THEME, "max_width": HELP_MAX_WIDTH})
@click.option("-H", "--host", required=True)
def cli(ctx, host: str):
    """ropeway-cli: Remote file operations over SSH

    This is a collection of commands used for remote file operations.
    It leverages the fabric module to perform file actions on a remote
    computer.

    When invoked without a subcommand the help screen is displayed.
    On successful invocation the host configuration is loaded from
    ``~/.config/ropeway-cli/hosts.json`` and a Fabric SSH connection is
    established, both stored in the Click context for use by
    subcommands.
    """

    if not pathlib.Path(HOST_CONFIG).exists():
        click.echo(
            click.style(
                f"ERROR: {HOST_CONFIG} does not exist!"
                " Create proper file (see README.md) and run ropeway-cli again!",
                fg="red",
                bg="white",
            )
        )
        return

    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())
        return

    ctx.ensure_object(dict)
    ctx.obj["host_conf"] = actions_local.load_host(host, HOST_CONFIG)
    ctx.obj["host_conf"]["hostname"] = host
    ctx.obj["conn"] = fabric.Connection(host)


@cli.command(
    short_help="""List content of directory. Path of directory is given as last argument.
    If a relative path is given, local_base_path and remote_base_path defined in the hosts.json
    file are used to determine the absolute path of the file or directory specified.""",
    context_settings={"show_default": True},
)
@click.argument("path", default=".")
@click.option("--args", default="-lAh --color=auto", help="Arguments for ls command")
@click.pass_context
def ls(ctx, path, args):
    """List the contents of a remote directory.

    Delegates to the remote machine's ``ls`` command. Relative paths
    are translated using the host configuration's path mapping.
    """
    try:
        actions_remote.ls(ctx.obj["conn"], path, ctx.obj["host_conf"], args)
    except ValueError as exc:
        click.echo(click.style(exc, fg="red", bg="white"))


@cli.command(short_help="View remote file.")
@click.argument("path")
@click.option("--editor", help="Set editor manually, otherwise system default will be used.")
@click.option("--write", is_flag=True, help="If set, file will be written back to remote host.")
@click.option(
    "--new",
    is_flag=True,
    help="If set, create new file and write to remote host (no need to set --write flag).",
)
@click.pass_context
def view(ctx, path, editor, write, new):
    """Fetch a remote file, edit it locally, and optionally write it back.

    Downloads the remote file to a temporary location, opens it in the
    local editor, and uploads the modified version if requested. Can
    also create a new remote file from scratch with ``--new``.
    """
    suffix = actions_local.determine_suffix(path)
    tmp_path = actions_local.create_tmp_file(suffix)

    if not new:
        try:
            # confirm_overwrite=False is safe here because path is always downloaded to a tmp file
            actions_remote.remote_fetch(
                ctx.obj["conn"], ctx.obj["host_conf"], path, tmp_path, confirm_overwrite=False
            )
        except FileNotFoundError as exc:
            click.echo(click.style(exc, fg="red", bg="white"))
            actions_local.remove_tmp_file(tmp_path)
            return

    actions_local.edit_file(tmp_path, editor)
    if write or new:
        actions_remote.remote_put(ctx.obj["conn"], ctx.obj["host_conf"], path, tmp_path)
    actions_local.remove_tmp_file(tmp_path)


@cli.command(short_help="Copy remote file to local machine.")
@click.option("--overwrite", "overwrite", is_flag=True, help="Overwrite local file without asking.")
@click.argument("filename")
@click.pass_context
def get(ctx, filename, overwrite):
    """Download a remote file to the local machine.

    Translates the remote filename to a corresponding local path using the
    host configuration and downloads the file.
    """
    local_path = actions_local.construct_local_path(filename, ctx.obj["host_conf"])
    actions_remote.remote_fetch(
        ctx.obj["conn"], ctx.obj["host_conf"], filename, local_path, confirm_overwrite=not overwrite
    )


@cli.command(short_help="Copy local file to remote machine.")
@click.option(
    "--overwrite", "overwrite", is_flag=True, help="Overwrite remote file without asking."
)
@click.argument(
    "filename",
)
@click.pass_context
def put(ctx, filename, overwrite):
    """Upload a local file to the remote machine.

    Translates the local filename to a corresponding remote path using the
    host configuration and uploads the file.
    """
    local_path = actions_local.construct_local_path(filename, ctx.obj["host_conf"])
    actions_remote.remote_put(
        ctx.obj["conn"], ctx.obj["host_conf"], filename, local_path, confirm_overwrite=not overwrite
    )


@cli.command(short_help="Make directory on remote host")
@click.argument("path", default=".")
@click.pass_context
def mkdir(ctx, path):
    """Create a directory on the remote host.

    Creates the directory and any missing parent directories. When no
    path is given, uses the name of the current local working directory.
    """
    try:
        actions_remote.mkdir(ctx.obj["conn"], ctx.obj["host_conf"], path)
    except ValueError as exc:
        click.echo(click.style(exc, fg="red", bg="white"))


@cli.command(short_help="Sync data from current directory to cluster (or vice versa).")
@click.option(
    "--args",
    "rsync_args",
    default="-auvzPh --stats --include='Input/**' --include='Input/' --exclude='*/'",
    help="Arguments for rsync command",
)
@click.option("--from", "from_remote", is_flag=True, help="Sync dir from remote to local.")
@click.pass_context
def sync_cwd(ctx, rsync_args, from_remote):
    """Synchronize the current directory with the remote host via rsync.

    By default syncs from local to remote.  Use ``--from`` to reverse
    the direction. The remote directory is created automatically if it
    does not exist. Use ``--args`` to specify additional arguments for
    rsync. By default, only files in the current working directory and
    a folder called Input/ (if it exists) are synced.
    """
    actions_remote.sync_cwd(ctx.obj["conn"], ctx.obj["host_conf"], rsync_args, from_remote)


@cli.command(short_help="Find files remotely")
@click.option("--use", "find_cmd", default="fd", help="Find command used for finding files")
@click.option("--args", "find_args", default="", help="Arguments for find command")
@click.option("--full-path", "full_path", is_flag=True, help="Show full path of found files")
@click.option("--show-type", "show_type", is_flag=True, help="Show type of file or directory")
@click.argument("expr", required=False)
@click.pass_context
def find(ctx, find_cmd, find_args, full_path, show_type, expr):
    # pylint: disable=too-many-arguments,too-many-positional-arguments
    """Search for files on the remote host.

    Runs a file search backend (``find`` or ``fd``) on the remote host
    and displays matching paths. Optionally resolves full paths and
    shows the file type.
    """
    files = actions_remote.find(ctx.obj["conn"], ctx.obj["host_conf"], find_cmd, find_args, expr)
    if files is None:
        click.echo("No files found!")
        return

    for f in files:
        if not f:
            continue
        if full_path:
            click.echo(actions_remote.realpath(ctx.obj["conn"], ctx.obj["host_conf"], f, show_type))
        else:
            msg = f"{f}"
            if show_type:
                # pylint: disable=protected-access
                file_type = actions_remote._get_file_type(
                    ctx.obj["conn"], actions_remote._construct_path(f, ctx.obj["host_conf"])
                )
                # pylint: enable=protected-access
                msg = f"{file_type:15} {f}"
            click.echo(msg)


@cli.command(short_help="Get full path of remote file or directory")
@click.argument("path")
@click.option("--show-type", "show_type", is_flag=True, help="Show type of file or directory")
@click.pass_context
def realpath(ctx, path, show_type):
    """Resolve the absolute path of a remote file or directory.

    Translates the given path using the host configuration and displays
    the result. Optionally prefixes the output with the file type.
    """
    path = actions_remote.realpath(ctx.obj["conn"], ctx.obj["host_conf"], path, show_type)
    click.echo(path)


@cli.command(short_help="Compress files in a directory.")
@click.option(
    "--use",
    "use",
    default="bzip2",
    help="Select program for compressing (must be available on the remote host).",
)
@click.option(
    "--exclude",
    "exclude",
    default="*png *jpg *jpeg *pdf *gz2 *bz2 *zip *kp *bak *bak-1 *wfn */Input/*",
    help="Patterns to exclude files.",
)
@click.option(
    "--only-cwd", "only_cwd", is_flag=True, help="Only compress file in current directory"
)
@click.option("--verbose", "verbose", is_flag=True, help="Show more information.")
@click.pass_context
def compress(ctx, use, exclude, only_cwd, verbose):
    """Compress files in a remote directory.

    Finds regular files matching the given criteria on the remote host
    and compresses them using the specified compression tool (e.g.
    ``bzip2``, ``gzip``). Supports excluding files by glob patterns.
    """
    find_args = " -type f "
    if only_cwd:
        find_args = "-maxdepth 1 " + find_args
    if excl := exclude.split():
        for e in excl:
            flag = "-a -not -name"
            if e.endswith("/*"):
                flag = "-a -not -wholename "
            find_args += flag + " " + shlex.quote(e)

    if verbose:
        click.echo(find_args)
    files = actions_remote.find(ctx.obj["conn"], ctx.obj["host_conf"], "find", find_args)

    if files is not None:
        files = list(set(files))
        try:
            actions_remote.compress(ctx.obj["conn"], ctx.obj["host_conf"], use, "", files)
        except ValueError as exc:
            click.echo(click.style(exc, fg="red", bg="white"))


@cli.command(short_help="Delete a file on the remote host.")
@click.argument("path")
@click.pass_context
def delete(ctx, path):
    """Delete a file on the remote host.

    Prompts for confirmation before removing the file. Only regular
    files can be deleted; directories are rejected.
    """
    try:
        actions_remote.delete_file(ctx.obj["conn"], ctx.obj["host_conf"], path)
    except ValueError as exc:
        click.echo(click.style(exc, fg="red", bg="white"))


@cli.command(short_help="Display the last part of a remote file.")
@click.option("-f", "tail_f", is_flag=True, help="Passes -f to tail for continous monitoring")
@click.argument("filename")
@click.pass_context
def tail(ctx, tail_f, filename):
    """Display the last part of a remote file.

    Supports follow mode (``-f``) for continuous monitoring of log
    files (abort using CTRL+C). Output is streamed directly to the terminal.
    """
    try:
        actions_remote.tail(ctx.obj["conn"], ctx.obj["host_conf"], tail_f, filename)
    except ValueError as exc:
        click.echo(click.style(exc, fg="red", bg="white"))


@cli.command(short_help="Copy a file on the remote machine.")
@click.argument("src")
@click.argument("dest")
@click.pass_context
def cp(ctx, src, dest):
    """Copy a file on the remote host.

    Runs ``cp`` on the remote machine, translating both source and
    destination paths using the host configuration.
    """
    try:
        actions_remote.copy(ctx.obj["conn"], ctx.obj["host_conf"], src, dest)
    except ValueError as exc:
        click.echo(click.style(exc, fg="red", bg="white"))


@cli.command(
    short_help="Execute an arbitrary command on the remote host. "
    + click.style("⚠ WARNING: use with care and on your own responsibility!", fg="red", bg="white")
)
@click.option("-D", "directory", default=".", help="Directory in which to run command.")
@click.argument("cmd", required=False)
@click.pass_context
def run(ctx, cmd, directory):
    """Execute an arbitrary command on the remote host.

    Runs the given command string directly on the remote host via SSH.
    The command is run in the current working directory, mapped to the corresponding remote
    directory. Supports ``@alias`` syntax for commands defined in the host
    configuration. \n


    ⚠ WARNING:

        This command executes arbitrary shell commands on a remote
        machine.  There is no sandboxing, no dry-run mode, and no
        validation of the input.  Depending on the command and the
        remote system, this may result in data loss, service
        disruption, security breaches, or other unintended
        consequences.  You are solely responsible for understanding
        what the command does before running it.  Always verify the
        command string, especially when using aliases or interpolating
        values.
    """
    if cmd is None:
        for k in ctx.obj["host_conf"]:
            if k.startswith("@"):
                click.echo(click.style("-" * 80, bold=True, fg="red"))
                click.echo(f"{click.style(k, bold=True, fg='blue')}: {ctx.obj['host_conf'][k]}")
        return

    try:
        actions_remote.run(ctx.obj["conn"], ctx.obj["host_conf"], cmd, directory)
    except ValueError as exc:
        click.echo(click.style(exc, fg="red", bg="white"))


@cli.command(short_help="Compare two remote files (remotely or locally)")
@click.option("--use", "diff_cmd", default="diff", help="diff command used for finding files")
@click.option("--args", "diff_args", default="", help="Arguments for diff command")
@click.option(
    "--local", "local", is_flag=True, help="Download files to temp files and compare locally"
)
@click.argument("path_1")
@click.argument("path_2")
@click.pass_context
def diff(ctx, diff_cmd, diff_args, local, path_1, path_2):
    # pylint: disable=too-many-arguments,too-many-positional-arguments
    """Compare two remote files using a diff tool.

    By default runs the diff command directly on the remote host.
    Use ``--local`` to download the files to temporary locations and
    compare them locally instead (useful when using a graphical diff tool).
    """

    actions_remote.diff(
        ctx.obj["conn"], ctx.obj["host_conf"], path_1, path_2, diff_cmd, diff_args, local
    )
