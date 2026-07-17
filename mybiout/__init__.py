r"""
MyBiOut! 包初始化模块

:file: mybiout/__init__.py
:author: WaterRun
:time: 2026-03-31
"""

import sys as 系统
from pathlib import Path as 路径

if 系统.platform != "win32":
    raise ImportError("MyBiOut! 仅支持 Windows 系统。")

if 系统.maxsize <= 2**32:
    raise ImportError("MyBiOut! 仅支持 64 位 Windows 系统。")


def 取版本号() -> str:
    r"""
    读取 mybiout/version.txt (由 打包.py 写入, 格式 YY.MM.DD.序号)
    :return: str: 版本号
    """
    文件: 路径 = 路径(__file__).resolve().parent / "version.txt"
    if 文件.is_file():
        文本: str = 文件.read_text(encoding="utf-8").strip()
        if 文本:
            return 文本
    return "0.0.0.0"


__version__: str = 取版本号()
