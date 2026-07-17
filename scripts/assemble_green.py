r"""
将 PyInstaller 输出组装为可分发的绿色目录, 并旁路复制 bin 工具链

:file: scripts/assemble_green.py
:author: WaterRun
:time: 2026-07-17
"""

from __future__ import annotations

import shutil as 文件工具
import sys as 系统
from pathlib import Path as 路径

仓库根: 路径 = 路径(__file__).resolve().parent.parent
源输出: 路径 = 仓库根 / "dist" / "MyBiOut"
目标输出: 路径 = 仓库根 / "dist" / "MyBiOut-green"
源工具目录: 路径 = 仓库根 / "mybiout" / "bin"
说明模板: str = """# MyBiOut! 绿色版

## 使用方法

1. 解压本目录到任意位置 (可放 U 盘)
2. 双击 `MyBiOut.exe` 启动
3. 关闭窗口即退出程序

## 环境要求

- Windows 11 x64 (兼容 Windows 10 x64 + WebView2)
- 若窗口无法显示, 请安装 Microsoft Edge WebView2 Runtime:
  https://developer.microsoft.com/microsoft-edge/webview2/

## 旁路目录说明

- `config.ini` — 配置文件 (首次运行自动生成/使用内置默认)
- `bin/` — 外部工具 (BBDown.exe / ffmpeg 等), 可自行替换升级
- `auth_profile/` — 扫码登录浏览器资料 (可选功能产生)

## 命令行 (可选)

在目录中打开终端:

```cmd
MyBiOut.exe --port 23333
MyBiOut.exe --browser
MyBiOut.exe --browser --no-animation
```

- `--browser` 使用系统浏览器而非内嵌窗口
- `--port` 指定本地服务端口 (默认 23333)

## 协议

HTTP/API 与页面路由保持稳定。发行形态仅为绿色版 (解压双击 MyBiOut.exe)。

仓库: https://github.com/Water-Run/MyBiOut
"""


def 主流程() -> int:
    r"""
    组装绿色包
    :return: int: 进程退出码
    """
    if not 源输出.is_dir():
        print(f"未找到 PyInstaller 输出: {源输出}")
        print("请先在仓库根目录执行: pyinstaller packaging/MyBiOut.spec")
        return 1

    if 目标输出.exists():
        文件工具.rmtree(目标输出)
    文件工具.copytree(源输出, 目标输出)

    目标工具: 路径 = 目标输出 / "bin"
    if 源工具目录.is_dir():
        if 目标工具.exists():
            文件工具.rmtree(目标工具)
        文件工具.copytree(
            源工具目录,
            目标工具,
            ignore=文件工具.ignore_patterns("__pycache__", "*.pyc", ".git"),
        )

    内置配置: 路径 = 仓库根 / "mybiout" / "config.ini"
    if 内置配置.exists():
        文件工具.copy2(内置配置, 目标输出 / "config.ini")

    (目标输出 / "使用说明.txt").write_text(说明模板, encoding="utf-8")
    print(f"绿色包已组装: {目标输出}")
    print("请运行 scripts/pack_rar.py 或 打包.bat 生成发布 .rar")
    return 0


if __name__ == "__main__":
    系统.exit(主流程())
