from pathlib import Path

import pytest

from server.config import load_config

CONFIG_PATH = Path(__file__).resolve().parent.parent / "server" / "config.yaml"


@pytest.fixture(scope="session")
def config():
    return load_config(CONFIG_PATH)
