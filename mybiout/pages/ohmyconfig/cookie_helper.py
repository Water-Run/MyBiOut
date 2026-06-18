r"""
MyBiOut! Windows 管理员权限独立 Cookie 抓取助手

此脚本由主进程以管理员身份 (runas) 启动，用于在必要时使用特权 (例如 shadowcopy) 读取被占用的浏览器数据库，
获取 SESSDATA 并输出至临时文件。
"""

import argparse
import sys
from pathlib import Path

# 将项目根目录加入模块路径
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from mybiout.pages.ohmyconfig.ohmyconfig import _auto_get_sessdata_from_browsers

def main():
    import traceback
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True, help="临时输出文件路径")
    parser.add_argument("--ua", default=None, help="目标浏览器的 User Agent")
    args = parser.parse_args()

    debug_log = Path("C:/Users/linzh/.gemini/antigravity-cli/brain/69764442-2682-4866-8a4e-2d061a9e403f/scratch/cookie_helper_debug.log")
    try:
        debug_log.write_text("cookie_helper started\n", encoding="utf-8")
        # 以管理员特权运行获取逻辑（包括 shadowcopy 支持）
        sessdata = _auto_get_sessdata_from_browsers(args.ua)
        if sessdata:
            debug_log.open("a", encoding="utf-8").write(f"SESSDATA extracted successfully, length={len(sessdata)}\n")
            with open(args.out, "w", encoding="utf-8") as f:
                f.write(sessdata.strip())
        else:
            debug_log.open("a", encoding="utf-8").write("SESSDATA extraction returned None\n")
    except Exception as e:
        with open(debug_log, "a", encoding="utf-8") as f:
            f.write(f"Exception occurred:\n")
            traceback.print_exc(file=f)

if __name__ == "__main__":
    main()

