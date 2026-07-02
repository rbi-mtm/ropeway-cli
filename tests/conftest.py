from __future__ import annotations

import json
from pathlib import Path

import fabric
import pytest
from pytest_mock import MockerFixture


@pytest.fixture
def host_conf() -> dict[str, str]:
    """Default host configuration with local and remote base paths."""
    return {
        "local_base_path": "/home/user/project",
        "remote_base_path": "/remote/home/user/project",
        "hostname": "testhost",
    }


@pytest.fixture
def mock_conn(mocker: MockerFixture) -> mocker.MagicMock:
    """Mocked Fabric connection with default run/get/put/cd return values."""
    conn = mocker.MagicMock(spec=fabric.Connection)

    result = mocker.MagicMock()
    result.stdout = ""
    result.stderr = ""
    result.exited = 0
    conn.run.return_value = result

    conn.get.return_value = None
    conn.put.return_value = None

    cd_cm = mocker.MagicMock()
    cd_cm.__enter__.return_value = None
    cd_cm.__exit__.return_value = None
    conn.cd.return_value = cd_cm

    return conn


@pytest.fixture
def mock_hosts_file(tmp_path: Path) -> str:
    """Temporary hosts JSON file with a single 'myhost' entry."""
    data: dict[str, dict[str, str]] = {
        "myhost": {
            "local_base_path": "/local/path",
            "remote_base_path": "/remote/path",
        }
    }
    f = tmp_path / "hosts.json"
    f.write_text(json.dumps(data))
    return str(f)
