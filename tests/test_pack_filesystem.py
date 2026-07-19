r"""
打包文件侧深度测试: 列举/体积/脱敏配置/zip/组装校验。
不跑 PyInstaller 与 pip。
"""

from __future__ import annotations

import configparser
import zipfile
from pathlib import Path

import pytest


def test_列举待拷文件忽略pycache(打包模块, tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("a", encoding="utf-8")
    bad = tmp_path / "sub" / "__pycache__"
    bad.mkdir(parents=True)
    (bad / "x.pyc").write_bytes(b"1")
    (tmp_path / "sub" / "b.txt").write_text("b", encoding="utf-8")
    文件 = 打包模块.列举待拷文件(tmp_path)
    名 = {p.name for p in 文件}
    assert "a.txt" in 名 and "b.txt" in 名
    assert "x.pyc" not in 名


def test_目录体积字节累计(打包模块, tmp_path: Path) -> None:
    (tmp_path / "f1").write_bytes(b"12345")
    (tmp_path / "d").mkdir()
    (tmp_path / "d" / "f2").write_bytes(b"abcd")
    assert 打包模块.目录体积字节(tmp_path) == 9
    assert 打包模块.目录体积字节(tmp_path / "missing") == 0


def test_计算下一版本同日递增(打包模块, monkeypatch) -> None:
    class _假日期:
        @staticmethod
        def today():
            from datetime import date

            return date(2026, 7, 19)

    monkeypatch.setattr(打包模块, "日期", _假日期)
    assert 打包模块.计算下一版本("0.0.0.0") == "26.07.19.1"
    assert 打包模块.计算下一版本("26.07.19.1") == "26.07.19.2"
    assert 打包模块.计算下一版本("26.07.18.9") == "26.07.19.1"


def test_写入脱敏默认配置无密钥(打包模块, tmp_path: Path) -> None:
    目标 = tmp_path / "config.ini"
    打包模块.写入脱敏默认配置(目标)
    cfg = configparser.ConfigParser(interpolation=None)
    cfg.read(目标, encoding="utf-8")
    assert cfg.get("export", "sessdata") == ""
    assert cfg.get("api", "key") == ""
    assert cfg.get("bbdown", "cookie") == ""
    文本 = 目标.read_text(encoding="utf-8")
    assert "无凭证" in 文本 or "配置文件" in 文本


def test_打包为压缩包结构与进度计量(打包模块, tmp_path: Path, monkeypatch) -> None:
    绿 = tmp_path / "green"
    (绿 / "sub").mkdir(parents=True)
    (绿 / "MyBiOut!.exe").write_bytes(b"MZ")
    (绿 / "sub" / "a.txt").write_text("hello", encoding="utf-8")
    (绿 / "sub" / "b.txt").write_text("world", encoding="utf-8")

    # 重定向发布目录到 tmp
    monkeypatch.setattr(打包模块, "工程根目录", tmp_path)
    monkeypatch.setattr(打包模块, "产物输出目录名", "dist")
    monkeypatch.setattr(打包模块, "发布目录名", "release")

    态 = 打包模块.打包进度(纯文本=True)
    归档 = 打包模块.打包为压缩包(绿, "26.07.19.1", 态)
    assert 归档.is_file()
    assert 归档.suffix == ".zip"
    assert 态.目标进度 >= 打包模块.阶段区间("压缩")[1] - 1e-9

    with zipfile.ZipFile(归档, "r") as zf:
        名 = zf.namelist()
    # 包内应有 MyBiOut!/ 前缀
    assert any(n.replace("\\", "/").startswith("MyBiOut!/") for n in 名)
    assert any(n.endswith("a.txt") for n in 名)


def test_校验绿色包工具缺BBDown失败(打包模块, tmp_path: Path) -> None:
    绿 = tmp_path / "g"
    (绿 / "bin").mkdir(parents=True)
    态 = 打包模块.打包进度(纯文本=True)
    with pytest.raises(SystemExit):
        打包模块.校验绿色包工具(绿, 态)


def test_校验绿色包工具齐全通过(打包模块, tmp_path: Path, 假工具bin: Path) -> None:
    import shutil

    绿 = tmp_path / "g"
    shutil.copytree(假工具bin, 绿 / "bin")
    态 = 打包模块.打包进度(纯文本=True)
    打包模块.校验绿色包工具(绿, 态)  # 不抛即通过


def test_组装绿色目录文件计数进度(
    打包模块,
    tmp_path: Path,
    假构建产物: Path,
    假工具bin: Path,
    monkeypatch,
) -> None:
    # 把工程路径指到 tmp, 并植入 version / 源 bin
    monkeypatch.setattr(打包模块, "工程根目录", tmp_path)
    monkeypatch.setattr(打包模块, "产物输出目录名", "dist")
    monkeypatch.setattr(打包模块, "绿色目录名", "MyBiOut-green")
    monkeypatch.setattr(打包模块, "产物显示名", "MyBiOut!")
    包目录 = tmp_path / "mybiout"
    包目录.mkdir()
    (包目录 / "version.txt").write_text("26.07.19.1\n", encoding="utf-8")
    monkeypatch.setattr(打包模块, "程序包目录", 包目录)
    monkeypatch.setattr(打包模块, "版本文件路径", 包目录 / "version.txt")
    import shutil

    shutil.copytree(假工具bin, 包目录 / "bin")

    dist = tmp_path / "dist"
    dist.mkdir()
    shutil.copytree(假构建产物, dist / "MyBiOut!")

    态 = 打包模块.打包进度(纯文本=True)
    绿 = 打包模块.组装绿色目录("26.07.19.1", 态)
    assert 绿.is_dir()
    assert (绿 / "MyBiOut!.exe").is_file()
    assert (绿 / "version.txt").is_file()
    assert (绿 / "config.ini").is_file()
    assert (绿 / "bin" / "BBDown.exe").is_file()
    assert (绿 / "使用说明.txt").is_file()
    # 组装阶段应走完
    assert 态.目标进度 >= 打包模块.阶段区间("组装")[1] - 1e-9
    assert "文件" in 态.明细
