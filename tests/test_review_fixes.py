from __future__ import annotations

import io
import threading
import time
from pathlib import Path

from fastapi.testclient import TestClient

from mybiout import main as app_main
from mybiout.pages import utils
from mybiout.pages.apis import 应用
from mybiout.pages.ohmyconfig import ohmyconfig


def test_invalid_json_body_returns_400() -> None:
    client = TestClient(应用, raise_server_exceptions=False)

    response = client.post(
        "/api/setting",
        content="{bad json",
        headers={"content-type": "application/json"},
    )

    assert response.status_code == 400
    assert response.json()["ok"] is False


def test_port_probe_uses_real_socket_constructor() -> None:
    assert app_main._探测端口绑定错误(0) is None


def test_console_output_replaces_unencodable_characters(monkeypatch) -> None:
    buffer = io.BytesIO()
    fake_stdout = io.TextIOWrapper(buffer, encoding="gbk", errors="strict")
    monkeypatch.setattr(app_main.系统, "stdout", fake_stdout)

    app_main._配置文本输出()
    print("✦", file=app_main.系统.stdout)
    app_main.系统.stdout.flush()

    assert buffer.getvalue()


def test_concurrent_setting_writes_preserve_both_changes(tmp_path: Path, monkeypatch) -> None:
    config_path = tmp_path / "config.ini"
    monkeypatch.setattr(utils, "_配置路径", config_path)

    original_save_config = utils.保存配置
    start = threading.Barrier(2)

    def slow_save_config(cfg) -> None:
        time.sleep(0.05)
        original_save_config(cfg)

    def set_after_barrier(section: str, key: str, value: str) -> None:
        start.wait(timeout=5)
        utils.设设置(section, key, value)

    monkeypatch.setattr(utils, "保存配置", slow_save_config)

    t1 = threading.Thread(target=set_after_barrier, args=("api", "key", "k1"))
    t2 = threading.Thread(target=set_after_barrier, args=("api", "model", "m1"))
    t1.start()
    t2.start()
    t1.join(timeout=5)
    t2.join(timeout=5)

    settings = utils.取全部设置()
    assert settings["api"]["key"] == "k1"
    assert settings["api"]["model"] == "m1"


def test_auto_sessdata_launch_login_uses_qr_login(monkeypatch) -> None:
    client = TestClient(应用, raise_server_exceptions=False)
    monkeypatch.setattr(ohmyconfig, "通过登录自动取会话数据", lambda _ua, 超时秒数=180: "SESS=qr")

    response = client.post("/api/auto-sessdata", json={"action": "launch_login"})

    assert response.status_code == 200
    assert response.json() == {"status": "success", "sessdata": "SESS=qr"}


def test_auto_sessdata_rejects_legacy_browser_extraction_actions() -> None:
    client = TestClient(应用, raise_server_exceptions=False)

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
        app_main._环境项("ffmpeg", False, ""),
        app_main._环境项("BBDown", False, ""),
        app_main._环境项("biliffm4s", False, ""),
    ]

    assert app_main._取启动阻断项(checks) == []


def test_terminal_helicopter_ascii_has_clear_airframe_parts() -> None:
    rotor_art = "\n".join(app_main._旋翼帧)
    body_art = "\n".join(app_main._机身帧)

    assert "════╦════" in rotor_art
    assert "╭" in body_art and "╯" in body_art
    assert "═══>" in body_art
    assert "╰─╯" in body_art
