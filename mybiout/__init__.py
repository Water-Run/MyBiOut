r"""
MyBiOut! 包初始化模块, 定义版本号

:file: mybiout/__init__.py
:author: WaterRun
:time: 2026-03-31
"""

import sys

if sys.platform != "win32":
    raise ImportError("MyBiOut! 仅支持 Windows 系统。 (MyBiOut! only supports Windows systems.)")

if sys.maxsize <= 2**32:
    raise ImportError("MyBiOut! 仅支持 64 位 Windows 系统。 (MyBiOut! only supports 64-bit Windows systems.)")

__version__: str = "60314.0"
