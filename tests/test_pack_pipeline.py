r"""
打包流水线深度集成: 跳过 pip/PyInstaller, 串起 版本→组装→zip→成功状态。
并覆盖 失败路径 与 阶段明细 的真实推进。
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest


def test_完整流水线无构建_成功状态与zip(
    打包模块,
    tmp_path: Path,
    假构建产物: Path,
    假工具bin: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import shutil

    monkeypatch.setattr(打包模块, "工程根目录", tmp_path)
    monkeypatch.setattr(打包模块, "产物输出目录名", "dist")
    monkeypatch.setattr(打包模块, "绿色目录名", "MyBiOut-green")
    monkeypatch.setattr(打包模块, "发布目录名", "release")
    monkeypatch.setattr(打包模块, "产物显示名", "MyBiOut!")
    monkeypatch.setattr(打包模块, "构建缓存目录名", "build")

    包目录 = tmp_path / "mybiout"
    包目录.mkdir()
    版本文件 = 包目录 / "version.txt"
    版本文件.write_text("26.07.19.1\n", encoding="utf-8")
    monkeypatch.setattr(打包模块, "程序包目录", 包目录)
    monkeypatch.setattr(打包模块, "版本文件路径", 版本文件)
    shutil.copytree(假工具bin, 包目录 / "bin")

    dist = tmp_path / "dist"
    dist.mkdir()
    shutil.copytree(假构建产物, dist / "MyBiOut!")

    # 跳过真 pip / 真 PyInstaller
    def _假依赖(状态=None):
        if 状态:
            状态.进入阶段("依赖", "跳过", 段内=1.0, 明细="0/0")
            状态.完成阶段("依赖", "依赖跳过", 明细="mock")

    def _假构建(状态=None):
        if 状态:
            状态.进入阶段("构建", "跳过", 段内=0.5, 明细="mock")
            状态.完成阶段("构建", "构建跳过", 明细="mock")

    monkeypatch.setattr(打包模块, "安装依赖", _假依赖)
    monkeypatch.setattr(打包模块, "执行构建", _假构建)

    态 = 打包模块.打包进度(
        旧版本="26.07.19.1",
        新版本="26.07.19.2",
        纯文本=True,
    )
    打包模块.执行完整打包(态)

    assert 态.已成功 and 态.已结束
    assert 态.目标进度 == 1.0
    assert 态.文案 == "搞定了!"
    assert 态.绿色根 is not None and 态.绿色根.is_dir()
    assert 态.归档 is not None and 态.归档.is_file()
    assert 态.归档.suffix == ".zip"
    assert 态.耗时秒 >= 0.0
    # 版本文件应被写成新版本
    assert 版本文件.read_text(encoding="utf-8").strip() == "26.07.19.2"
    with zipfile.ZipFile(态.归档, "r") as zf:
        names = zf.namelist()
    assert any("MyBiOut!.exe" in n.replace("\\", "/") for n in names)
    assert any(n.endswith("config.ini") for n in names)


def test_流水线中途失败标记(
    打包模块,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(打包模块, "工程根目录", tmp_path)
    monkeypatch.setattr(打包模块, "版本文件路径", tmp_path / "version.txt")
    (tmp_path / "version.txt").write_text("26.07.19.1\n", encoding="utf-8")

    def _炸依赖(状态=None):
        if 状态:
            状态.进入阶段("依赖", "将失败", 段内=0.2)
        raise RuntimeError("依赖爆炸")

    monkeypatch.setattr(打包模块, "安装依赖", _炸依赖)
    态 = 打包模块.打包进度(旧版本="26.07.19.1", 新版本="26.07.19.2", 纯文本=True)
    # 纯文本模式失败会 失败退出 → SystemExit
    with pytest.raises(SystemExit):
        打包模块.执行完整打包(态)
    assert 态.已结束 and not 态.已成功
    assert "依赖爆炸" in 态.失败原因
    assert 态.目标进度 < 1.0


def test_依赖逐包推进明细(打包模块, monkeypatch: pytest.MonkeyPatch) -> None:
    调用: list[str] = []

    def _假执行(命令, **kw):
        调用.append(" ".join(命令))

    monkeypatch.setattr(打包模块, "执行命令", _假执行)
    monkeypatch.setattr(打包模块, "依赖列表", ["pkgA", "pkgB", "pkgC"])
    态 = 打包模块.打包进度(纯文本=True)
    打包模块.安装依赖(态)
    assert 态.明细 == "3/3"
    assert 态.目标进度 >= 打包模块.阶段区间("依赖")[1] - 1e-9
    assert len(调用) == 3
    assert "pkgA" in 调用[0] and "pkgC" in 调用[2]


def test_构建完成后明细含产物体积(
    打包模块,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    r"""不真跑 PyInstaller: 假执行 + 预写产物目录, 断言完成阶段明细含 MB。"""
    monkeypatch.setattr(打包模块, "工程根目录", tmp_path)
    monkeypatch.setattr(打包模块, "产物输出目录名", "dist")
    monkeypatch.setattr(打包模块, "构建缓存目录名", "build")
    monkeypatch.setattr(打包模块, "产物显示名", "MyBiOut!")
    monkeypatch.setattr(打包模块, "内嵌数据项", [])
    (tmp_path / "mybiout" / "main.py").parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / "mybiout" / "main.py").write_text("#x\n", encoding="utf-8")
    monkeypatch.setattr(打包模块, "程序包目录", tmp_path / "mybiout")

    产物 = tmp_path / "dist" / "MyBiOut!"
    产物.mkdir(parents=True)
    (产物 / "MyBiOut!.exe").write_bytes(b"x" * (3 * 1024 * 1024))

    def _假执行(命令, **kw):
        import time

        time.sleep(0.2)

    monkeypatch.setattr(打包模块, "执行命令", _假执行)
    态 = 打包模块.打包进度(纯文本=True)
    打包模块.执行构建(态)
    assert 态.目标进度 >= 打包模块.阶段区间("构建")[1] - 1e-9
    assert "MB" in 态.明细


def test_生命周期文案契约(工程根: Path) -> None:
    源 = (工程根 / "打包.py").read_text(encoding="utf-8")
    assert 源.index("def 起飞演出") < 源.index("def 降落演出")
    assert 源.index("def 降落演出") < 源.index("def 坠机演出") or "def 坠机演出" in 源
    # 传统构型: 主旋翼 + 尾桨占位 + 完整地面
    assert "_尾桨帧" in 源 and "?" in 源
    assert "绘完整地面" in 源
    assert "_等待任意键" in 源
    # 无飞机状态旁白 (动画自解释)
    assert "旋翼启动" not in 源
    assert "起飞爬升" not in 源
    assert "降落中" not in 源
    # 主流程顺序: 起飞后再开工
    起飞调用 = 源.index("起飞演出()")
    开工 = 源.index("开工 is not None")
    assert 起飞调用 < 开工


def test_直升机座舱短于尾梁(打包模块) -> None:
    r"""传统构型: 尾梁单线单元格数应明显大于座舱, 撬只在舱下。"""
    for 名, 身 in (("右", 打包模块._机身朝右), ("左", 打包模块._机身朝左)):
        轮廓 = 身[1]
        梁 = sum(1 for c in 轮廓 if c in "-_")
        舱 = sum(1 for c in 轮廓 if c in "[]oO#")
        assert 梁 >= 舱 * 2, f"{名}: 尾梁{梁} 应 ≥ 2×座舱{舱}: {轮廓!r}"
        assert "?" in 轮廓 and ("T" in 轮廓 or "|" in 轮廓)
        assert "[" in 轮廓 and "]" in 轮廓
        # 起落撬行不得铺满尾梁投影: 非空字符应集中在座舱下方
        撬 = 身[3]
        舱心 = 打包模块._座舱中心列(轮廓)
        撬点 = [i for i, c in enumerate(撬) if c != " "]
        assert 撬点, 名
        assert all(abs(i - 舱心) <= 5 for i in 撬点), f"{名} 撬偏离座舱: {撬!r}"


def test_标题字形等宽且纯ascii(打包模块) -> None:
    # 开场/检查: 字母块
    形 = 打包模块._检查标题字形
    宽 = 打包模块._检查标题宽度
    assert 宽 >= 30
    for 行 in 形:
        assert len(行) == 宽
        assert all(ord(c) < 128 for c in 行)
    assert any("M" in 行 and "B" in 行 for 行 in 形)
    assert any("!" in 行 for 行 in 形)
    # 结算: 高密度轮廓字 (FIGlet 风格, 与检查页不同)
    结 = 打包模块._结算标题字形
    结宽 = 打包模块._结算标题宽度
    assert 结宽 >= 30
    for 行 in 结:
        assert len(行) == 结宽
        assert all(ord(c) < 128 for c in 行)
    assert any("_" in 行 or "|" in 行 for 行 in 结)
    assert 形 != 结


def test_单元宽不再把方块当双列(打包模块) -> None:
    assert 打包模块._单元宽("#") == 1
    assert 打包模块._单元宽("A") == 1
    assert 打包模块._单元宽("中") == 2
    # 全角块若出现也不应拖垮 ASCII 标题逻辑; 盲文按单列
    assert 打包模块._单元宽("⠿") == 1
