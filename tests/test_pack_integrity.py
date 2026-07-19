r"""
打包脚本完整性与安全边界: 不泄密、无预览、zip、windowed、快速检查。
"""

from __future__ import annotations

from pathlib import Path

import pytest


def test_打包源码安全与发行形态(工程根: Path) -> None:
    源 = (工程根 / "打包.py").read_text(encoding="utf-8")
    # 不把本机 config 打进包
    assert "config.ini';mybiout" not in 源
    assert "写入脱敏默认配置" in 源
    assert "强制脱敏配置分区" in 源
    assert "清理打包残留" in 源
    assert "获取打包互斥锁" in 源
    assert "安全移除树" in 源
    assert ".zip.part" in 源
    assert "testzip" in 源
    # 绿色 exe 无控制台
    assert "--windowed" in 源
    assert "--console" not in 源
    # 不用 WinRAR 硬依赖
    assert "查找压缩工具" not in 源
    assert "ZipFile" in 源 or "压缩包.ZipFile" in 源
    # 无预览旁路
    assert "预览TUI" not in 源
    assert "执行预览进度" not in 源
    # 进度真实计量
    assert "目录体积字节" in 源
    assert "列举待拷文件" in 源
    assert "进入阶段" in 源
    # 直升机生命周期: 起飞 → 巡航 → 降落/坠机
    assert "起飞演出" in 源
    assert "降落演出" in 源
    assert "坠机演出" in 源
    assert "_尾桨帧" in 源
    assert "绘完整地面" in 源
    assert "_等待任意键" in 源
    # 中文失败/成功
    assert "【失败】" in 源
    assert "搞定了!" in 源


def test_gitignore覆盖构建与密钥(工程根: Path) -> None:
    文本 = (工程根 / ".gitignore").read_text(encoding="utf-8")
    for 必须 in (
        "build/",
        "dist/",
        "mybiout/config.ini",
        "mybiout/bin/*.exe",
        "*.zip",
        "*.log",
        ".env",
        "auth_profile/",
        "*.part",
    ):
        assert 必须 in 文本, 必须


def test_快速代码检查通过当前树(打包模块) -> None:
    ok, msg = 打包模块.快速代码检查()
    assert ok is True
    assert "通过" in msg


def test_快速代码检查缺文件失败(打包模块, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(打包模块, "工程根目录", tmp_path)
    monkeypatch.setattr(打包模块, "程序包目录", tmp_path / "nope")
    ok, msg = 打包模块.快速代码检查()
    assert ok is False
    assert "缺少" in msg or "失败" in msg or "语法" in msg


def test_执行命令TUI模式写日志不抛成功(打包模块, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(打包模块, "工程根目录", tmp_path)
    monkeypatch.setattr(打包模块, "产物输出目录名", "dist")
    态 = 打包模块.打包进度(纯文本=False)
    # 成功命令
    打包模块.执行命令(
        [打包模块.系统.executable, "-c", "print(123)"],
        步骤说明="探测",
        状态=态,
    )
    日志 = tmp_path / "dist" / "pack_cmd.log"
    assert 日志.is_file()
    文本 = 日志.read_text(encoding="utf-8", errors="replace")
    assert "探测" in 文本
    assert "123" in 文本 or "print" in 文本


def test_执行命令失败在TUI模式标记失败(打包模块, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(打包模块, "工程根目录", tmp_path)
    monkeypatch.setattr(打包模块, "产物输出目录名", "dist")
    态 = 打包模块.打包进度(纯文本=False)
    with pytest.raises(SystemExit):
        打包模块.执行命令(
            [打包模块.系统.executable, "-c", "raise SystemExit(7)"],
            步骤说明="必败",
            状态=态,
        )
    assert 态.已结束 and not 态.已成功
    assert "必败" in 态.失败原因 or "7" in 态.失败原因


def test_依赖列表与隐藏导入非空(打包模块) -> None:
    assert "pyinstaller" in 打包模块.依赖列表
    assert "pywebview" in 打包模块.依赖列表
    assert any("mybiout.pages" in h for h in 打包模块.隐藏导入列表)
