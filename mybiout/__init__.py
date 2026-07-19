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
    读取版本号 (格式 YY.MM.DD.序号, 由 打包.py 写入)

    优先绿色根目录 / 运行根旁的 version.txt (与 config.ini 一致的便携心智);
    否则回退包内 / 冻结 _MEIPASS 中的 mybiout/version.txt。
    :return: str: 版本号
    """
    候选: list[路径] = []
    try:
        from mybiout.pages.utils import 取运行根目录

        候选.append(取运行根目录() / "version.txt")
    except Exception:
        pass
    候选.append(路径(__file__).resolve().parent / "version.txt")

    for 文件 in 候选:
        try:
            if 文件.is_file():
                文本: str = 文件.read_text(encoding="utf-8").strip()
                if 文本:
                    return 文本
        except OSError:
            continue
    return "0.0.0.0"


__version__: str = 取版本号()
