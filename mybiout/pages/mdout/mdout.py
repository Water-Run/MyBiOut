r"""
MdOut! Markdown 导出服务层, 负责从 B 站 API 获取信息并生成 Markdown 文档

:file: mybiout/pages/mdout/mdout.py
:author: WaterRun
:time: 2026-04-06
"""

import re as 正则
import threading as 线程
import time as 时间
import uuid as 唯一编号
from dataclasses import dataclass as 数据类
from dataclasses import field as 字段
from datetime import datetime as 日期时间
from pathlib import Path as 路径

import httpx as 网络请求

from mybiout.pages import utils as 工具

_BILI_HEADERS: dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.bilibili.com",
    "Origin": "https://www.bilibili.com",
}

_URL_PATTERNS: list[tuple[正则.Pattern[str], str, str]] = [
    (正则.compile(r"(?:https?://)?(?:www\.)?bilibili\.com/video/(BV[\w]{10,})", 正则.I), "video", "bvid"),
    (正则.compile(r"^(BV[\w]{10,})$", 正则.I), "video", "bvid"),
    (正则.compile(r"(?:https?://)?(?:www\.)?bilibili\.com/video/av(\d+)", 正则.I), "video", "avid"),
    (正则.compile(r"^av(\d+)$", 正则.I), "video", "avid"),
    (正则.compile(r"(?:https?://)?(?:www\.)?bilibili\.com/read/cv(\d+)", 正则.I), "article", "cvid"),
    (正则.compile(r"^cv(\d+)$", 正则.I), "article", "cvid"),
    (正则.compile(r"(?:https?://)?space\.bilibili\.com/(\d+)", 正则.I), "user", "mid"),
]

_TYPE_LABELS: dict[str, str] = {"video": "视频", "user": "用户", "article": "专栏", "unknown": "未知"}


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


def _清理文件名(name: str) -> str:
    r"""
    清理文件名中的非法字符
    :param: name: 原始名称
    :return: str: 安全的文件名
    """
    name = 正则.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(". ")
    return name[:200] if name else "untitled"


def _格式化数字(n: int | None) -> str:
    r"""
    格式化数字为可读字符串
    :param: n: 数字
    :return: str: 格式化后的字符串
    """
    if n is None:
        return "0"
    if n >= 100_000_000:
        return f"{n / 100_000_000:.1f}亿"
    if n >= 10_000:
        return f"{n / 10_000:.1f}万"
    return str(n)


def _格式化时长(seconds: int) -> str:
    r"""
    格式化秒数为时长字符串
    :param: seconds: 秒数
    :return: str: 格式化时长
    """
    h, m, s = seconds // 3600, (seconds % 3600) // 60, seconds % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _格式化时间戳(ts: int) -> str:
    r"""
    格式化 Unix 时间戳为日期字符串
    :param: ts: Unix 时间戳
    :return: str: 格式化日期
    """
    if not ts:
        return ""
    try:
        return 日期时间.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return ""


def _客户端() -> 网络请求.Client:
    r"""
    创建带认证的 HTTP 客户端
    :return: httpx.Client: HTTP 客户端
    """
    sessdata: str = 工具.取会话数据().strip()
    cookies: dict[str, str] = {"SESSDATA": sessdata} if sessdata else {}
    return 网络请求.Client(headers=_BILI_HEADERS, cookies=cookies, timeout=20.0, follow_redirects=True)


def _延迟() -> None:
    r"""
    根据设置执行请求间隔延迟
    """
    try:
        d: float = float(工具.取设置("mdout", "request_delay") or "0.5")
    except ValueError:
        d = 0.5
    时间.sleep(max(0.1, d))


def 解析输入(text: str) -> dict[str, str]:
    r"""
    解析用户输入, 识别类型和 ID
    :param: text: 用户输入文本
    :return: dict[str, str]: 解析结果
    """
    text = text.strip()
    if not text:
        return {"type": "unknown", "id_type": "", "id_value": "", "label": ""}

    if b23 := 正则.match(r"(?:https?://)?b23\.tv/([\w]+)", text, 正则.I):
        try:
            with _客户端() as c:
                r: 网络请求.Response = c.head(f"https://b23.tv/{b23.group(1)}")
                return 解析输入(str(r.headers.get("location", r.url)))
        except Exception:
            return {"type": "unknown", "id_type": "", "id_value": text, "label": "短链解析失败"}

    for pattern, item_type, id_type in _URL_PATTERNS:
        if m := pattern.search(text):
            return {"type": item_type, "id_type": id_type, "id_value": m.group(1), "label": _TYPE_LABELS[item_type]}

    if 正则.match(r"^\d{1,15}$", text):
        return {"type": "user", "id_type": "mid", "id_value": text, "label": "用户"}

    return {"type": "unknown", "id_type": "", "id_value": text, "label": "无法识别"}


def _接口读取(path: str, params: dict) -> dict:
    r"""
    调用 B 站 API 并返回 data 字段
    :param: path: API 路径
    :param: params: 查询参数
    :return: dict: API 返回的 data 字段
    :raise: RuntimeError: API 返回非零 code
    """
    with _客户端() as c:
        r: 网络请求.Response = c.get(f"https://api.bilibili.com{path}", params=params)
        data: dict = r.json()
    if data.get("code") != 0:
        raise RuntimeError(data.get("message", "API 未知错误"))
    return data.get("data", {})


def _安全接口读取(path: str, params: dict) -> dict:
    r"""
    安全调用 B 站 API, 异常时返回空字典
    :param: path: API 路径
    :param: params: 查询参数
    :return: dict: API 返回的 data 字段或空字典
    """
    try:
        return _接口读取(path, params)
    except Exception:
        return {}


def _获取视频(bvid: str = "", avid: str = "") -> dict:
    r"""
    获取视频详细信息
    :param: bvid: BV 号
    :param: avid: av 号
    :return: dict: 视频信息
    """
    params: dict[str, str] = {}
    if bvid:
        params["bvid"] = bvid
    elif avid:
        params["aid"] = avid
    return _接口读取("/x/web-interface/view", params)


def _获取视频标签(bvid: str = "", avid: str = "") -> list:
    r"""
    获取视频标签列表
    :param: bvid: BV 号
    :param: avid: av 号
    :return: list: 标签列表
    """
    params: dict[str, str] = {}
    if bvid:
        params["bvid"] = bvid
    elif avid:
        params["aid"] = avid
    return _安全接口读取("/x/tag/archive/tags", params) or []


def _获取用户卡片(mid: str) -> dict:
    r"""
    获取用户卡片信息
    :param: mid: 用户 UID
    :return: dict: 用户卡片数据
    """
    return _接口读取("/x/web-interface/card", {"mid": mid, "photo": "true"})


def _获取用户统计(mid: str) -> dict:
    r"""
    获取 UP 主统计信息
    :param: mid: 用户 UID
    :return: dict: 统计数据
    """
    return _安全接口读取("/x/space/upstat", {"mid": mid})


def _获取收藏夹列表(mid: str) -> list:
    r"""
    获取用户收藏夹列表
    :param: mid: 用户 UID
    :return: list: 收藏夹列表
    """
    data: dict = _安全接口读取("/x/v3/fav/folder/created/list-all", {"up_mid": mid})
    return data.get("list", []) or [] if isinstance(data, dict) else []


def _获取收藏内容(media_id: int, pn: int = 1, ps: int = 20) -> dict:
    r"""
    获取收藏夹内容
    :param: media_id: 收藏夹 ID
    :param: pn: 页码
    :param: ps: 每页数量
    :return: dict: 收藏夹内容
    """
    return _安全接口读取("/x/v3/fav/resource/list", {"media_id": media_id, "pn": pn, "ps": ps})


def _获取专栏(cvid: str) -> dict:
    r"""
    获取专栏文章信息
    :param: cvid: 专栏 cv 号
    :return: dict: 专栏信息
    """
    return _安全接口读取("/x/article/viewinfo", {"id": cvid})


def _视频Markdown(info: dict, tags: list, cfg: dict) -> str:
    r"""
    生成视频信息 Markdown 文档
    :param: info: 视频信息字典
    :param: tags: 标签列表
    :param: cfg: 导出配置
    :return: str: Markdown 文本
    """
    title: str = info.get("title", "未知标题")
    bvid: str = info.get("bvid", "")
    avid: str = info.get("aid", "")
    desc: str = info.get("desc", "")
    owner: dict = info.get("owner", {})
    stat: dict = info.get("stat", {})
    pages: list = info.get("pages", [])
    pic: str = info.get("pic", "")

    lines: list[str] = [
        f"# {title}\n",
        f"> {bvid} | av{avid}",
        f"> 导出时间: {_完整时间()}\n",
    ]

    if cfg.get("include_cover") == "true" and pic:
        lines.append(f"![封面]({pic})\n")

    lines.extend(
        [
            "## 基本信息\n",
            "| 项目 | 内容 |",
            "|------|------|",
            f"| UP主 | [{owner.get('name', '—')}](https://space.bilibili.com/{owner.get('mid', '')}) |",
            f"| 发布时间 | {_格式化时间戳(info.get('pubdate', 0))} |",
            f"| 分区 | {info.get('tname', '')} |",
            f"| 时长 | {_格式化时长(info.get('duration', 0))} |",
            f"| 链接 | https://www.bilibili.com/video/{bvid} |",
            "",
        ]
    )

    if cfg.get("include_stats") == "true":
        lines.extend(["## 数据统计\n", "| 指标 | 数值 |", "|------|------|"])
        for k, label in [
            ("view", "播放"),
            ("danmaku", "弹幕"),
            ("reply", "评论"),
            ("like", "点赞"),
            ("coin", "投币"),
            ("favorite", "收藏"),
            ("share", "转发"),
        ]:
            lines.append(f"| {label} | {_格式化数字(stat.get(k, 0))} |")
        lines.append("")

    if desc:
        lines.extend(["## 简介\n", desc + "\n"])

    if cfg.get("include_tags") == "true" and isinstance(tags, list):
        tag_strs: list[str] = [f"`{t.get('tag_name', '')}`" for t in tags if t.get("tag_name")]
        if tag_strs:
            lines.extend(["## 标签\n", " ".join(tag_strs) + "\n"])

    if len(pages) > 1:
        lines.extend(["## 分P列表\n", "| P | 标题 | 时长 |", "|---|------|------|"])
        lines.extend(
            f"| P{p.get('page', '')} | {p.get('part', '')} | {_格式化时长(p.get('duration', 0))} |" for p in pages
        )
        lines.append("")

    lines.extend(["---", f"*由 MyBiOut! MdOut 导出于 {_完整时间()}*"])
    return "\n".join(lines)


def _用户Markdown(card_data: dict, upstat: dict, favorites: list, fav_contents: dict, cfg: dict) -> str:
    r"""
    生成用户信息 Markdown 文档
    :param: card_data: 用户卡片数据
    :param: upstat: UP 主统计数据
    :param: favorites: 收藏夹列表
    :param: fav_contents: 收藏夹内容映射
    :param: cfg: 导出配置
    :return: str: Markdown 文本
    """
    card: dict = card_data.get("card", {})
    name: str = card.get("name", "未知用户")
    mid: str = card.get("mid", "")
    sign: str = card.get("sign", "")
    level: int = card.get("level_info", {}).get("current_level", 0)
    face: str = card.get("face", "")
    sex: str = card.get("sex", "")
    fans: int = card_data.get("follower", 0) or card.get("fans", 0)
    friend: int = card.get("attention", 0) or card.get("friend", 0)
    archive_count: int = card_data.get("archive_count", 0)
    like_num: int = card_data.get("like_num", 0)
    official_title: str = (card.get("Official") or {}).get("title", "")

    lines: list[str] = [
        f"# {name}\n",
        f"> UID: {mid}",
        f"> 导出时间: {_完整时间()}\n",
    ]

    if cfg.get("include_cover") == "true" and face:
        lines.append(f"![头像]({face})\n")

    lines.extend(["## 基本信息\n", "| 项目 | 内容 |", "|------|------|", f"| 昵称 | {name} |", f"| UID | {mid} |"])
    if sex and sex != "保密":
        lines.append(f"| 性别 | {sex} |")
    lines.append(f"| 等级 | Lv.{level} |")
    if official_title:
        lines.append(f"| 认证 | {official_title} |")
    if sign:
        lines.append(f"| 签名 | {sign} |")
    lines.extend([f"| 空间链接 | https://space.bilibili.com/{mid} |", ""])

    if cfg.get("include_stats") == "true":
        lines.extend(["## 数据统计\n", "| 指标 | 数值 |", "|------|------|"])
        lines.extend(
            [
                f"| 粉丝 | {_格式化数字(fans)} |",
                f"| 关注 | {_格式化数字(friend)} |",
                f"| 投稿视频 | {archive_count} |",
            ]
        )
        if like_num:
            lines.append(f"| 获赞 | {_格式化数字(like_num)} |")
        if upstat:
            if av := upstat.get("archive", {}).get("view", 0):
                lines.append(f"| 视频总播放 | {_格式化数字(av)} |")
            if arv := upstat.get("article", {}).get("view", 0):
                lines.append(f"| 文章总阅读 | {_格式化数字(arv)} |")
        lines.append("")

    if favorites:
        lines.append("## 收藏夹\n")
        detail: str = cfg.get("favorite_detail", "basic")
        for fav in favorites:
            fav_id: int = fav.get("id", 0)
            lines.extend([f"### {fav.get('title', '未命名')}\n", f"共 {fav.get('media_count', 0)} 个内容\n"])
            if detail == "full" and fav_id in fav_contents:
                medias: list = fav_contents[fav_id].get("medias") or []
                if medias:
                    lines.extend(["| # | 标题 | UP主 | BV号 |", "|---|------|------|------|"])
                    lines.extend(
                        f"| {idx} | {(m.get('title') or '—').replace('|', '\\|')} "
                        f"| {(m.get('upper', {}).get('name') or '—').replace('|', '\\|')} "
                        f"| {m.get('bvid') or '—'} |"
                        for idx, m in enumerate(medias, 1)
                    )
                    total: int = fav_contents[fav_id].get("info", {}).get("media_count", fav.get("media_count", 0))
                    if len(medias) < total:
                        lines.append(f"\n*（仅显示前 {len(medias)} 项，共 {total} 项）*")
                    lines.append("")

    lines.extend(["---", f"*由 MyBiOut! MdOut 导出于 {_完整时间()}*"])
    return "\n".join(lines)


def _专栏Markdown(info: dict, cfg: dict) -> str:
    r"""
    生成专栏文章 Markdown 文档
    :param: info: 专栏信息字典
    :param: cfg: 导出配置
    :return: str: Markdown 文本
    """
    title: str = info.get("title", "未知专栏")
    stats: dict = info.get("stats", {})
    banner: str = info.get("banner_url", "")

    lines: list[str] = [
        f"# {title}\n",
        f"> 专栏 cv{info.get('id', '')}",
        f"> 导出时间: {_完整时间()}\n",
    ]

    if cfg.get("include_cover") == "true" and banner:
        lines.append(f"![头图]({banner})\n")

    lines.extend(["## 基本信息\n", "| 项目 | 内容 |", "|------|------|"])
    if author := info.get("author_name", "") or str(info.get("mid", "")):
        lines.append(f"| 作者 | {author} |")
    if publish := info.get("publish_time", 0):
        lines.append(f"| 发布时间 | {_格式化时间戳(publish)} |")
    if info.get("mid"):
        lines.append(f"| 链接 | https://www.bilibili.com/read/cv{info.get('id', '')} |")
    lines.append("")

    if cfg.get("include_stats") == "true" and stats:
        lines.extend(["## 数据统计\n", "| 指标 | 数值 |", "|------|------|"])
        for k, label in [
            ("view", "阅读"),
            ("like", "点赞"),
            ("reply", "评论"),
            ("favorite", "收藏"),
            ("coin", "投币"),
            ("share", "转发"),
        ]:
            lines.append(f"| {label} | {_格式化数字(stats.get(k, 0))} |")
        lines.append("")

    lines.extend(["---", f"*由 MyBiOut! MdOut 导出于 {_完整时间()}*"])
    return "\n".join(lines)


@数据类(slots=True)
class 文档卡片:
    r"""
    Markdown 导出卡片数据模型
    """

    id: str = 字段(default_factory=_生成编号)
    input_text: str = ""
    item_type: str = "unknown"
    id_type: str = ""
    id_value: str = ""
    title: str = ""
    subtitle: str = ""
    markdown: str = ""
    status: str = "pending"
    error: str = ""
    filename: str = ""
    output_path: str = ""

    def to_dict(self) -> dict:
        r"""
        转换为前端可用的字典
        :return: dict: 卡片字典
        """
        return {
            "id": self.id,
            "input_text": self.input_text,
            "item_type": self.item_type,
            "id_value": self.id_value,
            "title": self.title,
            "subtitle": self.subtitle,
            "has_markdown": bool(self.markdown),
            "status": self.status,
            "error": self.error,
            "filename": self.filename,
            "output_path": self.output_path,
        }


class _文档状态:
    r"""
    MdOut 全局运行状态管理
    """

    def __init__(self) -> None:
        r"""
        初始化全局状态
        """
        self.lock: 线程.RLock = 线程.RLock()
        self.cards: list[文档卡片] = []
        self.completed: list[文档卡片] = []
        self.logs: list[dict] = []
        self.selected_id: str = ""
        self._fetch_queue: list[str] = []
        self._worker: 线程.Thread | None = None
        self._cancel: 线程.Event = 线程.Event()

    def log(self, level: str, msg: str) -> None:
        r"""
        记录日志
        :param: level: 日志级别
        :param: msg: 日志消息
        """
        with self.lock:
            self.logs.append({"time": _短时间(), "level": level, "msg": msg})
            if len(self.logs) > 500:
                self.logs = self.logs[-300:]

    def snapshot(self) -> dict:
        r"""
        获取当前状态快照
        :return: dict: 状态数据
        """
        with self.lock:
            sel_md: str = ""
            for c in self.cards:
                if c.id == self.selected_id and c.markdown:
                    sel_md = c.markdown
                    break
            return {
                "cards": [c.to_dict() for c in self.cards],
                "completed": [c.to_dict() for c in self.completed],
                "logs": list(self.logs),
                "selected_id": self.selected_id,
                "selected_markdown": sel_md,
            }

    def _find(self, card_id: str) -> 文档卡片 | None:
        r"""
        按 ID 查找卡片
        :param: card_id: 卡片 ID
        :return: MdCard | None: 找到的卡片或 None
        """
        for c in self.cards:
            if c.id == card_id:
                return c
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
    }


def _执行获取视频(card: 文档卡片) -> None:
    r"""
    获取视频信息并生成 Markdown
    :param: card: Markdown 卡片
    """
    cfg: dict[str, str] = _设置字典()
    info: dict = _获取视频(bvid=card.id_value) if card.id_type == "bvid" else _获取视频(avid=card.id_value)
    card.title = info.get("title", "未知视频")
    owner: dict = info.get("owner", {})
    card.subtitle = f"{owner.get('name', '—')} · {_格式化时长(info.get('duration', 0))}"
    _延迟()
    tags: list = []
    if cfg.get("include_tags") == "true":
        bvid: str = info.get("bvid", card.id_value if card.id_type == "bvid" else "")
        avid: str = str(info.get("aid", card.id_value if card.id_type == "avid" else ""))
        tags = _获取视频标签(bvid=bvid, avid=avid)
        if not isinstance(tags, list):
            tags = []
    card.markdown = _视频Markdown(info, tags, cfg)


def _执行获取用户(card: 文档卡片) -> None:
    r"""
    获取用户信息并生成 Markdown
    :param: card: Markdown 卡片
    """
    cfg: dict[str, str] = _设置字典()
    card_data: dict = _获取用户卡片(card.id_value)
    crd: dict = card_data.get("card", {})
    card.title = crd.get("name", "未知用户")
    card.subtitle = f"UID {card.id_value} · 粉丝 {_格式化数字(card_data.get('follower', 0))}"
    _延迟()
    upstat: dict = _获取用户统计(card.id_value)
    _延迟()
    favorites: list = _获取收藏夹列表(card.id_value)
    fav_contents: dict[int, dict] = {}
    if cfg.get("favorite_detail") == "full" and favorites:
        max_fav: int = 20
        for i, fav in enumerate(favorites[:max_fav]):
            if 状态._cancel.is_set():
                break
            _延迟()
            if (fav_id := fav.get("id", 0)) and (fc := _获取收藏内容(fav_id, pn=1, ps=20)):
                fav_contents[fav_id] = fc
            状态.log("info", f"获取收藏夹 ({i + 1}/{min(len(favorites), max_fav)}): {fav.get('title', '')}")
    card.markdown = _用户Markdown(card_data, upstat, favorites, fav_contents, cfg)


def _执行获取专栏(card: 文档卡片) -> None:
    r"""
    获取专栏信息并生成 Markdown
    :param: card: Markdown 卡片
    :raise: RuntimeError: 无法获取专栏信息
    """
    cfg: dict[str, str] = _设置字典()
    info: dict = _获取专栏(card.id_value)
    if not info:
        raise RuntimeError("无法获取专栏信息")
    card.title = info.get("title", "未知专栏")
    card.subtitle = f"cv{card.id_value}"
    card.markdown = _专栏Markdown(info, cfg)


def _工作线程函数() -> None:
    r"""
    后台 worker 线程函数, 逐个处理获取队列
    """
    while True:
        with 状态.lock:
            if not 状态._fetch_queue or 状态._cancel.is_set():
                状态._worker = None
                return
            card_id: str = 状态._fetch_queue.pop(0)
            card: 文档卡片 | None = 状态._find(card_id)
            if not card or card.status != "pending":
                continue
            card.status = "fetching"

        状态.log("info", f"获取中: {card.input_text}")
        try:
            match card.item_type:
                case "video":
                    _执行获取视频(card)
                case "user":
                    _执行获取用户(card)
                case "article":
                    _执行获取专栏(card)
                case _:
                    raise RuntimeError("无法识别的类型")
            with 状态.lock:
                card.status = "ready"
            状态.log("success", f"获取完成: {card.title}")
        except Exception as e:
            with 状态.lock:
                card.status = "failed"
                card.error = str(e)
            状态.log("error", f"获取失败: {card.input_text} — {e}")
        _延迟()


def _确保工作线程() -> None:
    r"""
    确保后台 worker 线程正在运行
    """
    with 状态.lock:
        if 状态._worker is None or not 状态._worker.is_alive():
            状态._cancel.clear()
            t: 线程.Thread = 线程.Thread(target=_工作线程函数, daemon=True)
            状态._worker = t
            t.start()


def 取状态() -> dict:
    r"""
    获取当前状态快照
    :return: dict: 状态数据
    """
    return 状态.snapshot()


def 执行解析(text: str) -> dict[str, str]:
    r"""
    解析用户输入文本
    :param: text: 输入文本
    :return: dict[str, str]: 解析结果
    """
    return 解析输入(text)


def 添加并获取(input_text: str) -> dict:
    r"""
    添加获取任务并启动异步获取
    :param: input_text: 用户输入文本
    :return: dict: 添加结果
    """
    parsed: dict[str, str] = 解析输入(input_text)
    if parsed["type"] == "unknown":
        return {"ok": False, "error": f"无法识别: {input_text}"}
    card: 文档卡片 = 文档卡片(
        input_text=input_text,
        item_type=parsed["type"],
        id_type=parsed["id_type"],
        id_value=parsed["id_value"],
        title=f"[{_TYPE_LABELS.get(parsed['type'], '?')}] {parsed['id_value']}",
        subtitle="等待获取...",
        status="pending",
    )
    with 状态.lock:
        状态.cards.append(card)
        状态._fetch_queue.append(card.id)
    状态.log("info", f"已添加: {input_text} → {_TYPE_LABELS.get(parsed['type'], '?')}")
    _确保工作线程()
    return {"ok": True, "card_id": card.id}


def 选择卡片(card_id: str) -> None:
    r"""
    选中卡片以预览
    :param: card_id: 卡片 ID
    """
    with 状态.lock:
        状态.selected_id = card_id


def 导出卡片(card_ids: list[str]) -> dict:
    r"""
    导出指定卡片为 Markdown 文件
    :param: card_ids: 卡片 ID 列表
    :return: dict: 导出结果
    """
    output_dir: 路径 = 工具.取导出路径() / 工具.取设置("mdout", "folder")
    output_dir.mkdir(parents=True, exist_ok=True)

    exported: int = 0
    with 状态.lock:
        targets: list[文档卡片] = [c for c in 状态.cards if c.id in card_ids and c.status == "ready"]

    for card in targets:
        if not card.markdown:
            continue
        fname: str = _清理文件名(card.title or "untitled") + ".md"
        out: 路径 = output_dir / fname
        counter: int = 1
        while out.exists():
            out = output_dir / f"{_清理文件名(card.title or 'untitled')}_{counter}.md"
            counter += 1
        try:
            out.write_text(card.markdown, encoding="utf-8")
            with 状态.lock:
                card.status = "success"
                card.filename = out.name
                card.output_path = str(out)
                状态.cards = [c for c in 状态.cards if c.id != card.id]
                状态.completed.append(card)
            exported += 1
            状态.log("success", f"已导出: {out.name}")
        except Exception as e:
            with 状态.lock:
                card.status = "failed"
                card.error = str(e)
            状态.log("error", f"导出失败: {card.title} — {e}")

    return {"ok": True, "exported": exported}


def 导出全部就绪() -> dict:
    r"""
    导出全部就绪的卡片
    :return: dict: 导出结果
    """
    with 状态.lock:
        ids: list[str] = [c.id for c in 状态.cards if c.status == "ready"]
    if not ids:
        return {"ok": False, "error": "没有可导出的项目"}
    return 导出卡片(ids)


def 移除卡片(card_ids: list[str]) -> None:
    r"""
    移除指定卡片
    :param: card_ids: 卡片 ID 列表
    """
    ids: set[str] = set(card_ids)
    with 状态.lock:
        状态.cards = [c for c in 状态.cards if c.id not in ids]
        状态._fetch_queue = [fid for fid in 状态._fetch_queue if fid not in ids]


def 清空卡片() -> None:
    r"""
    清空全部卡片和获取队列
    """
    with 状态.lock:
        状态.cards.clear()
        状态._fetch_queue.clear()
        状态.selected_id = ""
    状态.log("info", "已清空获取列表")


def 清空完成() -> None:
    r"""
    清空已完成列表
    """
    with 状态.lock:
        状态.completed.clear()
    状态.log("info", "已清空完成列表")


def 取导出文件夹路径() -> str:
    r"""
    获取 MdOut 导出目录的完整路径
    :return: str: 目录路径
    """
    output_dir: 路径 = 工具.取导出路径() / 工具.取设置("mdout", "folder")
    output_dir.mkdir(parents=True, exist_ok=True)
    return str(output_dir)


_uid = _生成编号
_ts = _短时间
_ts_full = _完整时间
_sanitize = _清理文件名
_fmt_num = _格式化数字
_fmt_dur = _格式化时长
_fmt_ts = _格式化时间戳
_client = _客户端
_delay = _延迟
parse_input = 解析输入
_api_get = _接口读取
_api_get_safe = _安全接口读取
_fetch_video = _获取视频
_fetch_video_tags = _获取视频标签
_fetch_user_card = _获取用户卡片
_fetch_user_upstat = _获取用户统计
_fetch_favorites_list = _获取收藏夹列表
_fetch_favorite_content = _获取收藏内容
_fetch_article = _获取专栏
_md_video = _视频Markdown
_md_user = _用户Markdown
_md_article = _专栏Markdown
MdCard = 文档卡片
_State = _文档状态
S = 状态
_settings_dict = _设置字典
_do_fetch_video = _执行获取视频
_do_fetch_user = _执行获取用户
_do_fetch_article = _执行获取专栏
_worker_fn = _工作线程函数
_ensure_worker = _确保工作线程
get_state = 取状态
do_parse = 执行解析
add_and_fetch = 添加并获取
select_card = 选择卡片
export_cards = 导出卡片
export_all_ready = 导出全部就绪
remove_cards = 移除卡片
clear_cards = 清空卡片
clear_completed = 清空完成
get_export_folder_path = 取导出文件夹路径
