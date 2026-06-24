from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

from fastapi.testclient import TestClient

from mybiout import main as app_main
from mybiout.pages import utils
from mybiout.pages.apis import app
from mybiout.pages.ohmyconfig import cookie_helper, ohmyconfig


def test_invalid_json_body_returns_400() -> None:
    client = TestClient(app, raise_server_exceptions=False)

    response = client.post(
        "/api/setting",
        content="{bad json",
        headers={"content-type": "application/json"},
    )

    assert response.status_code == 400
    assert response.json()["ok"] is False


def test_concurrent_setting_writes_preserve_both_changes(tmp_path: Path, monkeypatch) -> None:
    config_path = tmp_path / "config.ini"
    monkeypatch.setattr(utils, "_CONFIG_PATH", config_path)

    original_save_config = utils.save_config
    start = threading.Barrier(2)

    def slow_save_config(cfg) -> None:
        time.sleep(0.05)
        original_save_config(cfg)

    def set_after_barrier(section: str, key: str, value: str) -> None:
        start.wait(timeout=5)
        utils.set_setting(section, key, value)

    monkeypatch.setattr(utils, "save_config", slow_save_config)

    t1 = threading.Thread(target=set_after_barrier, args=("api", "key", "k1"))
    t2 = threading.Thread(target=set_after_barrier, args=("api", "model", "m1"))
    t1.start()
    t2.start()
    t1.join(timeout=5)
    t2.join(timeout=5)

    settings = utils.get_all_settings()
    assert settings["api"]["key"] == "k1"
    assert settings["api"]["model"] == "m1"


def test_cookie_helper_writes_output_without_machine_specific_debug_path(
    tmp_path: Path,
    monkeypatch,
) -> None:
    out = tmp_path / "sessdata.txt"
    monkeypatch.setattr(sys, "argv", ["cookie_helper.py", "--out", str(out)])
    monkeypatch.setattr(cookie_helper, "_auto_get_sessdata_from_browsers", lambda _ua: "SESS=ok")

    cookie_helper.main()

    assert out.read_text(encoding="utf-8") == "SESS=ok"


def test_cookie_helper_has_no_machine_specific_debug_path() -> None:
    source = Path(cookie_helper.__file__).read_text(encoding="utf-8")

    assert "C:/Users/linzh" not in source
    assert "antigravity-cli" not in source


def test_elevation_flow_does_not_silently_restart_browsers(monkeypatch) -> None:
    monkeypatch.setattr(ohmyconfig, "_auto_get_sessdata_from_browsers", lambda _ua: "SESS=ok")

    assert ohmyconfig._auto_get_sessdata_via_elevation("UA") == ("SESS=ok", None)

    source = Path(ohmyconfig.__file__).read_text(encoding="utf-8")
    assert "taskkill /F /IM" not in source


def test_gitignore_excludes_tmp_edit_files() -> None:
    ignore_text = Path(".gitignore").read_text(encoding="utf-8")

    assert "TmpEdit*.txt" in ignore_text


def test_startup_does_not_block_when_feature_tools_are_missing() -> None:
    checks = [
        app_main._EnvItem("ffmpeg", False, ""),
        app_main._EnvItem("BBDown", False, ""),
        app_main._EnvItem("biliffm4s", False, ""),
    ]

    assert app_main._get_startup_blockers(checks) == []
