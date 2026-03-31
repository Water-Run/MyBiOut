r"""
MyBiOut! 主入口模块, 解析命令行参数并启动 FastAPI 服务

:file: mybiout/main.py
:author: WaterRun
:time: 2026-03-31
"""

import argparse
import threading
import time
import webbrowser

import uvicorn

from mybiout.pages.utils import get_port

_BANNER: str = r"""
  __  __       ____  _  ___        _   _
 |  \/  |_   _| __ )(_)/ _ \ _   _| |_| |
 | |\/| | | | |  _ \| | | | | | | | __| |
 | |  | | |_| | |_) | | |_| | |_| | |_|_|
 |_|  |_|\__, |____/|_|\___/ \__,_|\__(_)
         |___/                          !
"""


def main() -> None:
    r"""
    主入口函数, 解析命令行参数并启动 uvicorn 服务
    """
    default_port: int = get_port()

    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        prog="MyBiOut!",
        description="MyBiOut! 综合性一站式开箱即用哔哩哔哩导出工具集",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=default_port,
        help=f"指定服务端口号 (默认: {default_port})",
    )
    args: argparse.Namespace = parser.parse_args()
    port: int = args.port

    print(_BANNER)
    print(f"  ✦ 端口: {port}")
    print(f"  ✦ 访问: http://localhost:{port}")
    print()

    def _open_browser() -> None:
        r"""
        延迟后自动打开浏览器访问本地服务
        """
        time.sleep(1.5)
        webbrowser.open(f"http://localhost:{port}")

    threading.Thread(target=_open_browser, daemon=True).start()

    uvicorn.run(
        "mybiout.pages.apis:app",
        host="127.0.0.1",
        port=port,
        log_level="warning",
    )


if __name__ == "__main__":
    main()
    