"""MyBiOut! 主入口"""

import argparse
import threading
import webbrowser

import uvicorn

from mybiout.pages.utils import get_port

_BANNER = r"""
  __  __       ____  _  ___        _   _
 |  \/  |_   _| __ )(_)/ _ \ _   _| |_| |
 | |\/| | | | |  _ \| | | | | | | | __| |
 | |  | | |_| | |_) | | |_| | |_| | |_|_|
 |_|  |_|\__, |____/|_|\___/ \__,_|\__(_)
         |___/
"""


def main() -> None:
    """主入口函数"""
    default_port = get_port()

    parser = argparse.ArgumentParser(
        prog="MyBiOut!",
        description="MyBiOut! 综合性一站式开箱即用哔哩哔哩导出工具集",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=default_port,
        help=f"指定服务端口号 (默认: {default_port})",
    )
    args = parser.parse_args()
    port: int = args.port

    print(_BANNER)
    print(f"  ✦ 端口: {port}")
    print(f"  ✦ 访问: http://localhost:{port}")
    print()

    def _open_browser() -> None:
        import time
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