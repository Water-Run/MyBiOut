r"""
MyBiOut! 包初始化模块, 定义版本号

:file: mybiout/__init__.py
:author: WaterRun
:time: 2026-03-31
"""

import sys as 系统

if 系统.platform != "win32":
    raise ImportError("MyBiOut! 仅支持 Windows 系统。")

if 系统.maxsize <= 2**32:
    raise ImportError("MyBiOut! 仅支持 64 位 Windows 系统。")

__version__: str = "60314.0"
