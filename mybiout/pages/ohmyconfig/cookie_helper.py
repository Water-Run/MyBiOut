r"""
MyBiOut! Windows 管理员权限独立 Cookie 抓取助手

此脚本由主进程以管理员身份 (runas) 启动，用于在必要时使用特权 (例如 shadowcopy) 读取被占用的浏览器数据库，
获取 SESSDATA 并输出至临时文件。
"""

import argparse
import sys
import tempfile
import traceback
from pathlib import Path

# 将项目根目录加入模块路径
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from mybiout.pages.ohmyconfig.ohmyconfig import _auto_get_sessdata_from_browsers


def _append_log(path: Path, text: str) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(text)
    except OSError:
        pass


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True, help="临时输出文件路径")
    parser.add_argument("--ua", default=None, help="目标浏览器的 User Agent")
    parser.add_argument(
        "--debug-log",
        default=str(Path(tempfile.gettempdir()) / "mybiout_cookie_helper_debug.log"),
        help="调试日志路径",
    )
    args = parser.parse_args()

    debug_log = Path(args.debug_log)
    try:
        _append_log(debug_log, "cookie_helper started\n")
        # 以管理员特权运行获取逻辑（包括 shadowcopy 支持）
        sessdata = _auto_get_sessdata_from_browsers(args.ua)
        if sessdata:
            _append_log(debug_log, f"SESSDATA extracted successfully, length={len(sessdata)}\n")
            with Path(args.out).open("w", encoding="utf-8") as f:
                f.write(sessdata.strip())
        else:
            _append_log(debug_log, "SESSDATA extraction returned None\n")
    except Exception:
        _append_log(debug_log, "Exception occurred:\n")
        try:
            with debug_log.open("a", encoding="utf-8") as f:
                traceback.print_exc(file=f)
        except OSError:
            pass

if __name__ == "__main__":
    main()
