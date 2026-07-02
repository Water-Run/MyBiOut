from __future__ import annotations

import io
import threading
import time
from pathlib import Path

from fastapi.testclient import TestClient

from mybiout import main as app_main
from mybiout.pages import utils
from mybiout.pages.apis import app
from mybiout.pages.ohmyconfig import ohmyconfig


def test_invalid_json_body_returns_400() -> None:
    client = TestClient(app, raise_server_exceptions=False)

    response = client.post(
        "/api/setting",
        content="{bad json",
        headers={"content-type": "application/json"},
    )

    assert response.status_code == 400
    assert response.json()["ok"] is False


def test_port_probe_uses_real_socket_constructor() -> None:
    assert app_main._probe_port_bind_error(0) is None


def test_console_output_replaces_unencodable_characters(monkeypatch) -> None:
    buffer = io.BytesIO()
    fake_stdout = io.TextIOWrapper(buffer, encoding="gbk", errors="strict")
    monkeypatch.setattr(app_main.系统, "stdout", fake_stdout)

    app_main._configure_text_output()
    print("✦", file=app_main.系统.stdout)
    app_main.系统.stdout.flush()

    assert buffer.getvalue()


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


def test_auto_sessdata_launch_login_uses_qr_login(monkeypatch) -> None:
    client = TestClient(app, raise_server_exceptions=False)
    monkeypatch.setattr(ohmyconfig, "_auto_get_sessdata_via_login", lambda _ua, timeout_sec=180: "SESS=qr")

    response = client.post("/api/auto-sessdata", json={"action": "launch_login"})

    assert response.status_code == 200
    assert response.json() == {"status": "success", "sessdata": "SESS=qr"}


def test_auto_sessdata_rejects_legacy_browser_extraction_actions() -> None:
    client = TestClient(app, raise_server_exceptions=False)

    for action in ("check_direct", "check_elevated"):
        response = client.post("/api/auto-sessdata", json={"action": action})

        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "failed"
        assert "sessdata" not in payload


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


def test_terminal_helicopter_ascii_has_clear_airframe_parts() -> None:
    rotor_art = "\n".join(app_main._ROTORS)
    body_art = "\n".join(app_main._BODY)

    assert "════╦════" in rotor_art
    assert "╭" in body_art and "╯" in body_art
    assert "═══>" in body_art
    assert "╰─╯" in body_art
