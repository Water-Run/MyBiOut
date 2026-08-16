r"""Wine 下跑 Windows CPython, 验证 win32 分支真实行为。"""

from __future__ import annotations

import sys as 系统
from pathlib import Path as 路径


def 主() -> int:
    失败: list[str] = []

    def 查(名: str, 条件: bool, 详情: str = "") -> None:
        状态 = "OK" if 条件 else "FAIL"
        print(f"[{状态}] {名} {详情}".rstrip())
        if not 条件:
            失败.append(名)

    print("platform=", 系统.platform)
    print("maxsize=", 系统.maxsize)
    查("64bit", 系统.maxsize > 2**32)
    查("win32", 系统.platform == "win32", 系统.platform)

    import mybiout

    版本 = mybiout.__version__.splitlines()[0]
    print("version=", 版本)
    查("版本二六〇八丙", 版本 == "二六〇八丙")
    查("版本越过乙", 版本 != "二六〇八乙")

    from mybiout.pages.utils import 默认设置
    from mybiout.pages.utils import 取默认导出路径
    from mybiout.pages.utils import 打开本地路径

    导出 = 取默认导出路径()
    print("default export=", 导出)
    查("默认导出C盘", 导出 == r"C:\MyBiOut!")
    查("默认设置同步", 默认设置["export"]["path"] == 导出)
    查("完整收藏默认开", 默认设置["mdout"]["favorite_complete"] == "true")

    空开 = 打开本地路径("")
    查("空路径拒绝", 空开.get("ok") is False)

    from mybiout.pages.batch_input import 构建批量文本
    from mybiout.pages.batch_input import 解析批量输入

    查("空解析", 解析批量输入("") == [] and 构建批量文本([]) == "")
    混排 = (
        "https://www.bilibili.com/video/BV1aa411c7mD, "
        "BV1bb411c7mE; av170001，"
        "https://b23.tv/abcdefg、https://www.bilibili.com/video/BV1aa411c7mD"
    )
    项 = 解析批量输入(混排)
    期望 = [
        "https://www.bilibili.com/video/BV1aa411c7mD",
        "BV1bb411c7mE",
        "av170001",
        "https://b23.tv/abcdefg",
    ]
    查("混排解析", 项 == 期望, repr(项))
    查("混排重建", 构建批量文本(项) == "\n".join(期望))

    from mybiout.pages.mdout import mdout as 文档导出

    调用: list[tuple[int, int]] = []

    def 假读取(接口路径: str, 参数: dict) -> dict:
        调用.append((int(参数["pn"]), int(参数["ps"])))
        页 = int(参数["pn"])
        if 页 == 1:
            return {
                "info": {"media_count": 25},
                "medias": [{"bvid": f"BV{i:010d}"} for i in range(1, 21)],
            }
        if 页 == 2:
            return {
                "info": {"media_count": 25},
                "medias": [{"bvid": f"BV{i:010d}"} for i in range(21, 26)],
            }
        return {"info": {"media_count": 25}, "medias": []}

    文档导出._安全接口读取 = 假读取  # type: ignore[method-assign]
    文档导出._延迟 = lambda: None  # type: ignore[assignment]
    全量 = 文档导出.拉取收藏夹内容(1, 完整=True)
    查("完整25条", len(全量["medias"]) == 25, str(len(全量["medias"])))
    查("请求两页", 调用 == [(1, 20), (2, 20)], repr(调用))

    调用.clear()
    半 = 文档导出.拉取收藏夹内容(1, 完整=False)
    查("关闭仅20", len(半["medias"]) == 20 and 调用 == [(1, 20)])

    工程 = 路径(__file__).resolve().parent.parent
    for 相对 in (
        "mybiout/pages/bbdown/bbdown.html",
        "mybiout/pages/mdout/mdout.html",
    ):
        文 = (工程 / 相对).read_text(encoding="utf-8")
        查(f"+控件 {相对}", 'id="btn-multi"' in 文 and 'id="url-multi"' in 文)

    设置页 = (工程 / "mybiout/pages/ohmyconfig/ohmyconfig.html").read_text(encoding="utf-8")
    查("设置完整收藏文案", "导出完整收藏列表" in 设置页)

    print("FAILED", len(失败), 失败)
    return 1 if 失败 else 0


if __name__ == "__main__":
    raise 系统.exit(主())
