r"""
打包边缘场景: 脱敏泄漏、残留清理、跳过垃圾文件、原子 zip、互斥锁、旧包裁剪。
"""

from __future__ import annotations

import configparser
import zipfile
from pathlib import Path

import pytest


def test_强制脱敏清空凭证与本机用户路径(打包模块) -> None:
    脏 = {
        "export": {
            "path": r"C:\Users\linzh\Documents\out",
            "sessdata": "SECRET_SESS",
        },
        "api": {"key": "sk-live-xxx", "model": "x"},
        "localout": {
            "bilibili_pc_cache_path": r"C:\Users\linzh\Videos\bilibili",
            "folder": "localout!",
        },
        "bbdown": {"cookie": "SESSDATA=abc", "folder": "bbdown!"},
        "mdout": {"sessdata": "md-secret"},
    }
    净 = 打包模块.强制脱敏配置分区(脏)
    assert 净["export"]["sessdata"] == ""
    assert 净["api"]["key"] == ""
    assert 净["bbdown"]["cookie"] == ""
    assert 净["mdout"]["sessdata"] == ""
    assert 净["localout"]["bilibili_pc_cache_path"] == ""
    # 含 Users 的 export.path 回落通用目录
    assert 净["export"]["path"] == r"C:\MyBiOut!"
    assert 净["localout"]["folder"] == "localout!"
    assert 净["api"]["model"] == "x"


def test_写入脱敏配置不带用户目录(打包模块, tmp_path: Path) -> None:
    r"""即使程序 默认设置 含 Path.home() 缓存路径, 写出的发布配置也必须清空。"""
    目标 = tmp_path / "config.ini"
    打包模块.写入脱敏默认配置(目标)
    cfg = configparser.ConfigParser(interpolation=None)
    cfg.read(目标, encoding="utf-8")
    assert cfg.get("export", "sessdata") == ""
    assert cfg.get("api", "key") == ""
    bili = cfg.get("localout", "bilibili_pc_cache_path", fallback="")
    assert bili == ""
    assert "Users" not in 目标.read_text(encoding="utf-8")
    assert "无凭证" in 目标.read_text(encoding="utf-8")


def test_列举待拷跳过垃圾与半成品(打包模块, tmp_path: Path) -> None:
    (tmp_path / "ok.txt").write_text("1", encoding="utf-8")
    (tmp_path / "Thumbs.db").write_bytes(b"x")
    (tmp_path / "desktop.ini").write_text("x", encoding="utf-8")
    (tmp_path / "a.zip.part").write_bytes(b"p")
    bad = tmp_path / "sub" / "__pycache__"
    bad.mkdir(parents=True)
    (bad / "z.pyc").write_bytes(b"1")
    (tmp_path / "sub" / "good.dat").write_text("g", encoding="utf-8")
    名 = {p.name for p in 打包模块.列举待拷文件(tmp_path)}
    assert "ok.txt" in 名 and "good.dat" in 名
    assert "Thumbs.db" not in 名
    assert "desktop.ini" not in 名
    assert "a.zip.part" not in 名
    assert "z.pyc" not in 名


def test_清理打包残留删除半成品并裁剪旧zip(
    打包模块, tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(打包模块, "工程根目录", tmp_path)
    monkeypatch.setattr(打包模块, "产物输出目录名", "dist")
    monkeypatch.setattr(打包模块, "发布目录名", "release")
    monkeypatch.setattr(打包模块, "产物显示名", "MyBiOut!")
    monkeypatch.setattr(打包模块, "绿色目录名", "MyBiOut-green")
    monkeypatch.setattr(打包模块, "发布包保留个数", 2)

    发布 = tmp_path / "dist" / "release"
    发布.mkdir(parents=True)
    (发布 / "MyBiOut!-26.07.19.1.zip.part").write_bytes(b"partial")
    (发布 / "junk.tmp").write_bytes(b"t")
    # 3 个旧 zip, 收尾只留 2
    for i, name in enumerate(
        ["MyBiOut!-a.zip", "MyBiOut!-b.zip", "MyBiOut!-c.zip"]
    ):
        p = 发布 / name
        p.write_bytes(b"z" * (10 + i))
        # 保证 mtime 顺序: a 最旧 c 最新
        import os
        import time

        os.utime(p, (time.time() - 100 + i * 10, time.time() - 100 + i * 10))

    暂存 = tmp_path / "dist" / "MyBiOut-green.staging"
    暂存.mkdir(parents=True)
    (暂存 / "x").write_text("1", encoding="utf-8")

    打包模块.清理打包残留(None, 阶段="开工")
    assert not (发布 / "MyBiOut!-26.07.19.1.zip.part").exists()
    assert not (发布 / "junk.tmp").exists()
    assert not 暂存.exists()

    打包模块.清理打包残留(None, 阶段="收尾", 保留版本="c")
    剩余 = sorted(p.name for p in 发布.glob("MyBiOut!-*.zip"))
    assert len(剩余) == 2
    assert "MyBiOut!-a.zip" not in 剩余
    assert "MyBiOut!-c.zip" in 剩余


def test_打包为压缩包原子写出无part残留(
    打包模块, tmp_path: Path, monkeypatch
) -> None:
    绿 = tmp_path / "green"
    (绿 / "sub").mkdir(parents=True)
    (绿 / "MyBiOut!.exe").write_bytes(b"MZ")
    (绿 / "sub" / "a.txt").write_text("hello", encoding="utf-8")
    monkeypatch.setattr(打包模块, "工程根目录", tmp_path)
    monkeypatch.setattr(打包模块, "产物输出目录名", "dist")
    monkeypatch.setattr(打包模块, "发布目录名", "release")
    monkeypatch.setattr(打包模块, "产物显示名", "MyBiOut!")

    态 = 打包模块.打包进度(纯文本=True)
    归档 = 打包模块.打包为压缩包(绿, "26.07.19.9", 态)
    assert 归档.is_file()
    part = 归档.with_suffix(归档.suffix + ".part")
    assert not part.exists()
    with zipfile.ZipFile(归档, "r") as zf:
        assert zf.testzip() is None
        assert any(n.endswith("a.txt") for n in zf.namelist())


def test_互斥锁二次获取失败(
    打包模块, tmp_path: Path, monkeypatch
) -> None:
    if 打包模块.系统.platform != "win32":
        pytest.skip("仅 Windows")
    monkeypatch.setattr(打包模块, "工程根目录", tmp_path)
    monkeypatch.setattr(打包模块, "产物输出目录名", "dist")
    锁1 = 打包模块.获取打包互斥锁(None)
    assert 锁1 is not None
    try:
        with pytest.raises(SystemExit):
            打包模块.获取打包互斥锁(None)
    finally:
        打包模块.释放打包互斥锁(锁1)
    # 释放后应可再获取
    锁2 = 打包模块.获取打包互斥锁(None)
    打包模块.释放打包互斥锁(锁2)


def test_组装失败不留下半成品绿包(
    打包模块,
    tmp_path: Path,
    假构建产物: Path,
    monkeypatch,
) -> None:
    r"""缺 BBDown 时组装应失败, 且无 MyBiOut-green 与 .staging。"""
    import shutil

    monkeypatch.setattr(打包模块, "工程根目录", tmp_path)
    monkeypatch.setattr(打包模块, "产物输出目录名", "dist")
    monkeypatch.setattr(打包模块, "绿色目录名", "MyBiOut-green")
    monkeypatch.setattr(打包模块, "产物显示名", "MyBiOut!")
    包目录 = tmp_path / "mybiout"
    包目录.mkdir()
    (包目录 / "version.txt").write_text("1\n", encoding="utf-8")
    # 故意不放 BBDown
    (包目录 / "bin").mkdir()
    monkeypatch.setattr(打包模块, "程序包目录", 包目录)
    monkeypatch.setattr(打包模块, "版本文件路径", 包目录 / "version.txt")
    dist = tmp_path / "dist"
    dist.mkdir()
    shutil.copytree(假构建产物, dist / "MyBiOut!")

    态 = 打包模块.打包进度(纯文本=True)
    with pytest.raises(SystemExit):
        打包模块.组装绿色目录("1", 态)
    assert not (dist / "MyBiOut-green").exists()
    assert not (dist / "MyBiOut-green.staging").exists()
