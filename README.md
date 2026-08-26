# ropeway-cli

**ropeway-cli** is a command-line tool for performing remote file operations over SSH.
It uses [Fabric](https://www.fabfile.org/) under the hood and provides a
convenient Click-based interface for common remote file tasks.

> **⚠ Warning:** ropeway-cli executes commands on remote machines via SSH.
> Use it at your own risk. It has only been tested on Linux (local) communicating with Linux hosts.

## Features

- **ls** — List remote directory contents
- **view** — Fetch a remote file, edit it locally, and write it back
- **get** / **put** — Download / upload files
- **mkdir** — Create remote directories
- **sync_cwd** — Bidirectional `rsync` between current directory and remote
- **find** — Search for files on the remote host (uses [fd](https://github.com/sharkdp/fd) by default; falls back to `find`)
- **realpath** — Resolve the absolute path of a remote file
- **compress** — Compress remote files (bzip2, gzip, etc.)
- **delete** — Remove a remote file (with confirmation)
- **tail** — Tail a remote file (supports `-f`)
- **cp** — Copy a file on the remote machine
- **diff** — Compare two remote files (remotely or locally)
- **run** — Execute arbitrary commands on the remote host

## Installation

The package is not yet on PyPI.  Clone the repository and install
from source.

### Using `uv` (recommended)

```bash
git clone https://github.com/bernik86/ropeway-cli.git
cd ropeway-cli
uv venv
source .venv/bin/activate
uv pip install .
```

### Using `pip`

```bash
git clone https://github.com/bernik86/ropeway-cli.git
cd ropeway-cli
python3 -m venv .venv
source .venv/bin/activate
pip install .
```

After either method, the `ropeway-cli` command is available inside the virtual
environment.

## Configuration

Create `~/.config/ropeway-cli/hosts.json` with one entry per remote host.
The host name (e.g. `"mycluster"`) must match a host defined in your
`~/.ssh/config` file.

```json
{
  "mycluster": {
    "local_base_path": "/home/user/projects",
    "remote_base_path": "/remote/home/user/projects",
    "@mycommand": "some_remote_command --with-flags",
    "@build": ["make && make install", "/remote/home/user/projects/build"]
  }
}
```

| Key | Description |
|---|---|
| `local_base_path` | Base path on the local machine |
| `remote_base_path` | Corresponding base path on the remote machine |
| `@<name>` | Command alias (invoked via `run @<name>`). Can be a string (the command) or a list `["command", "directory"]` to override the working directory. |

## Usage

```
ropeway-cli -H <host> <command> [options] [args]
```

The `-H` / `--host` flag is **required** and must match a key in
`hosts.json`.

### Commands

| Command | Description |
|---|---|
| `ls [PATH]` | List remote directory contents. `--args` to pass options to `ls` |
| `view PATH` | Fetch, edit locally, optionally write back. `--editor`, `--write`, `--new` |
| `get PATH` | Download a remote file. `--overwrite` to skip confirmation |
| `put PATH` | Upload a local file. `--overwrite` to skip confirmation |
| `mkdir [PATH]` | Create a directory on the remote host |
| `sync_cwd` | Sync current directory via `rsync`. `--args` for rsync flags, `--from` for remote→local |
| `find [EXPR]` | Search files via `fd` or `find`. `--use`, `--args`, `--full-path`, `--show-type` |
| `realpath PATH` | Resolve absolute remote path. `--show-type` to prefix file type |
| `compress` | Compress files remotely. `--use` (compressor), `--exclude` (patterns), `--only-cwd` |
| `delete PATH` | Delete a remote file (prompts for confirmation) |
| `tail FILENAME` | Tail a remote file. `-f` for follow mode |
| `cp SRC DEST` | Copy a file on the remote machine |
| `diff PATH_1 PATH_2` | Compare two remote files. `--use` (diff tool), `--args`, `--local` (download and diff locally) |
| `run CMD` | Run an arbitrary command or `@alias` on the remote host. `-D` / `--directory` to set working dir (overridden by alias directory if specified) |

### Examples

```bash
# List remote directory
ropeway-cli -H mycluster ls /remote/path

# Edit a remote file locally and write changes back
ropeway-cli -H mycluster view /remote/path/file.txt --write

# Create a new file on the remote host
ropeway-cli -H mycluster view /remote/path/new.txt --new

# Download a file
ropeway-cli -H mycluster get /remote/path/file.txt
ropeway-cli -H mycluster get --overwrite /remote/path/file.txt

# Upload a file
ropeway-cli -H mycluster put /local/path/file.txt
ropeway-cli -H mycluster put --overwrite /local/path/file.txt

# Sync current directory to remote
ropeway-cli -H mycluster sync_cwd

# Sync from remote to local
ropeway-cli -H mycluster sync_cwd --from

# Find Python files (uses fd by default; install fd on the remote host)
# See https://github.com/sharkdp/fd
ropeway-cli -H mycluster find -e py
ropeway-cli -H mycluster find -e py --full-path --show-type

# Use find backend explicitly
ropeway-cli -H mycluster find --use find --args "-maxdepth 3 -name '*.py'"

# Compress files with gzip, excluding images
ropeway-cli -H mycluster compress --use gzip --exclude "*png *jpg"

# Tail a remote log
ropeway-cli -H mycluster tail /remote/path/log.txt
ropeway-cli -H mycluster tail -f /remote/path/log.txt

# Copy a file on the remote host
ropeway-cli -H mycluster cp /remote/path/file.txt /remote/path/file.bak

# Run a command or alias
ropeway-cli -H mycluster run "ls -la /tmp"
ropeway-cli -H mycluster run @mycommand
ropeway-cli -H mycluster run @build

# Compare two remote files (default: remote diff)
ropeway-cli -H mycluster diff /remote/path/a.txt /remote/path/b.txt

# Compare using a custom diff tool
ropeway-cli -H mycluster diff /remote/path/a.txt /remote/path/b.txt --use vimdiff

# Download and compare locally
ropeway-cli -H mycluster diff /remote/path/a.txt /remote/path/b.txt --local
```

## Path Mapping

ropeway-cli automatically translates paths between local and remote machines.
When a **relative** path is given, `local_base_path` in the current working
directory is replaced by `remote_base_path` (or vice versa).  Absolute
paths are used as-is.

For example, with the config above:
- `ropeway-cli -H mycluster ls .` from `/home/user/projects/foo` lists
  `/remote/home/user/projects/foo` on the remote host.
- `ropeway-cli -H mycluster get /remote/home/user/projects/foo/bar.txt` saves
  the file locally as `/home/user/projects/foo/bar.txt`.

## Contributing

Pull requests are welcome. New contributions should include proper tests.

### Setup

```bash
git clone https://github.com/bernik86/ropeway-cli.git
cd ropeway-cli
uv venv
uv pip install -e '.[dev]'
```

### Lint / format

```bash
uv run isort src/
uv run black src/
uv run pylint src/
uv run mypy src/
```

### Test

```bash
uv run pytest -v --cov --cov-report=term-missing
```

## License

Copyright (C) 2026 Berni

This program is free software; you can redistribute it and/or modify it
under the terms of the GNU General Public License as published by the
Free Software Foundation; either version 3 of the License, or (at your
option) any later version.