r"""
应用侧契约: 便携路径、版本、默认配置、HTTP 路由与静态资源。
"""

from __future__ import annotations

from pathlib import Path

import pytest


def test_开发态便携路径(工程根: Path) -> None:
    from mybiout.pages.utils import 是否冻结运行
    from mybiout.pages.utils import 取工具目录
    from mybiout.pages.utils import 取页面目录
    from mybiout.pages.utils import 取运行根目录
    from mybiout.pages.utils import 取资料目录
    from mybiout.pages.utils import 取静态资源目录

    assert 是否冻结运行() is False
    assert 取运行根目录().name == "mybiout"
    assert 取工具目录().name == "bin"
    assert (取页面目录() / "index.html").is_file()
    assert (取静态资源目录() / "entry.js").is_file()
    assert 取资料目录().name == "auth_profile"


def test_版本号优先运行根(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from mybiout import 取版本号
    import mybiout.pages.utils as 工具

    (tmp_path / "version.txt").write_text("11.22.33.4\n", encoding="utf-8")
    monkeypatch.setattr(工具, "取运行根目录", lambda: tmp_path)
    assert 取版本号() == "11.22.33.4"


def test_默认设置凭证为空() -> None:
    from mybiout.pages.utils import 默认设置

    assert 默认设置["export"]["sessdata"] == ""
    assert 默认设置["api"]["key"] == ""
    assert 默认设置["bbdown"]["cookie"] == ""
    assert 默认设置["mdout"]["sessdata"] == ""


def test_关键api与页面路由(工程根: Path) -> None:
    from fastapi.testclient import TestClient
    from mybiout.pages.apis import 应用

    client = TestClient(应用)
    for path in (
        "/",
        "/ohmyconfig",
        "/localout",
        "/bbdown",
        "/mdout",
        "/man",
        "/api/version",
        "/api/settings",
        "/assets/entry.js",
        "/assets/entry.css",
    ):
        r = client.get(path)
        assert r.status_code == 200, path
    ver = client.get("/api/version").json()
    assert "version" in ver and ver["version"]
    settings = client.get("/api/settings").json()
    assert "export" in settings and "api" in settings


def test_configparser对百分号sessdata不炸(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    r"""回归: SESSDATA 含 % 时默认插值会炸, 必须 interpolation=None。"""
    import mybiout.pages.utils as 工具

    cfg = tmp_path / "config.ini"
    cfg.write_text(
        "[export]\npath=C:\\\\x\nsessdata=abc%2Cdef%2Aghi\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(工具, "_配置路径", cfg)
    值 = 工具.取设置("export", "sessdata")
    assert "%2C" in 值
