import os

import pytest

from src import config


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for k in ["OPENAI_API_KEY", "NAVER_CLIENT_ID", "NAVER_CLIENT_SECRET", "OPENAI_MODEL", "EXTRA_VAR"]:
        monkeypatch.delenv(k, raising=False)


def test_loads_keys_from_env_file(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text(
        'OPENAI_API_KEY="sk-test"\n'
        "NAVER_CLIENT_ID=naver-id\n"
        "# comment line\n"
        "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(config, "ENV_PATH", env)
    config._load_env_file()
    assert os.environ["OPENAI_API_KEY"] == "sk-test"
    assert os.environ["NAVER_CLIENT_ID"] == "naver-id"


def test_existing_env_not_overwritten(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("EXTRA_VAR=from_file\n", encoding="utf-8")
    monkeypatch.setenv("EXTRA_VAR", "from_shell")
    monkeypatch.setattr(config, "ENV_PATH", env)
    config._load_env_file()
    assert os.environ["EXTRA_VAR"] == "from_shell"


def test_missing_env_file_no_error(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "ENV_PATH", tmp_path / "nonexistent.env")
    config._load_env_file()  # should not raise
