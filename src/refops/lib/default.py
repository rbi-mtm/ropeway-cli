#!/home/berni/.local/share/python-envs/rbi/bin/python
#
#  defaults.py
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

"""Default configuration values for the refops CLI."""

import os

THEME = "solarized-box"  # Theme for CLI (see rich-click documentation for alternatives)
HELP_MAX_WIDTH = 80  # Maximum width (in characters) of help messages

HOST_CONFIG = os.path.expanduser("~/.config/refops/hosts.json")
