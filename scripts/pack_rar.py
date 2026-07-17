r"""
将已组装的绿色目录打成发布版 .rar

:file: scripts/pack_rar.py
:author: WaterRun
:time: 2026-07-17
"""

from __future__ import annotations

import re as 正则
import shutil as 文件工具
import subprocess as 子进程
import sys as 系统
from pathlib import Path as 路径

仓库根: 路径 = 路径(__file__).resolve().parent.parent
绿色目录: 路径 = 仓库根 / "dist" / "MyBiOut-green"
发布目录: 路径 = 仓库根 / "dist" / "release"
候选Rar路径: tuple[路径, ...] = (
    路径(r"C:\Program Files\WinRAR\Rar.exe"),
    路径(r"C:\Program Files (x86)\WinRAR\Rar.exe"),
    路径.home() / "AppData" / "Local" / "Programs" / "WinRAR" / "Rar.exe",
)


def 取版本号() -> str:
    r"""
    从 mybiout/__init__.py 读取 __version__
    :return: str: 版本号
    """
    初始化文件: 路径 = 仓库根 / "mybiout" / "__init__.py"
    文本: str = 初始化文件.read_text(encoding="utf-8")
    匹配 = 正则.search(r'__version__\s*:\s*str\s*=\s*["\']([^"\']+)["\']', 文本)
    if 匹配 is None:
        匹配 = 正则.search(r'__version__\s*=\s*["\']([^"\']+)["\']', 文本)
    if 匹配 is None:
        raise RuntimeError(f"无法从 {初始化文件} 解析版本号")
    return 匹配.group(1)


def 寻找Rar可执行文件() -> 路径 | None:
    r"""
    查找 WinRAR 命令行 Rar.exe
    :return: Path | None: 路径, 未找到返回 None
    """
    which结果: str | None = 文件工具.which("Rar") or 文件工具.which("rar")
    if which结果:
        return 路径(which结果)
    for 候选 in 候选Rar路径:
        if 候选.is_file():
            return 候选
    return None


def 主流程() -> int:
    r"""
    打包绿色目录为 dist/release/MyBiOut-版本.rar
    :return: int: 退出码
    """
    if not 绿色目录.is_dir():
        print(f"未找到绿色目录: {绿色目录}")
        print("请先完成 PyInstaller 组装 (assemble_green.py)")
        return 1

    rar路径: 路径 | None = 寻找Rar可执行文件()
    if rar路径 is None:
        print("未找到 WinRAR 的 Rar.exe, 无法生成 .rar 发布包。")
        print("请安装 WinRAR 后重试: https://www.win-rar.com/")
        print("常见路径: C:\\Program Files\\WinRAR\\Rar.exe")
        return 1

    版本: str = 取版本号()
    发布目录.mkdir(parents=True, exist_ok=True)
    归档名: str = f"MyBiOut-{版本}.rar"
    归档路径: 路径 = 发布目录 / 归档名

    # 统一外层目录名, 解压后得到 MyBiOut/
    暂存根: 路径 = 仓库根 / "dist" / "_rar_stage"
    暂存包: 路径 = 暂存根 / "MyBiOut"
    if 暂存根.exists():
        文件工具.rmtree(暂存根)
    文件工具.copytree(
        绿色目录,
        暂存包,
        ignore=文件工具.ignore_patterns("__pycache__", "*.pyc", ".git"),
    )

    if 归档路径.exists():
        归档路径.unlink()

    # 在暂存根下打包, 归档内顶层目录为 MyBiOut\
    命令: list[str] = [
        str(rar路径),
        "a",
        "-r",
        "-m5",
        "-y",
        str(归档路径),
        "MyBiOut",
    ]
    print("执行:", " ".join(命令))
    print("工作目录:", 暂存根)
    结果 = 子进程.run(命令, cwd=str(暂存根), check=False)
    文件工具.rmtree(暂存根, ignore_errors=True)

    if 结果.returncode != 0:
        print(f"Rar 打包失败, 退出码 {结果.returncode}")
        return 结果.returncode or 1

    if not 归档路径.is_file():
        print(f"未生成归档: {归档路径}")
        return 1

    大小兆: float = 归档路径.stat().st_size / (1024 * 1024)
    print(f"发布包已生成: {归档路径}")
    print(f"大小: {大小兆:.1f} MB")
    return 0


if __name__ == "__main__":
    系统.exit(主流程())
