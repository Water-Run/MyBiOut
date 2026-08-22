r"""
MdOut! Markdown 导出服务层, 负责从 B 站 API 获取信息并生成 Markdown 文档

:file: mybiout/pages/mdout/mdout.py
:author: WaterRun
:time: 2026-04-06
"""

import json as 数据交换
import re as 正则
import shutil as 文件工具
import threading as 线程
import time as 时间
import uuid as 唯一编号
from contextlib import suppress as 忽略异常
from dataclasses import dataclass as 数据类
from dataclasses import field as 字段
from datetime import datetime as 日期时间
from html.parser import HTMLParser as 网页解析器
from pathlib import Path as 路径

import httpx as 网络请求

from mybiout.pages import utils as 工具

_哔哩请求头: dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.bilibili.com",
    "Origin": "https://www.bilibili.com",
}

_网址模式列表: list[tuple[正则.Pattern[str], str, str]] = [
    (正则.compile(r"(?:https?://)?(?:www\.)?bilibili\.com/video/(BV[\w]{10,})", 正则.I), "video", "bvid"),
    (正则.compile(r"^(BV[\w]{10,})$", 正则.I), "video", "bvid"),
    (正则.compile(r"(?:https?://)?(?:www\.)?bilibili\.com/video/av(\d+)", 正则.I), "video", "avid"),
    (正则.compile(r"^av(\d+)$", 正则.I), "video", "avid"),
    (正则.compile(r"(?:https?://)?(?:www\.)?bilibili\.com/read/cv(\d+)", 正则.I), "article", "cvid"),
    (正则.compile(r"^cv(\d+)$", 正则.I), "article", "cvid"),
    (
        正则.compile(r"(?:https?://)?(?:www\.)?bilibili\.com/read/(?:readlist/)?rl(\d+)", 正则.I),
        "article",
        "rlid",
    ),
    (正则.compile(r"^rl(\d+)$", 正则.I), "article", "rlid"),
    (正则.compile(r"(?:https?://)?(?:www\.)?bilibili\.com/opus/(\d+)", 正则.I), "article", "opusid"),
    (正则.compile(r"(?:https?://)?space\.bilibili\.com/(\d+)", 正则.I), "user", "mid"),
]

_类型标签表: dict[str, str] = {"video": "视频", "user": "用户", "article": "专栏", "unknown": "未知"}


def _生成编号() -> str:
    r"""
    生成 12 位唯一标识
    :return: str: UUID 前 12 位
    """
    return 唯一编号.uuid4().hex[:12]


def _短时间() -> str:
    r"""
    获取当前时间短格式
    :return: str: HH:MM:SS
    """
    return 日期时间.now().strftime("%H:%M:%S")


def _完整时间() -> str:
    r"""
    获取当前时间完整格式
    :return: str: YYYY-MM-DD HH:MM:SS
    """
    return 日期时间.now().strftime("%Y-%m-%d %H:%M:%S")


def _清理文件名(名称: str) -> str:
    r"""
    清理文件名中的非法字符
    :param: name: 原始名称
    :return: str: 安全的文件名
    """
    名称 = 正则.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", 名称).strip(". ")
    return 名称[:200] if 名称 else "untitled"


def _格式化数字(数字: int | None) -> str:
    r"""
    格式化数字为可读字符串
    :param: n: 数字
    :return: str: 格式化后的字符串
    """
    if 数字 is None:
        return "0"
    if 数字 >= 100_000_000:
        return f"{数字 / 100_000_000:.1f}亿"
    if 数字 >= 10_000:
        return f"{数字 / 10_000:.1f}万"
    return str(数字)


def _格式化时长(秒数: int) -> str:
    r"""
    格式化秒数为时长字符串
    :param: 秒数: 秒数
    :return: str: 格式化时长
    """
    小时, 分钟, 秒 = 秒数 // 3600, (秒数 % 3600) // 60, 秒数 % 60
    return f"{小时}:{分钟:02d}:{秒:02d}" if 小时 else f"{分钟}:{秒:02d}"


def _格式化时间戳(时间戳: int) -> str:
    r"""
    格式化 Unix 时间戳为日期字符串
    :param: 时间戳: Unix 时间戳
    :return: str: 格式化日期
    """
    if not 时间戳:
        return ""
    try:
        return 日期时间.fromtimestamp(时间戳).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return ""


def _表格文本(值: object, 默认值: str = "—") -> str:
    r"""把接口文本安全放入 Markdown 表格单元格。"""
    文本: str = str(值 or 默认值).replace("\r", " ").replace("\n", " ")
    return 文本.replace("|", "\\|")


class _专栏HTML转Markdown(网页解析器):
    r"""将 B 站旧专栏正文中的常用 HTML 元素转换为可离线阅读的 Markdown。"""

    def __init__(自身) -> None:
        super().__init__(convert_charrefs=True)
        自身.片段: list[str] = []
        自身.链接栈: list[str] = []
        自身.列表层级: int = 0
        自身.预格式层级: int = 0
        自身.忽略层级: int = 0

    def _写(自身, 文本: str) -> None:
        if 文本:
            自身.片段.append(文本)

    def handle_starttag(自身, 标签: str, 属性列表: list[tuple[str, str | None]]) -> None:
        标签 = 标签.lower()
        属性: dict[str, str] = {键: 值 or "" for 键, 值 in 属性列表}
        if 标签 in {"script", "style"}:
            自身.忽略层级 += 1
            return
        if 自身.忽略层级:
            return
        if 标签 in {"p", "div", "section", "figure", "figcaption"}:
            自身._写("\n\n")
        elif 标签 == "br":
            自身._写("  \n")
        elif 标签 in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            层级: int = min(6, int(标签[1]) + 1)
            自身._写(f"\n\n{'#' * 层级} ")
        elif 标签 in {"ul", "ol"}:
            自身.列表层级 += 1
            自身._写("\n")
        elif 标签 == "li":
            自身._写(f"\n{'  ' * max(0, 自身.列表层级 - 1)}- ")
        elif 标签 == "blockquote":
            自身._写("\n\n> ")
        elif 标签 in {"strong", "b"}:
            自身._写("**")
        elif 标签 in {"em", "i"}:
            自身._写("*")
        elif 标签 in {"del", "s"}:
            自身._写("~~")
        elif 标签 == "code" and not 自身.预格式层级:
            自身._写("`")
        elif 标签 == "pre":
            自身.预格式层级 += 1
            自身._写("\n\n```text\n")
        elif 标签 == "a":
            地址: str = 属性.get("href", "").strip()
            自身.链接栈.append(地址)
            自身._写("[")
        elif 标签 == "img":
            地址 = 属性.get("data-src", "") or 属性.get("src", "")
            if 地址.startswith("//"):
                地址 = f"https:{地址}"
            if 地址:
                自身._写(f"\n\n![{属性.get('alt', '图片')}]({地址})\n\n")
        elif 标签 == "hr":
            自身._写("\n\n---\n\n")

    def handle_endtag(自身, 标签: str) -> None:
        标签 = 标签.lower()
        if 标签 in {"script", "style"}:
            自身.忽略层级 = max(0, 自身.忽略层级 - 1)
            return
        if 自身.忽略层级:
            return
        if 标签 in {"p", "div", "section", "figure", "figcaption", "blockquote"}:
            自身._写("\n\n")
        elif 标签 in {"h1", "h2", "h3", "h4", "h5", "h6", "li"}:
            自身._写("\n")
        elif 标签 in {"ul", "ol"}:
            自身.列表层级 = max(0, 自身.列表层级 - 1)
            自身._写("\n")
        elif 标签 in {"strong", "b"}:
            自身._写("**")
        elif 标签 in {"em", "i"}:
            自身._写("*")
        elif 标签 in {"del", "s"}:
            自身._写("~~")
        elif 标签 == "code" and not 自身.预格式层级:
            自身._写("`")
        elif 标签 == "pre":
            自身._写("\n```\n\n")
            自身.预格式层级 = max(0, 自身.预格式层级 - 1)
        elif 标签 == "a":
            地址: str = 自身.链接栈.pop() if 自身.链接栈 else ""
            自身._写(f"]({地址})" if 地址 else "]")

    def handle_data(自身, 数据: str) -> None:
        if 自身.忽略层级 or not 数据:
            return
        if 自身.预格式层级:
            自身._写(数据)
            return
        文本: str = 正则.sub(r"[\t\r\f\v ]+", " ", 数据)
        文本 = 正则.sub(r"\n+", " ", 文本)
        自身._写(文本)

    def 取结果(自身) -> str:
        文本: str = "".join(自身.片段)
        文本 = 正则.sub(r"[ \t]+\n", "\n", 文本)
        文本 = 正则.sub(r"\n{3,}", "\n\n", 文本)
        return 文本.strip()


def _专栏正文转Markdown(网页正文: str) -> str:
    if not 网页正文.strip():
        return ""
    转换器 = _专栏HTML转Markdown()
    try:
        转换器.feed(网页正文)
        转换器.close()
        return 转换器.取结果()
    except Exception:
        # Markdown 可直接容纳 HTML，极少数异常正文仍保留原文而不是整篇丢失。
        return 网页正文.strip()


def _客户端() -> 网络请求.Client:
    r"""
    创建带认证的 HTTP 客户端
    :return: httpx.Client: HTTP 客户端
    """
    会话数据: str = 工具.取会话数据().strip()
    曲奇: dict[str, str] = {"SESSDATA": 会话数据} if 会话数据 else {}
    return 网络请求.Client(headers=_哔哩请求头, cookies=曲奇, timeout=20.0, follow_redirects=True)


def _延迟() -> None:
    r"""
    根据设置执行请求间隔延迟
    """
    try:
        延迟秒数: float = float(工具.取设置("mdout", "request_delay") or "0.5")
    except ValueError:
        延迟秒数 = 0.5
    时间.sleep(max(0.1, 延迟秒数))


def 解析输入(文本: str) -> dict[str, str]:
    r"""
    解析用户输入, 识别类型和 ID
    :param: 文本: 用户输入文本
    :return: dict[str, str]: 解析结果
    """
    文本 = 文本.strip()
    if not 文本:
        return {"type": "unknown", "id_type": "", "id_value": "", "label": ""}

    if 短链 := 正则.match(r"(?:https?://)?b23\.tv/([\w]+)", 文本, 正则.I):
        try:
            with _客户端() as 客户端:
                响应: 网络请求.Response = 客户端.head(f"https://b23.tv/{短链.group(1)}")
                return 解析输入(str(响应.headers.get("location", 响应.url)))
        except Exception:
            return {"type": "unknown", "id_type": "", "id_value": 文本, "label": "短链解析失败"}

    for 模式, 项目类型, 编号类型 in _网址模式列表:
        if 媒体项 := 模式.search(文本):
            return {"type": 项目类型, "id_type": 编号类型, "id_value": 媒体项.group(1), "label": _类型标签表[项目类型]}

    if 正则.match(r"^\d{1,15}$", 文本):
        return {"type": "user", "id_type": "mid", "id_value": 文本, "label": "用户"}

    return {"type": "unknown", "id_type": "", "id_value": 文本, "label": "无法识别"}


def _接口读取(接口路径: str, 参数: dict) -> dict:
    r"""
    调用 B 站 API 并返回 data 字段
    :param: path: API 路径
    :param: params: 查询参数
    :return: dict: API 返回的 data 字段
    :raise: RuntimeError: API 返回非零 code
    """
    with _客户端() as 客户端:
        响应: 网络请求.Response = 客户端.get(f"https://api.bilibili.com{接口路径}", params=参数)
        数据: dict = 响应.json()
    if 数据.get("code") != 0:
        raise RuntimeError(数据.get("message", "API 未知错误"))
    return 数据.get("data", {})


def _安全接口读取(接口路径: str, 参数: dict) -> dict:
    r"""
    安全调用 B 站 API, 异常时返回空字典
    :param: path: API 路径
    :param: params: 查询参数
    :return: dict: API 返回的 data 字段或空字典
    """
    try:
        return _接口读取(接口路径, 参数)
    except Exception:
        return {}


def _获取视频(BV号: str = "", AV号: str = "") -> dict:
    r"""
    获取视频详细信息
    :param: bvid: BV 号
    :param: avid: av 号
    :return: dict: 视频信息
    """
    参数: dict[str, str] = {}
    if BV号:
        参数["bvid"] = BV号
    elif AV号:
        参数["aid"] = AV号
    return _接口读取("/x/web-interface/view", 参数)


def _获取视频标签(BV号: str = "", AV号: str = "") -> list:
    r"""
    获取视频标签列表
    :param: bvid: BV 号
    :param: avid: av 号
    :return: list: 标签列表
    """
    参数: dict[str, str] = {}
    if BV号:
        参数["bvid"] = BV号
    elif AV号:
        参数["aid"] = AV号
    return _安全接口读取("/x/tag/archive/tags", 参数) or []


def _获取用户卡片(用户号: str) -> dict:
    r"""
    获取用户卡片信息
    :param: mid: 用户 UID
    :return: dict: 用户卡片数据
    """
    return _接口读取("/x/web-interface/card", {"mid": 用户号, "photo": "true"})


def _获取用户统计(用户号: str) -> dict:
    r"""
    获取 UP 主统计信息
    :param: mid: 用户 UID
    :return: dict: 统计数据
    """
    return _安全接口读取("/x/space/upstat", {"mid": 用户号})


def _获取收藏夹列表(用户号: str) -> list:
    r"""
    获取用户收藏夹列表
    :param: mid: 用户 UID
    :return: list: 收藏夹列表
    """
    数据: dict = _安全接口读取("/x/v3/fav/folder/created/list-all", {"up_mid": 用户号})
    return 数据.get("list", []) or [] if isinstance(数据, dict) else []


def _获取收藏内容(收藏夹编号: int, 页码: int = 1, 每页数量: int = 20) -> dict:
    r"""
    获取收藏夹内容
    :param: media_id: 收藏夹 ID
    :param: pn: 页码
    :param: ps: 每页数量
    :return: dict: 收藏夹内容
    """
    return _安全接口读取("/x/v3/fav/resource/list", {"media_id": 收藏夹编号, "pn": 页码, "ps": 每页数量})


def _获取收藏全部内容(
    收藏夹编号: int,
    *,
    每页数量: int = 20,
    取消事件: 线程.Event | None = None,
) -> dict:
    r"""
    分页拉完一个收藏夹的全部媒体项 (默认每页 20, 直到 media_count 或空页)。
    """
    首包: dict = _获取收藏内容(收藏夹编号, 页码=1, 每页数量=每页数量)
    if not 首包:
        return {}
    媒体列表: list = list(首包.get("medias") or [])
    信息: dict = 首包.get("info") or {}
    try:
        总数: int = int(信息.get("media_count") or 0)
    except (TypeError, ValueError):
        总数 = 0
    已见: set[object] = set()
    去重后: list = []
    for 媒体 in 媒体列表:
        键 = 媒体.get("id") if isinstance(媒体, dict) else None
        if 键 is None and isinstance(媒体, dict):
            键 = 媒体.get("bvid")
        if 键 in 已见:
            continue
        if 键 is not None:
            已见.add(键)
        去重后.append(媒体)
    媒体列表 = 去重后
    页码: int = 2
    # 不设人为页数上限；空页、无新项、media_count 与取消标记已能收敛。
    # 这样大型收藏夹也不会在 10000 条处被静默截断。
    while 总数 <= 0 or len(媒体列表) < 总数:
        if 取消事件 is not None and 取消事件.is_set():
            break
        if 总数 > 0 and len(媒体列表) >= 总数:
            break
        _延迟()
        包: dict = _获取收藏内容(收藏夹编号, 页码=页码, 每页数量=每页数量)
        本页: list = list((包 or {}).get("medias") or [])
        if not 本页:
            break
        新增: int = 0
        for 媒体 in 本页:
            键 = 媒体.get("id") if isinstance(媒体, dict) else None
            if 键 is None and isinstance(媒体, dict):
                键 = 媒体.get("bvid")
            if 键 in 已见:
                continue
            if 键 is not None:
                已见.add(键)
            媒体列表.append(媒体)
            新增 += 1
        if 新增 == 0:
            break
        页码 += 1
    return {"info": 信息, "medias": 媒体列表}


def 拉取收藏夹内容(
    收藏夹编号: int,
    *,
    完整: bool,
    取消事件: 线程.Event | None = None,
) -> dict:
    r"""
    用户页导出用的收藏夹拉取入口。
    完整=True 逐页拉全量; 完整=False 只取第 1 页 20 条。
    """
    if 完整:
        return _获取收藏全部内容(收藏夹编号, 取消事件=取消事件)
    return _获取收藏内容(收藏夹编号, 页码=1, 每页数量=20)


def _获取专栏(专栏号: str) -> dict:
    r"""
    获取专栏文章信息与正文；旧稿异常时回退到基础信息接口。
    :param: cvid: 专栏 cv 号
    :return: dict: 专栏信息
    """
    try:
        信息: dict = _接口读取(
            "/x/article/view",
            {"id": 专栏号, "web_location": "333.976"},
        )
        if 信息.get("content") or 信息.get("opus") or 信息.get("id"):
            return 信息
    except Exception:
        pass

    # 旧专栏正在逐步迁移为 opus；read/cv 页面会 301 到对应 opus，页面内仍有完整正文。
    try:
        with _客户端() as 客户端:
            响应: 网络请求.Response = 客户端.get(f"https://www.bilibili.com/read/cv{专栏号}")
        if 响应.status_code == 200 and "/opus/" in str(响应.url):
            详情: dict = _解析动态页面(响应.text)
            return {"id": int(专栏号), "_opus_detail": 详情}
    except Exception:
        pass

    基础信息: dict = _安全接口读取("/x/article/viewinfo", {"id": 专栏号})
    if 基础信息:
        基础信息.setdefault("id", int(专栏号))
    return 基础信息


def _获取专栏文集(文集号: str) -> dict:
    r"""获取 rl 文集概览及其中全部专栏条目。"""
    return _接口读取("/x/article/list/web/articles", {"id": 文集号})


def _获取动态专栏(动态号: str) -> dict:
    r"""
    获取 opus 动态/图文专栏详情

    动态详情 JSON 接口有风控 (-352), 改解析 opus 页面内嵌的
    ``window.__INITIAL_STATE__`` —— 标题、作者、统计与正文段落树都在其中。
    :param: 动态号: opus 动态 ID
    :return: dict: detail 字典
    :raise: RuntimeError: 页面请求失败或无可解析数据
    """
    with _客户端() as 客户端:
        响应: 网络请求.Response = 客户端.get(f"https://www.bilibili.com/opus/{动态号}")
    if 响应.status_code != 200:
        raise RuntimeError(f"动态页面请求失败 (HTTP {响应.status_code})")
    return _解析动态页面(响应.text)


def _解析动态页面(网页文本: str) -> dict:
    r"""从 opus 页面内嵌的 INITIAL_STATE 中提取正文详情。"""
    匹配 = 正则.search(r"window\.__INITIAL_STATE__=(.*?);\(function", 网页文本, 正则.S)
    if not 匹配:
        raise RuntimeError("动态页面无可解析数据 (可能被风控拦截)")
    try:
        初始状态: dict = 数据交换.loads(匹配.group(1))
    except ValueError:
        raise RuntimeError("动态页面数据解析失败") from None
    详情: dict = 初始状态.get("detail") or {}
    if not 详情.get("id_str"):
        raise RuntimeError("动态不存在或已删除")
    return 详情


def _节点组Markdown(节点列表: list) -> str:
    r"""
    将 opus 富文本节点组转换为 Markdown 片段
    :param: 节点列表: text.nodes 列表
    :return: str: Markdown 片段
    """
    片段列表: list[str] = []
    for 节点 in 节点列表:
        类型: str | int = 节点.get("type", 节点.get("node_type", ""))
        if 类型 in {"TEXT_NODE_TYPE_WORD", 1} or isinstance(节点.get("word"), dict):
            词: dict = 节点.get("word") or {}
            文本: str = 词.get("words", "")
            if 文本.strip():
                样式: dict = 词.get("style") or {}
                if 样式.get("bold"):
                    文本 = f"**{文本}**"
                if 样式.get("italic"):
                    文本 = f"*{文本}*"
                if 样式.get("strikethrough"):
                    文本 = f"~~{文本}~~"
            片段列表.append(文本)
        elif 类型 in {"TEXT_NODE_TYPE_RICH", 2} or isinstance(节点.get("rich"), dict):
            富文: dict = 节点.get("rich") or {}
            文本 = 富文.get("text", "")
            if not 文本:
                continue
            跳转: str = 富文.get("jump_url", "") or ""
            if 跳转.startswith("//"):
                跳转 = "https:" + 跳转
            片段列表.append(f"[{文本}]({跳转})" if 跳转 else 文本)
        elif 类型 in {"TEXT_NODE_TYPE_FORMULA", 3} or isinstance(节点.get("formula"), dict):
            公式: dict = 节点.get("formula") or {}
            内容: str = 公式.get("latex_content", "") or 公式.get("content", "")
            if 内容:
                片段列表.append(f"${内容}$")
    return "".join(片段列表)


def _段落文本Markdown(段落: dict) -> str:
    r"""提取段落的纯文本行 (软换行转为 Markdown 硬换行)"""
    节点列表: list = (段落.get("text") or {}).get("nodes", []) or []
    return _节点组Markdown(节点列表).replace("\n", "  \n")


def _段落Markdown(段落: dict) -> list[str]:
    r"""
    将 opus 单个段落转换为 Markdown 行 (按非空字段识别段落类型, 兼容未知 para_type)
    :param: 段落: paragraphs 项
    :return: list[str]: Markdown 行列表
    """
    if 段落.get("heading") is not None:
        标题内容: dict = 段落.get("heading") or {}
        文本: str = _节点组Markdown((标题内容.get("text") or {}).get("nodes", []) or [])
        级别: int = 标题内容.get("level", 2) or 2
        return [f"{'#' * min(6, max(2, int(级别)))} {文本}".rstrip(), ""]
    if 段落.get("pic") is not None:
        图片组: list = (段落.get("pic") or {}).get("pics", []) or []
        行: list[str] = [f"![图片]({图['url']})" for 图 in 图片组 if 图.get("url")]
        return 行 + [""] if 行 else []
    if 段落.get("line") is not None:
        分隔图: str = str(((段落.get("line") or {}).get("pic") or {}).get("url") or "")
        if 分隔图:
            if 分隔图.startswith("//"):
                分隔图 = "https:" + 分隔图
            return [f"![分隔图]({分隔图})", ""]
        return ["---", ""]
    if 段落.get("blockquote") is not None:
        引用行: list[str] = []
        for 子段 in (段落.get("blockquote") or {}).get("children", []) or []:
            引用行.extend(f"> {子行}".rstrip() for 子行 in _段落Markdown(子段))
        return 引用行 + [""] if 引用行 else []
    if 段落.get("list") is not None:
        列表: dict = 段落.get("list") or {}
        有序: bool = 列表.get("style") == 2
        列表行: list[str] = []
        for 项 in 列表.get("children", []) or 列表.get("items", []) or []:
            首行: bool = True
            for 子段 in 项.get("children", []) or []:
                for 子行 in (行 for 行 in _段落Markdown(子段) if 行.strip()):
                    if 首行:
                        序号: int = 项.get("order", 1) or 1
                        列表行.append(f"{序号}. {子行}" if 有序 else f"- {子行}")
                        首行 = False
                    else:
                        列表行.append(f"  {子行}")
        return 列表行 + [""] if 列表行 else []
    if 段落.get("code") is not None:
        代码: dict = 段落.get("code") or {}
        语言: str = 代码.get("lang", "") or ""
        内容: str = str(代码.get("content", "")).rstrip("\n")
        return [f"```{语言}", 内容, "```", ""]
    if 段落.get("link_card") is not None:
        卡片: dict = 段落.get("link_card") or {}
        链接: str = 卡片.get("url", "") or ""
        标题: str = 卡片.get("title", "") or 链接
        return [f"[{标题}]({链接})", ""] if 链接 else []
    文本 = _段落文本Markdown(段落)
    return [文本, ""] if 文本.strip() else []


def _动态标题(详情: dict) -> str:
    r"""
    从 opus 详情中提取标题
    :param: 详情: detail 字典
    :return: str: 标题 (可能为空)
    """
    for 模块 in 详情.get("modules", []):
        if 标题模块 := 模块.get("module_title"):
            if 文本 := 标题模块.get("text", ""):
                return 文本
    return (详情.get("basic") or {}).get("title", "")


def _动态Markdown(详情: dict, 配置: dict) -> str:
    r"""
    由 opus 动态详情生成 Markdown 文档 (含正文)
    :param: 详情: __INITIAL_STATE__.detail
    :param: 配置: 导出配置
    :return: str: Markdown 文本
    """
    动态号: str = 详情.get("id_str", "")
    标题: str = _动态标题(详情) or "未知动态"
    作者名: str = ""
    作者号: str = ""
    发布时间戳: int = 0
    统计: dict = {}
    段落列表: list = []

    for 模块 in 详情.get("modules", []):
        if 作者模块 := 模块.get("module_author"):
            作者名 = 作者名 or 作者模块.get("name", "") or ""
            作者号 = 作者号 or str(作者模块.get("mid", "") or "")
            发布时间戳 = 发布时间戳 or int(作者模块.get("pub_ts", 0) or 0)
        if 统计模块 := 模块.get("module_stat"):
            统计 = 统计 or 统计模块
        if 内容模块 := 模块.get("module_content"):
            段落列表 = 段落列表 or 内容模块.get("paragraphs", []) or []

    行列表: list[str] = [
        f"# {标题}\n",
        f"> 动态 opus{动态号} | https://www.bilibili.com/opus/{动态号}",
        f"> 导出时间: {_完整时间()}\n",
    ]

    行列表.extend(["## 基本信息\n", "| 项目 | 内容 |", "|------|------|"])
    if 作者名 or 作者号:
        行列表.append(f"| 作者 | {作者名 or 作者号} |")
    if 作者号:
        行列表.append(f"| UID | {作者号} |")
    if 发布时间戳:
        行列表.append(f"| 发布时间 | {_格式化时间戳(发布时间戳)} |")
    行列表.append("")

    if 配置.get("include_stats") == "true" and 统计:
        统计行: list[str] = []
        for 键, 标签名 in [("forward", "转发"), ("comment", "评论"), ("like", "点赞"), ("coin", "投币")]:
            项: dict = 统计.get(键) or {}
            if 项.get("hidden"):
                continue
            统计行.append(f"| {标签名} | {_格式化数字(项.get('count', 0))} |")
        if 统计行:
            行列表.extend(["## 数据统计\n", "| 指标 | 数值 |", "|------|------|", *统计行, ""])

    if 段落列表:
        行列表.append("## 正文\n")
        for 段落 in 段落列表:
            行列表.extend(_段落Markdown(段落))

    行列表.extend(["---", f"*由 MyBiOut! MdOut 导出于 {_完整时间()}*"])
    return "\n".join(行列表)


def _视频Markdown(信息: dict, 标签: list, 配置: dict) -> str:
    r"""
    生成视频信息 Markdown 文档
    :param: info: 视频信息字典
    :param: tags: 标签列表
    :param: cfg: 导出配置
    :return: str: Markdown 文本
    """
    标题: str = 信息.get("title", "未知标题")
    BV号: str = 信息.get("bvid", "")
    AV号: str = 信息.get("aid", "")
    简介: str = 信息.get("desc", "")
    作者信息: dict = 信息.get("owner", {})
    统计: dict = 信息.get("stat", {})
    分页列表: list = 信息.get("pages", [])
    封面: str = 信息.get("pic", "")

    行列表: list[str] = [
        f"# {标题}\n",
        f"> {BV号} | av{AV号}",
        f"> 导出时间: {_完整时间()}\n",
    ]

    if 配置.get("include_cover") == "true" and 封面:
        行列表.append(f"![封面]({封面})\n")

    行列表.extend(
        [
            "## 基本信息\n",
            "| 项目 | 内容 |",
            "|------|------|",
            f"| UP主 | [{作者信息.get('name', '—')}](https://space.bilibili.com/{作者信息.get('mid', '')}) |",
            f"| 发布时间 | {_格式化时间戳(信息.get('pubdate', 0))} |",
            f"| 分区 | {信息.get('tname', '')} |",
            f"| 时长 | {_格式化时长(信息.get('duration', 0))} |",
            f"| 链接 | https://www.bilibili.com/video/{BV号} |",
            "",
        ]
    )

    if 配置.get("include_stats") == "true":
        行列表.extend(["## 数据统计\n", "| 指标 | 数值 |", "|------|------|"])
        for 键, 标签名 in [
            ("view", "播放"),
            ("danmaku", "弹幕"),
            ("reply", "评论"),
            ("like", "点赞"),
            ("coin", "投币"),
            ("favorite", "收藏"),
            ("share", "转发"),
        ]:
            行列表.append(f"| {标签名} | {_格式化数字(统计.get(键, 0))} |")
        行列表.append("")

    if 简介:
        行列表.extend(["## 简介\n", 简介 + "\n"])

    if 配置.get("include_tags") == "true" and isinstance(标签, list):
        标签文本列表: list[str] = [f"`{标签项.get('tag_name', '')}`" for 标签项 in 标签 if 标签项.get("tag_name")]
        if 标签文本列表:
            行列表.extend(["## 标签\n", " ".join(标签文本列表) + "\n"])

    if len(分页列表) > 1:
        行列表.extend(["## 分P列表\n", "| P | 标题 | 时长 |", "|---|------|------|"])
        行列表.extend(
            f"| P{分P.get('page', '')} | {分P.get('part', '')} | {_格式化时长(分P.get('duration', 0))} |" for 分P in 分页列表
        )
        行列表.append("")

    行列表.extend(["---", f"*由 MyBiOut! MdOut 导出于 {_完整时间()}*"])
    return "\n".join(行列表)


def _用户Markdown(卡片数据: dict, 用户统计: dict, 收藏夹列表: list, 收藏内容: dict, 配置: dict) -> str:
    r"""
    生成用户信息 Markdown 文档
    :param: card_data: 用户卡片数据
    :param: upstat: UP 主统计数据
    :param: favorites: 收藏夹列表
    :param: fav_contents: 收藏夹内容映射
    :param: cfg: 导出配置
    :return: str: Markdown 文本
    """
    卡片: dict = 卡片数据.get("card", {})
    名称: str = 卡片.get("name", "未知用户")
    用户号: str = 卡片.get("mid", "")
    签名: str = 卡片.get("sign", "")
    级别: int = 卡片.get("level_info", {}).get("current_level", 0)
    头像: str = 卡片.get("face", "")
    性别: str = 卡片.get("sex", "")
    粉丝数: int = 卡片数据.get("follower", 0) or 卡片.get("fans", 0)
    关注数: int = 卡片.get("attention", 0) or 卡片.get("friend", 0)
    投稿数: int = 卡片数据.get("archive_count", 0)
    获赞数: int = 卡片数据.get("like_num", 0)
    认证标题: str = (卡片.get("Official") or {}).get("title", "")

    行列表: list[str] = [
        f"# {名称}\n",
        f"> UID: {用户号}",
        f"> 导出时间: {_完整时间()}\n",
    ]

    if 配置.get("include_cover") == "true" and 头像:
        行列表.append(f"![头像]({头像})\n")

    行列表.extend(["## 基本信息\n", "| 项目 | 内容 |", "|------|------|", f"| 昵称 | {名称} |", f"| UID | {用户号} |"])
    if 性别 and 性别 != "保密":
        行列表.append(f"| 性别 | {性别} |")
    行列表.append(f"| 等级 | Lv.{级别} |")
    if 认证标题:
        行列表.append(f"| 认证 | {认证标题} |")
    if 签名:
        行列表.append(f"| 签名 | {签名} |")
    行列表.extend([f"| 空间链接 | https://space.bilibili.com/{用户号} |", ""])

    if 配置.get("include_stats") == "true":
        行列表.extend(["## 数据统计\n", "| 指标 | 数值 |", "|------|------|"])
        行列表.extend(
            [
                f"| 粉丝 | {_格式化数字(粉丝数)} |",
                f"| 关注 | {_格式化数字(关注数)} |",
                f"| 投稿视频 | {投稿数} |",
            ]
        )
        if 获赞数:
            行列表.append(f"| 获赞 | {_格式化数字(获赞数)} |")
        if 用户统计:
            if 视频播放量 := 用户统计.get("archive", {}).get("view", 0):
                行列表.append(f"| 视频总播放 | {_格式化数字(视频播放量)} |")
            if 文章阅读量 := 用户统计.get("article", {}).get("view", 0):
                行列表.append(f"| 文章总阅读 | {_格式化数字(文章阅读量)} |")
        行列表.append("")

    if 收藏夹列表:
        行列表.append("## 收藏夹\n")
        详细模式: str = 配置.get("favorite_detail", "basic")
        完整导出: bool = 配置.get("favorite_complete", "true") == "true"
        要列出内容: bool = 完整导出 or 详细模式 == "full"
        for 收藏夹 in 收藏夹列表:
            收藏夹编号值: int = 收藏夹.get("id", 0)
            行列表.extend([f"### {收藏夹.get('title', '未命名')}\n", f"共 {收藏夹.get('media_count', 0)} 个内容\n"])
            if 要列出内容 and 收藏夹编号值 in 收藏内容:
                媒体列表: list = 收藏内容[收藏夹编号值].get("medias") or []
                if 媒体列表:
                    行列表.extend(["| # | 标题 | UP主 | BV号 |", "|---|------|------|------|"])
                    for 序号, 媒体项 in enumerate(媒体列表, 1):
                        媒体数据: dict = 媒体项 if isinstance(媒体项, dict) else {}
                        作者数据: dict = (
                            媒体数据.get("upper")
                            if isinstance(媒体数据.get("upper"), dict)
                            else {}
                        )
                        行列表.append(
                            f"| {序号} | {_表格文本(媒体数据.get('title'))} "
                            f"| {_表格文本(作者数据.get('name'))} "
                            f"| {_表格文本(媒体数据.get('bvid'))} |"
                        )
                    总数: int = 收藏内容[收藏夹编号值].get("info", {}).get("media_count", 收藏夹.get("media_count", 0))
                    if len(媒体列表) < 总数:
                        行列表.append(f"\n*（仅显示前 {len(媒体列表)} 项，共 {总数} 项）*")
                    行列表.append("")

    行列表.extend(["---", f"*由 MyBiOut! MdOut 导出于 {_完整时间()}*"])
    return "\n".join(行列表)


def _专栏Markdown(信息: dict, 配置: dict) -> str:
    r"""
    生成专栏文章 Markdown 文档
    :param: info: 专栏信息字典
    :param: cfg: 导出配置
    :return: str: Markdown 文本
    """
    if isinstance(信息.get("_opus_detail"), dict):
        return _动态Markdown(信息["_opus_detail"], 配置)

    标题: str = 信息.get("title", "未知专栏")
    统计项: dict = 信息.get("stats", {})
    头图: str = 信息.get("banner_url", "")
    作者信息: dict = 信息.get("author", {}) if isinstance(信息.get("author"), dict) else {}

    行列表: list[str] = [
        f"# {标题}\n",
        f"> 专栏 cv{信息.get('id', '')}",
        f"> 导出时间: {_完整时间()}\n",
    ]

    if 配置.get("include_cover") == "true" and 头图:
        行列表.append(f"![头图]({头图})\n")

    行列表.extend(["## 基本信息\n", "| 项目 | 内容 |", "|------|------|"])
    if 作者 := (
        信息.get("author_name", "")
        or 作者信息.get("name", "")
        or str(信息.get("mid", "") or 作者信息.get("mid", ""))
    ):
        行列表.append(f"| 作者 | {作者} |")
    if 发布时间 := 信息.get("publish_time", 0):
        行列表.append(f"| 发布时间 | {_格式化时间戳(发布时间)} |")
    if 信息.get("id"):
        行列表.append(f"| 链接 | https://www.bilibili.com/read/cv{信息.get('id', '')} |")
    行列表.append("")

    if 配置.get("include_tags") == "true" and (标签们 := 信息.get("tags")):
        标签名称: list[str] = [
            str(项.get("name", ""))
            for 项 in 标签们
            if isinstance(项, dict) and 项.get("name")
        ]
        if 标签名称:
            行列表.append(f"**标签:** {', '.join(标签名称)}\n")

    if 配置.get("include_stats") == "true" and 统计项:
        行列表.extend(["## 数据统计\n", "| 指标 | 数值 |", "|------|------|"])
        for 键, 标签名 in [
            ("view", "阅读"),
            ("like", "点赞"),
            ("reply", "评论"),
            ("favorite", "收藏"),
            ("coin", "投币"),
            ("share", "转发"),
        ]:
            行列表.append(f"| {标签名} | {_格式化数字(统计项.get(键, 0))} |")
        行列表.append("")

    if 摘要 := str(信息.get("summary", "") or "").strip():
        行列表.extend(["## 摘要\n", 摘要, ""])

    专栏动态数据: dict = 信息.get("opus") if isinstance(信息.get("opus"), dict) else {}
    动态正文数据: dict = (
        专栏动态数据.get("content")
        if isinstance(专栏动态数据.get("content"), dict)
        else {}
    )
    动态段落列表: list = (
        动态正文数据.get("paragraphs", [])
        if isinstance(动态正文数据.get("paragraphs"), list)
        else []
    )
    if 动态段落列表:
        行列表.append("## 正文\n")
        for 段落 in 动态段落列表:
            if isinstance(段落, dict):
                行列表.extend(_段落Markdown(段落))
    else:
        正文: str = _专栏正文转Markdown(str(信息.get("content", "") or ""))
        if 正文:
            行列表.extend(["## 正文\n", 正文, ""])

    行列表.extend(["---", f"*由 MyBiOut! MdOut 导出于 {_完整时间()}*"])
    return "\n".join(行列表)


def _文集索引Markdown(文集数据: dict, 文档列表: list[dict[str, str]], 配置: dict) -> str:
    r"""生成文集目录页，链接到同目录下逐篇导出的 Markdown。"""
    概览: dict = 文集数据.get("list", {}) if isinstance(文集数据.get("list"), dict) else {}
    作者: dict = 文集数据.get("author", {}) if isinstance(文集数据.get("author"), dict) else {}
    标题: str = str(概览.get("name") or "未命名文集")
    行列表: list[str] = [
        f"# {标题}\n",
        f"> 专栏文集 rl{概览.get('id', '')}",
        f"> 共 {len(文档列表)} 篇 · 导出时间: {_完整时间()}\n",
    ]
    封面: str = str(概览.get("image_url") or "")
    if 配置.get("include_cover") == "true" and 封面:
        行列表.append(f"![文集封面]({封面})\n")
    if 作者名 := str(作者.get("name") or 概览.get("author_name") or ""):
        行列表.append(f"**作者:** {作者名}\n")
    if 简介 := str(概览.get("summary") or "").strip():
        行列表.extend(["## 简介\n", 简介, ""])
    行列表.extend(["## 目录\n", "| # | 文章 | 原链接 |", "|---:|------|--------|"])
    for 序号, 文档 in enumerate(文档列表, 1):
        标题文本: str = _表格文本(文档.get("title"), "未命名")
        文件名: str = 文档.get("filename", "")
        专栏号: str = 文档.get("cvid", "")
        行列表.append(
            f"| {序号} | [{标题文本}](<{文件名}>) | "
            f"[cv{专栏号}](https://www.bilibili.com/read/cv{专栏号}) |"
        )
    行列表.extend(["", "---", f"*由 MyBiOut! MdOut 批量导出于 {_完整时间()}*"])
    return "\n".join(行列表)


@数据类(slots=True)
class 文档卡片:
    r"""
    Markdown 导出卡片数据模型
    """

    编号: str = 字段(default_factory=_生成编号)
    输入文本: str = ""
    项目类型: str = "unknown"
    编号类型: str = ""
    编号值: str = ""
    标题: str = ""
    副标题: str = ""
    Markdown文本: str = ""
    批量文档列表: list[dict[str, str]] = 字段(default_factory=list)
    状态名: str = "pending"
    错误: str = ""
    文件名: str = ""
    输出路径: str = ""

    def 转字典(自身) -> dict:
        r"""
        转换为前端可用的字典
        :return: dict: 卡片字典
        """
        return {
            "id": 自身.编号,
            "input_text": 自身.输入文本,
            "item_type": 自身.项目类型,
            "id_value": 自身.编号值,
            "title": 自身.标题,
            "subtitle": 自身.副标题,
            "has_markdown": bool(自身.Markdown文本),
            "batch_count": len(自身.批量文档列表),
            "status": 自身.状态名,
            "error": 自身.错误,
            "filename": 自身.文件名,
            "output_path": 自身.输出路径,
        }


class _文档状态:
    r"""
    MdOut 全局运行状态管理
    """

    def __init__(自身) -> None:
        r"""
        初始化全局状态
        """
        自身.锁: 线程.RLock = 线程.RLock()
        自身.卡片列表: list[文档卡片] = []
        自身.完成列表: list[文档卡片] = []
        自身.日志列表: list[dict] = []
        自身.选中编号: str = ""
        自身._获取队列: list[str] = []
        自身._工作线程: 线程.Thread | None = None
        自身._取消标记: 线程.Event = 线程.Event()

    def 记录日志(自身, 级别: str, 消息: str) -> None:
        r"""
        记录日志
        :param: level: 日志级别
        :param: msg: 日志消息
        """
        with 自身.锁:
            自身.日志列表.append({"time": _短时间(), "level": 级别, "msg": 消息})
            if len(自身.日志列表) > 500:
                自身.日志列表 = 自身.日志列表[-300:]

    def 快照(自身) -> dict:
        r"""
        获取当前状态快照
        :return: dict: 状态数据
        """
        with 自身.锁:
            选中Markdown: str = ""
            for 客户端 in 自身.卡片列表:
                if 客户端.编号 == 自身.选中编号 and 客户端.Markdown文本:
                    选中Markdown = 客户端.Markdown文本
                    break
            return {
                "cards": [客户端.转字典() for 客户端 in 自身.卡片列表],
                "completed": [客户端.转字典() for 客户端 in 自身.完成列表],
                "logs": list(自身.日志列表),
                "selected_id": 自身.选中编号,
                "selected_markdown": 选中Markdown,
            }

    def _查找(自身, 卡片编号: str) -> 文档卡片 | None:
        r"""
        按 ID 查找卡片
        :param: card_id: 卡片 ID
        :return: MdCard | None: 找到的卡片或 None
        """
        for 客户端 in 自身.卡片列表:
            if 客户端.编号 == 卡片编号:
                return 客户端
        return None


状态: _文档状态 = _文档状态()


def _设置字典() -> dict[str, str]:
    r"""
    获取 MdOut 相关设置字典
    :return: dict[str, str]: 设置键值对
    """
    return {
        "include_cover": 工具.取设置("mdout", "include_cover"),
        "include_tags": 工具.取设置("mdout", "include_tags"),
        "include_stats": 工具.取设置("mdout", "include_stats"),
        "favorite_detail": 工具.取设置("mdout", "favorite_detail"),
        "favorite_complete": 工具.取设置("mdout", "favorite_complete") or "true",
    }


def _执行获取视频(卡片: 文档卡片) -> None:
    r"""
    获取视频信息并生成 Markdown
    :param: 卡片: Markdown 卡片
    """
    配置: dict[str, str] = _设置字典()
    信息: dict = _获取视频(BV号=卡片.编号值) if 卡片.编号类型 == "bvid" else _获取视频(AV号=卡片.编号值)
    卡片.标题 = 信息.get("title", "未知视频")
    作者信息: dict = 信息.get("owner", {})
    卡片.副标题 = f"{作者信息.get('name', '—')} · {_格式化时长(信息.get('duration', 0))}"
    _延迟()
    标签: list = []
    if 配置.get("include_tags") == "true":
        BV号: str = 信息.get("bvid", 卡片.编号值 if 卡片.编号类型 == "bvid" else "")
        AV号: str = str(信息.get("aid", 卡片.编号值 if 卡片.编号类型 == "avid" else ""))
        标签 = _获取视频标签(BV号=BV号, AV号=AV号)
        if not isinstance(标签, list):
            标签 = []
    卡片.Markdown文本 = _视频Markdown(信息, 标签, 配置)


def _执行获取用户(卡片: 文档卡片) -> None:
    r"""
    获取用户信息并生成 Markdown
    :param: card: Markdown 卡片
    """
    配置: dict[str, str] = _设置字典()
    卡片数据: dict = _获取用户卡片(卡片.编号值)
    用户卡片: dict = 卡片数据.get("card", {})
    卡片.标题 = 用户卡片.get("name", "未知用户")
    卡片.副标题 = f"UID {卡片.编号值} · 粉丝 {_格式化数字(卡片数据.get('follower', 0))}"
    _延迟()
    用户统计: dict = _获取用户统计(卡片.编号值)
    _延迟()
    收藏夹列表: list = _获取收藏夹列表(卡片.编号值)
    收藏内容: dict[int, dict] = {}
    完整导出: bool = 配置.get("favorite_complete", "true") == "true"
    要内容: bool = 完整导出 or 配置.get("favorite_detail") == "full"
    if 要内容 and 收藏夹列表:
        夹们: list = 收藏夹列表 if 完整导出 else 收藏夹列表[:20]
        for 序号, 收藏夹 in enumerate(夹们):
            if 状态._取消标记.is_set():
                break
            _延迟()
            收藏夹编号值: int = 收藏夹.get("id", 0)
            if not 收藏夹编号值:
                continue
            收藏夹内容: dict = 拉取收藏夹内容(
                收藏夹编号值,
                完整=完整导出,
                取消事件=状态._取消标记,
            )
            if 收藏夹内容:
                收藏内容[收藏夹编号值] = 收藏夹内容
            状态.记录日志(
                "info",
                f"获取收藏夹 ({序号 + 1}/{len(夹们)}): {收藏夹.get('title', '')}",
            )
    卡片.Markdown文本 = _用户Markdown(卡片数据, 用户统计, 收藏夹列表, 收藏内容, 配置)


def _执行获取专栏(卡片: 文档卡片) -> None:
    r"""
    获取专栏信息并生成 Markdown
    :param: card: Markdown 卡片
    :raise: RuntimeError: 无法获取专栏信息
    """
    配置: dict[str, str] = _设置字典()
    if 卡片.编号类型 == "rlid":
        文集数据: dict = _获取专栏文集(卡片.编号值)
        概览: dict = 文集数据.get("list", {}) if isinstance(文集数据.get("list"), dict) else {}
        文章列表: list = 文集数据.get("articles", []) or []
        if not 文章列表:
            raise RuntimeError("文集为空、不可见或不存在")
        位数: int = max(2, len(str(len(文章列表))))
        批量文档: list[dict[str, str]] = []
        for 序号, 文章摘要 in enumerate(文章列表, 1):
            if 状态._取消标记.is_set():
                break
            if not isinstance(文章摘要, dict) or not 文章摘要.get("id"):
                continue
            if 序号 > 1:
                _延迟()
            专栏号: str = str(文章摘要["id"])
            动态号: str = str(文章摘要.get("dyn_id_str") or "")
            if 动态号:
                try:
                    信息: dict = {
                        "id": int(专栏号),
                        "_opus_detail": _获取动态专栏(动态号),
                    }
                except Exception:
                    信息 = _获取专栏(专栏号) or 文章摘要
            else:
                信息 = _获取专栏(专栏号) or 文章摘要
            动态详情: dict = (
                信息.get("_opus_detail", {})
                if isinstance(信息.get("_opus_detail"), dict)
                else {}
            )
            标题: str = str(
                信息.get("title")
                or (_动态标题(动态详情) if 动态详情 else "")
                or 文章摘要.get("title")
                or f"专栏 cv{专栏号}"
            )
            文件名: str = f"{序号:0{位数}d}-{_清理文件名(标题)}.md"
            批量文档.append(
                {
                    "title": 标题,
                    "cvid": 专栏号,
                    "filename": 文件名,
                    "markdown": _专栏Markdown(信息, 配置),
                }
            )
            状态.记录日志("info", f"获取文集文章 ({序号}/{len(文章列表)}): {标题}")
        if not 批量文档:
            raise RuntimeError("文集文章均未能获取")
        卡片.标题 = str(概览.get("name") or f"专栏文集 rl{卡片.编号值}")
        卡片.副标题 = f"rl{卡片.编号值} · {len(批量文档)} 篇"
        卡片.批量文档列表 = 批量文档
        卡片.Markdown文本 = _文集索引Markdown(文集数据, 批量文档, 配置)
        return
    if 卡片.编号类型 == "opusid":
        详情: dict = _获取动态专栏(卡片.编号值)
        卡片.标题 = _动态标题(详情) or "未知动态"
        卡片.副标题 = f"opus{卡片.编号值}"
        卡片.Markdown文本 = _动态Markdown(详情, 配置)
        return
    信息: dict = _获取专栏(卡片.编号值)
    if not 信息:
        raise RuntimeError("无法获取专栏信息")
    动态详情: dict = (
        信息.get("_opus_detail", {}) if isinstance(信息.get("_opus_detail"), dict) else {}
    )
    卡片.标题 = 信息.get("title") or (_动态标题(动态详情) if 动态详情 else "") or "未知专栏"
    卡片.副标题 = f"cv{卡片.编号值}"
    卡片.Markdown文本 = _专栏Markdown(信息, 配置)


def _工作线程函数() -> None:
    r"""
    后台 worker 线程函数, 逐个处理获取队列
    """
    while True:
        with 状态.锁:
            if not 状态._获取队列 or 状态._取消标记.is_set():
                状态._工作线程 = None
                return
            卡片编号: str = 状态._获取队列.pop(0)
            卡片: 文档卡片 | None = 状态._查找(卡片编号)
            if not 卡片 or 卡片.状态名 != "pending":
                continue
            卡片.状态名 = "fetching"

        状态.记录日志("info", f"获取中: {卡片.输入文本}")
        try:
            match 卡片.项目类型:
                case "video":
                    _执行获取视频(卡片)
                case "user":
                    _执行获取用户(卡片)
                case "article":
                    _执行获取专栏(卡片)
                case _:
                    raise RuntimeError("无法识别的类型")
            with 状态.锁:
                卡片.状态名 = "ready"
            状态.记录日志("success", f"获取完成: {卡片.标题}")
        except Exception as e:
            with 状态.锁:
                卡片.状态名 = "failed"
                卡片.错误 = str(e)
            状态.记录日志("error", f"获取失败: {卡片.输入文本} — {e}")
        _延迟()


def _确保工作线程() -> None:
    r"""
    确保后台 worker 线程正在运行
    """
    with 状态.锁:
        if 状态._工作线程 is None or not 状态._工作线程.is_alive():
            状态._取消标记.clear()
            标签项: 线程.Thread = 线程.Thread(target=_工作线程函数, daemon=True)
            状态._工作线程 = 标签项
            标签项.start()


def 取状态() -> dict:
    r"""
    获取当前状态快照
    :return: dict: 状态数据
    """
    return 状态.快照()


def 执行解析(文本: str) -> dict[str, str]:
    r"""
    解析用户输入文本
    :param: text: 输入文本
    :return: dict[str, str]: 解析结果
    """
    return 解析输入(文本)


def _添加单项(输入文本: str, 期望类型: str | None = None) -> dict:
    r"""解析并入队单条输入。"""
    解析结果: dict[str, str] = 解析输入(输入文本)
    if 解析结果["type"] == "unknown":
        return {"ok": False, "error": f"无法识别: {输入文本}"}
    if 期望类型 and 解析结果["type"] != 期望类型:
        return {"ok": False, "error": "类型不符"}
    卡片: 文档卡片 = 文档卡片(
        输入文本=输入文本,
        项目类型=解析结果["type"],
        编号类型=解析结果["id_type"],
        编号值=解析结果["id_value"],
        标题=f"[{_类型标签表.get(解析结果['type'], '?')}] {解析结果['id_value']}",
        副标题="等待获取...",
        状态名="pending",
    )
    with 状态.锁:
        状态.卡片列表.append(卡片)
        状态._获取队列.append(卡片.编号)
    状态.记录日志("info", f"已添加: {输入文本} → {_类型标签表.get(解析结果['type'], '?')}")
    _确保工作线程()
    return {"ok": True, "card_id": 卡片.编号}


def 添加并获取(输入文本: str, 期望类型: str | None = None) -> dict:
    r"""
    添加获取任务并启动异步获取。支持混排批量粘贴。
    :param: input_text: 用户输入文本
    :param: 期望类型: 面板类型 video/user/article, 不符则跳过
    :return: dict: 添加结果
    """
    from mybiout.pages.batch_input import 解析批量输入

    项们: list[str] = 解析批量输入(输入文本)
    if not 项们 and 输入文本.strip():
        项们 = [输入文本.strip()]
    if not 项们:
        return {"ok": False, "error": "无法识别: 空输入"}
    if len(项们) == 1:
        return _添加单项(项们[0], 期望类型)

    成功: int = 0
    错类: int = 0
    不识: int = 0
    首个编号: str = ""
    for 项 in 项们:
        结果: dict = _添加单项(项, 期望类型)
        if 结果.get("ok"):
            成功 += 1
            if not 首个编号:
                首个编号 = str(结果.get("card_id") or "")
        elif 结果.get("error") == "类型不符":
            错类 += 1
        else:
            不识 += 1
    if 成功 == 0:
        return {
            "ok": False,
            "error": f"没有可添加的项（类型不符 {错类}，无法识别 {不识}）",
            "added": 0,
            "wrong_type": 错类,
            "unknown": 不识,
        }
    return {
        "ok": True,
        "added": 成功,
        "wrong_type": 错类,
        "unknown": 不识,
        "card_id": 首个编号,
    }


def 选择卡片(卡片编号: str) -> None:
    r"""
    选中卡片以预览
    :param: card_id: 卡片 ID
    """
    with 状态.锁:
        状态.选中编号 = 卡片编号


def _导出文集卡片(卡片: 文档卡片, 输出目录: 路径) -> 路径:
    r"""把文集目录页与逐篇 Markdown 写入同名文件夹。"""
    基础名称: str = _清理文件名(卡片.标题 or f"文集-rl{卡片.编号值}")
    目标目录: 路径 = 输出目录 / 基础名称
    序号: int = 1
    while 目标目录.exists():
        目标目录 = 输出目录 / f"{基础名称}_{序号}"
        序号 += 1
    目标目录.mkdir(parents=False, exist_ok=False)
    try:
        (目标目录 / "00-文集索引.md").write_text(卡片.Markdown文本, encoding="utf-8")
        for 文档 in 卡片.批量文档列表:
            文件名: str = 路径(str(文档.get("filename") or "untitled.md")).name
            if not 文件名.lower().endswith(".md"):
                文件名 += ".md"
            (目标目录 / 文件名).write_text(str(文档.get("markdown") or ""), encoding="utf-8")
        return 目标目录
    except Exception:
        with 忽略异常(OSError):
            文件工具.rmtree(目标目录)
        raise


def 导出卡片(卡片编号列表: list[str]) -> dict:
    r"""
    导出指定卡片为 Markdown 文件
    :param: card_ids: 卡片 ID 列表
    :return: dict: 导出结果
    """
    输出目录: 路径 = 工具.取导出路径() / 工具.取设置("mdout", "folder")
    输出目录.mkdir(parents=True, exist_ok=True)

    导出数量: int = 0
    导出文件数量: int = 0
    with 状态.锁:
        目标列表: list[文档卡片] = [客户端 for 客户端 in 状态.卡片列表 if 客户端.编号 in 卡片编号列表 and 客户端.状态名 == "ready"]

    for 卡片 in 目标列表:
        if not 卡片.Markdown文本:
            continue
        if 卡片.批量文档列表:
            try:
                文集目录: 路径 = _导出文集卡片(卡片, 输出目录)
                with 状态.锁:
                    卡片.状态名 = "success"
                    卡片.文件名 = 文集目录.name
                    卡片.输出路径 = str(文集目录)
                    状态.卡片列表 = [
                        客户端 for 客户端 in 状态.卡片列表 if 客户端.编号 != 卡片.编号
                    ]
                    状态.完成列表.append(卡片)
                导出数量 += 1
                导出文件数量 += len(卡片.批量文档列表) + 1
                状态.记录日志(
                    "success",
                    f"已批量导出文集: {文集目录.name}（{len(卡片.批量文档列表)} 篇）",
                )
            except Exception as e:
                with 状态.锁:
                    卡片.状态名 = "failed"
                    卡片.错误 = str(e)
                状态.记录日志("error", f"文集导出失败: {卡片.标题} — {e}")
            continue
        文件名文本: str = _清理文件名(卡片.标题 or "untitled") + ".md"
        输出文件: 路径 = 输出目录 / 文件名文本
        计数器: int = 1
        while 输出文件.exists():
            输出文件 = 输出目录 / f"{_清理文件名(卡片.标题 or 'untitled')}_{计数器}.md"
            计数器 += 1
        try:
            输出文件.write_text(卡片.Markdown文本, encoding="utf-8")
            with 状态.锁:
                卡片.状态名 = "success"
                卡片.文件名 = 输出文件.name
                卡片.输出路径 = str(输出文件)
                状态.卡片列表 = [客户端 for 客户端 in 状态.卡片列表 if 客户端.编号 != 卡片.编号]
                状态.完成列表.append(卡片)
            导出数量 += 1
            导出文件数量 += 1
            状态.记录日志("success", f"已导出: {输出文件.name}")
        except Exception as e:
            with 状态.锁:
                卡片.状态名 = "failed"
                卡片.错误 = str(e)
            状态.记录日志("error", f"导出失败: {卡片.标题} — {e}")

    return {"ok": True, "exported": 导出数量, "files": 导出文件数量}


def 导出全部就绪() -> dict:
    r"""
    导出全部就绪的卡片
    :return: dict: 导出结果
    """
    with 状态.锁:
        编号集合: list[str] = [客户端.编号 for 客户端 in 状态.卡片列表 if 客户端.状态名 == "ready"]
    if not 编号集合:
        return {"ok": False, "error": "没有可导出的项目"}
    return 导出卡片(编号集合)


def 移除卡片(卡片编号列表: list[str]) -> None:
    r"""
    移除指定卡片
    :param: card_ids: 卡片 ID 列表
    """
    编号集合: set[str] = set(卡片编号列表)
    with 状态.锁:
        状态.卡片列表 = [客户端 for 客户端 in 状态.卡片列表 if 客户端.编号 not in 编号集合]
        状态._获取队列 = [队列编号 for 队列编号 in 状态._获取队列 if 队列编号 not in 编号集合]


def 清空卡片() -> None:
    r"""
    清空全部卡片和获取队列
    """
    with 状态.锁:
        状态.卡片列表.clear()
        状态._获取队列.clear()
        状态.选中编号 = ""
    状态.记录日志("info", "已清空获取列表")


def 清空完成() -> None:
    r"""
    清空已完成列表
    """
    with 状态.锁:
        状态.完成列表.clear()
    状态.记录日志("info", "已清空完成列表")


def 取导出文件夹路径() -> str:
    r"""
    获取 MdOut 导出目录的完整路径
    :return: str: 目录路径
    """
    输出目录: 路径 = 工具.取导出路径() / 工具.取设置("mdout", "folder")
    输出目录.mkdir(parents=True, exist_ok=True)
    return str(输出目录)
