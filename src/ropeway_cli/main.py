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

# pylint: disable=missing-docstring

import sys

from .lib import cli


def main():

    cli.cli(obj={})  # pylint: disable=no-value-for-parameter

    return 0


if __name__ == "__main__":
    sys.exit(main())
