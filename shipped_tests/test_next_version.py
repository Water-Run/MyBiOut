r"""
二六〇八丙 入库验收: 驱动已上线入口, 不复刻实现。

覆盖:
- Linux 可导入、版本越过 二六〇八乙、默认导出路径不在 C:\
- /api/parse-batch 同一套 解析批量输入 / 构建批量文本
- 收藏夹完整分页 vs 关闭时只取第 1 页 20 条
- 完整列表开关默认 true
- BBDown / MdOut 有 + 多行控件
"""

from __future__ import annotations

from pathlib import Path as 路径

import mybiout
from mybiout.pages.batch_input import 构建批量文本
from mybiout.pages.batch_input import 解析批量输入
from mybiout.pages.mdout import mdout as 文档导出
from mybiout.pages.utils import 默认设置
from mybiout.pages.utils import 取默认导出路径

_工程根: 路径 = 路径(__file__).resolve().parent.parent
_混排夹具: str = (
    "https://www.bilibili.com/video/BV1aa411c7mD, "
    "BV1bb411c7mE; av170001，"
    "https://b23.tv/abcdefg、https://www.bilibili.com/video/BV1aa411c7mD"
)


def test_导入不因非Windows中止且版本已推进() -> None:
    版本: str = mybiout.__version__.splitlines()[0]
    assert 版本 != "二六〇八乙"
    assert 版本 == "二六〇八丙"


def test_默认导出路径是家目录不是Windows盘符() -> None:
    路径文本: str = 取默认导出路径()
    assert 路径文本.endswith("MyBiOut!")
    assert not 路径文本.startswith("C:\\")
    assert 默认设置["export"]["path"] == 路径文本


def test_解析批量空输入() -> None:
    assert 解析批量输入("") == []
    assert 解析批量输入("   \n\t") == []
    assert 构建批量文本([]) == ""


def test_解析批量单条链接() -> None:
    链接 = "https://www.bilibili.com/video/BV1xx411c7mD"
    assert 解析批量输入(链接) == [链接]


def test_解析批量回车分隔BV() -> None:
    assert 解析批量输入("BV1xx411c7mD\nBV1yy411c7mE\n") == [
        "BV1xx411c7mD",
        "BV1yy411c7mE",
    ]


def test_解析批量混排分界去重并重建() -> None:
    项们 = 解析批量输入(_混排夹具)
    assert 项们 == [
        "https://www.bilibili.com/video/BV1aa411c7mD",
        "BV1bb411c7mE",
        "av170001",
        "https://b23.tv/abcdefg",
    ]
    assert 构建批量文本(项们) == "\n".join(项们)


def test_parse_batch接口与解析函数同一入口() -> None:
    import inspect

    from mybiout.pages import apis as 接口

    源 = inspect.getsource(接口.解析批量输入接口)
    assert "解析批量输入(" in 源
    assert "构建批量文本(" in 源


def test_完整收藏分页合并二十五条(monkeypatch) -> None:
    调用: list[tuple[int, int]] = []

    def 假读取(接口路径: str, 参数: dict) -> dict:
        调用.append((int(参数["pn"]), int(参数["ps"])))
        页码 = int(参数["pn"])
        if 页码 == 1:
            return {
                "info": {"media_count": 25},
                "medias": [{"bvid": f"BV{i:010d}"} for i in range(1, 21)],
            }
        if 页码 == 2:
            return {
                "info": {"media_count": 25},
                "medias": [{"bvid": f"BV{i:010d}"} for i in range(21, 26)],
            }
        return {"info": {"media_count": 25}, "medias": []}

    monkeypatch.setattr(文档导出, "_安全接口读取", 假读取)
    monkeypatch.setattr(文档导出, "_延迟", lambda: None)

    结果 = 文档导出.拉取收藏夹内容(12345, 完整=True)
    assert len(结果["medias"]) == 25
    assert 结果["medias"][0]["bvid"] == "BV0000000001"
    assert 结果["medias"][-1]["bvid"] == "BV0000000025"
    assert 调用 == [(1, 20), (2, 20)]


def test_完整收藏仅一页不再请求(monkeypatch) -> None:
    次数 = {"n": 0}

    def 假读取(接口路径: str, 参数: dict) -> dict:
        次数["n"] += 1
        return {
            "info": {"media_count": 3},
            "medias": [{"bvid": "BVa"}, {"bvid": "BVb"}, {"bvid": "BVc"}],
        }

    monkeypatch.setattr(文档导出, "_安全接口读取", 假读取)
    monkeypatch.setattr(文档导出, "_延迟", lambda: None)

    结果 = 文档导出.拉取收藏夹内容(99, 完整=True)
    assert len(结果["medias"]) == 3
    assert 次数["n"] == 1


def test_关闭完整列表只请求第一页二十条(monkeypatch) -> None:
    调用: list[tuple[int, int]] = []

    def 假读取(接口路径: str, 参数: dict) -> dict:
        调用.append((int(参数["pn"]), int(参数["ps"])))
        return {
            "info": {"media_count": 25},
            "medias": [{"bvid": f"BV{i:010d}"} for i in range(1, 21)],
        }

    monkeypatch.setattr(文档导出, "_安全接口读取", 假读取)
    monkeypatch.setattr(文档导出, "_延迟", lambda: None)

    结果 = 文档导出.拉取收藏夹内容(7, 完整=False)
    assert len(结果["medias"]) == 20
    assert 调用 == [(1, 20)]


def test_完整收藏开关默认打开() -> None:
    import inspect

    assert 默认设置["mdout"]["favorite_complete"] == "true"
    源 = inspect.getsource(文档导出._设置字典)
    assert '"favorite_complete"' in 源
    assert 'or "true"' in 源


def test_用户导出走拉取收藏夹内容入口() -> None:
    import inspect

    源 = inspect.getsource(文档导出._执行获取用户)
    assert "拉取收藏夹内容(" in 源
    assert "完整=完整导出" in 源


def test_BBDown与MdOut有加号多行控件() -> None:
    bb = (_工程根 / "mybiout" / "pages" / "bbdown" / "bbdown.html").read_text(encoding="utf-8")
    md = (_工程根 / "mybiout" / "pages" / "mdout" / "mdout.html").read_text(encoding="utf-8")
    设置 = (_工程根 / "mybiout" / "pages" / "ohmyconfig" / "ohmyconfig.html").read_text(
        encoding="utf-8"
    )
    for 页 in (bb, md):
        assert 'id="btn-multi"' in 页
        assert 'id="url-multi"' in 页
        assert "挂载批量输入" in 页
    assert "导出完整收藏列表" in 设置
    assert 'id="s-mdout-fav-complete"' in 设置
