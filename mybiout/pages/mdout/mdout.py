r"""
MdOut! Markdown 导出服务层, 负责从 B 站 API 获取信息并生成 Markdown 文档

:file: mybiout/pages/mdout/mdout.py
:author: WaterRun
:time: 2026-03-31
"""

import re
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import httpx

from mybiout.pages import utils

_BILI_HEADERS: dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.bilibili.com",
    "Origin": "https://www.bilibili.com",
}

_URL_PATTERNS: list[tuple[re.Pattern[str], str, str]] = [
    (re.compile(r"(?:https?://)?(?:www\.)?bilibili\.com/video/(BV[\w]{10,})", re.I), "video", "bvid"),
    (re.compile(r"^(BV[\w]{10,})$", re.I), "video", "bvid"),
    (re.compile(r"(?:https?://)?(?:www\.)?bilibili\.com/video/av(\d+)", re.I), "video", "avid"),
    (re.compile(r"^av(\d+)$", re.I), "video", "avid"),
    (re.compile(r"(?:https?://)?(?:www\.)?bilibili\.com/read/cv(\d+)", re.I), "article", "cvid"),
    (re.compile(r"^cv(\d+)$", re.I), "article", "cvid"),
    (re.compile(r"(?:https?://)?space\.bilibili\.com/(\d+)", re.I), "user", "mid"),
]

_TYPE_LABELS: dict[str, str] = {"video": "视频", "user": "用户", "article": "专栏", "unknown": "未知"}


def _uid() -> str:
    r"""
    生成 12 位唯一标识
    :return: str: UUID 前 12 位
    """
    return uuid.uuid4().hex[:12]


def _ts() -> str:
    r"""
    获取当前时间短格式
    :return: str: HH:MM:SS
    """
    return datetime.now().strftime("%H:%M:%S")


def _ts_full() -> str:
    r"""
    获取当前时间完整格式
    :return: str: YYYY-MM-DD HH:MM:SS
    """
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _sanitize(name: str) -> str:
    r"""
    清理文件名中的非法字符
    :param: name: 原始名称
    :return: str: 安全的文件名
    """
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(". ")
    return name[:200] if name else "untitled"


def _fmt_num(n: int | None) -> str:
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


def _fmt_dur(seconds: int) -> str:
    r"""
    格式化秒数为时长字符串
    :param: seconds: 秒数
    :return: str: 格式化时长
    """
    h, m, s = seconds // 3600, (seconds % 3600) // 60, seconds % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _fmt_ts(ts: int) -> str:
    r"""
    格式化 Unix 时间戳为日期字符串
    :param: ts: Unix 时间戳
    :return: str: 格式化日期
    """
    if not ts:
        return ""
    try:
        return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return ""


def _client() -> httpx.Client:
    r"""
    创建带认证的 HTTP 客户端
    :return: httpx.Client: HTTP 客户端
    """
    sessdata: str = utils.get_setting("mdout", "sessdata").strip()
    cookies: dict[str, str] = {"SESSDATA": sessdata} if sessdata else {}
    return httpx.Client(headers=_BILI_HEADERS, cookies=cookies, timeout=20.0, follow_redirects=True)


def _delay() -> None:
    r"""
    根据设置执行请求间隔延迟
    """
    try:
        d: float = float(utils.get_setting("mdout", "request_delay") or "0.5")
    except ValueError:
        d = 0.5
    time.sleep(max(0.1, d))


def parse_input(text: str) -> dict[str, str]:
    r"""
    解析用户输入, 识别类型和 ID
    :param: text: 用户输入文本
    :return: dict[str, str]: 解析结果
    """
    text = text.strip()
    if not text:
        return {"type": "unknown", "id_type": "", "id_value": "", "label": ""}

    if b23 := re.match(r"(?:https?://)?b23\.tv/([\w]+)", text, re.I):
        try:
            with _client() as c:
                r: httpx.Response = c.head(f"https://b23.tv/{b23.group(1)}")
                return parse_input(str(r.headers.get("location", r.url)))
        except Exception:
            return {"type": "unknown", "id_type": "", "id_value": text, "label": "短链解析失败"}

    for pattern, item_type, id_type in _URL_PATTERNS:
        if m := pattern.search(text):
            return {"type": item_type, "id_type": id_type, "id_value": m.group(1), "label": _TYPE_LABELS[item_type]}

    if re.match(r"^\d{1,15}$", text):
        return {"type": "user", "id_type": "mid", "id_value": text, "label": "用户"}

    return {"type": "unknown", "id_type": "", "id_value": text, "label": "无法识别"}


def _api_get(path: str, params: dict) -> dict:
    r"""
    调用 B 站 API 并返回 data 字段
    :param: path: API 路径
    :param: params: 查询参数
    :return: dict: API 返回的 data 字段
    :raise: RuntimeError: API 返回非零 code
    """
    with _client() as c:
        r: httpx.Response = c.get(f"https://api.bilibili.com{path}", params=params)
        data: dict = r.json()
    if data.get("code") != 0:
        raise RuntimeError(data.get("message", "API 未知错误"))
    return data.get("data", {})


def _api_get_safe(path: str, params: dict) -> dict:
    r"""
    安全调用 B 站 API, 异常时返回空字典
    :param: path: API 路径
    :param: params: 查询参数
    :return: dict: API 返回的 data 字段或空字典
    """
    try:
        return _api_get(path, params)
    except Exception:
        return {}


def _fetch_video(bvid: str = "", avid: str = "") -> dict:
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
    return _api_get("/x/web-interface/view", params)


def _fetch_video_tags(bvid: str = "", avid: str = "") -> list:
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
    return _api_get_safe("/x/tag/archive/tags", params) or []


def _fetch_user_card(mid: str) -> dict:
    r"""
    获取用户卡片信息
    :param: mid: 用户 UID
    :return: dict: 用户卡片数据
    """
    return _api_get("/x/web-interface/card", {"mid": mid, "photo": "true"})


def _fetch_user_upstat(mid: str) -> dict:
    r"""
    获取 UP 主统计信息
    :param: mid: 用户 UID
    :return: dict: 统计数据
    """
    return _api_get_safe("/x/space/upstat", {"mid": mid})


def _fetch_favorites_list(mid: str) -> list:
    r"""
    获取用户收藏夹列表
    :param: mid: 用户 UID
    :return: list: 收藏夹列表
    """
    data: dict = _api_get_safe("/x/v3/fav/folder/created/list-all", {"up_mid": mid})
    return data.get("list", []) or [] if isinstance(data, dict) else []


def _fetch_favorite_content(media_id: int, pn: int = 1, ps: int = 20) -> dict:
    r"""
    获取收藏夹内容
    :param: media_id: 收藏夹 ID
    :param: pn: 页码
    :param: ps: 每页数量
    :return: dict: 收藏夹内容
    """
    return _api_get_safe("/x/v3/fav/resource/list", {"media_id": media_id, "pn": pn, "ps": ps})


def _fetch_article(cvid: str) -> dict:
    r"""
    获取专栏文章信息
    :param: cvid: 专栏 cv 号
    :return: dict: 专栏信息
    """
    return _api_get_safe("/x/article/viewinfo", {"id": cvid})


def _md_video(info: dict, tags: list, cfg: dict) -> str:
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
        f"> 导出时间: {_ts_full()}\n",
    ]

    if cfg.get("include_cover") == "true" and pic:
        lines.append(f"![封面]({pic})\n")

    lines.extend([
        "## 基本信息\n", "| 项目 | 内容 |", "|------|------|",
        f"| UP主 | [{owner.get('name', '—')}](https://space.bilibili.com/{owner.get('mid', '')}) |",
        f"| 发布时间 | {_fmt_ts(info.get('pubdate', 0))} |",
        f"| 分区 | {info.get('tname', '')} |",
        f"| 时长 | {_fmt_dur(info.get('duration', 0))} |",
        f"| 链接 | https://www.bilibili.com/video/{bvid} |", "",
    ])

    if cfg.get("include_stats") == "true":
        lines.extend(["## 数据统计\n", "| 指标 | 数值 |", "|------|------|"])
        for k, label in [
            ("view", "播放"), ("danmaku", "弹幕"), ("reply", "评论"),
            ("like", "点赞"), ("coin", "投币"), ("favorite", "收藏"), ("share", "转发"),
        ]:
            lines.append(f"| {label} | {_fmt_num(stat.get(k, 0))} |")
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
            f"| P{p.get('page', '')} | {p.get('part', '')} | {_fmt_dur(p.get('duration', 0))} |" for p in pages
        )
        lines.append("")

    lines.extend(["---", f"*由 MyBiOut! MdOut 导出于 {_ts_full()}*"])
    return "\n".join(lines)


def _md_user(card_data: dict, upstat: dict, favorites: list, fav_contents: dict, cfg: dict) -> str:
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
        f"> 导出时间: {_ts_full()}\n",
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
        lines.extend([
            f"| 粉丝 | {_fmt_num(fans)} |", f"| 关注 | {_fmt_num(friend)} |",
            f"| 投稿视频 | {archive_count} |",
        ])
        if like_num:
            lines.append(f"| 获赞 | {_fmt_num(like_num)} |")
        if upstat:
            if av := upstat.get("archive", {}).get("view", 0):
                lines.append(f"| 视频总播放 | {_fmt_num(av)} |")
            if arv := upstat.get("article", {}).get("view", 0):
                lines.append(f"| 文章总阅读 | {_fmt_num(arv)} |")
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

    lines.extend(["---", f"*由 MyBiOut! MdOut 导出于 {_ts_full()}*"])
    return "\n".join(lines)


def _md_article(info: dict, cfg: dict) -> str:
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
        f"> 导出时间: {_ts_full()}\n",
    ]

    if cfg.get("include_cover") == "true" and banner:
        lines.append(f"![头图]({banner})\n")

    lines.extend(["## 基本信息\n", "| 项目 | 内容 |", "|------|------|"])
    if author := info.get("author_name", "") or str(info.get("mid", "")):
        lines.append(f"| 作者 | {author} |")
    if publish := info.get("publish_time", 0):
        lines.append(f"| 发布时间 | {_fmt_ts(publish)} |")
    if info.get("mid"):
        lines.append(f"| 链接 | https://www.bilibili.com/read/cv{info.get('id', '')} |")
    lines.append("")

    if cfg.get("include_stats") == "true" and stats:
        lines.extend(["## 数据统计\n", "| 指标 | 数值 |", "|------|------|"])
        for k, label in [
            ("view", "阅读"), ("like", "点赞"), ("reply", "评论"),
            ("favorite", "收藏"), ("coin", "投币"), ("share", "转发"),
        ]:
            lines.append(f"| {label} | {_fmt_num(stats.get(k, 0))} |")
        lines.append("")

    lines.extend(["---", f"*由 MyBiOut! MdOut 导出于 {_ts_full()}*"])
    return "\n".join(lines)


@dataclass(slots=True)
class MdCard:
    r"""
    Markdown 导出卡片数据模型
    """
    id: str = field(default_factory=_uid)
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

    def to_dict(self) -> dict:
        r"""
        转换为前端可用的字典
        :return: dict: 卡片字典
        """
        return {
            "id": self.id, "input_text": self.input_text, "item_type": self.item_type,
            "id_value": self.id_value, "title": self.title, "subtitle": self.subtitle,
            "has_markdown": bool(self.markdown), "status": self.status,
            "error": self.error, "filename": self.filename,
        }


class _State:
    r"""
    MdOut 全局运行状态管理
    """

    def __init__(self) -> None:
        r"""
        初始化全局状态
        """
        self.lock: threading.RLock = threading.RLock()
        self.cards: list[MdCard] = []
        self.completed: list[MdCard] = []
        self.logs: list[dict] = []
        self.selected_id: str = ""
        self._fetch_queue: list[str] = []
        self._worker: threading.Thread | None = None
        self._cancel: threading.Event = threading.Event()

    def log(self, level: str, msg: str) -> None:
        r"""
        记录日志
        :param: level: 日志级别
        :param: msg: 日志消息
        """
        with self.lock:
            self.logs.append({"time": _ts(), "level": level, "msg": msg})
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

    def _find(self, card_id: str) -> MdCard | None:
        r"""
        按 ID 查找卡片
        :param: card_id: 卡片 ID
        :return: MdCard | None: 找到的卡片或 None
        """
        for c in self.cards:
            if c.id == card_id:
                return c
        return None


S: _State = _State()


def _settings_dict() -> dict[str, str]:
    r"""
    获取 MdOut 相关设置字典
    :return: dict[str, str]: 设置键值对
    """
    return {
        "include_cover": utils.get_setting("mdout", "include_cover"),
        "include_tags": utils.get_setting("mdout", "include_tags"),
        "include_stats": utils.get_setting("mdout", "include_stats"),
        "favorite_detail": utils.get_setting("mdout", "favorite_detail"),
    }


def _do_fetch_video(card: MdCard) -> None:
    r"""
    获取视频信息并生成 Markdown
    :param: card: Markdown 卡片
    """
    cfg: dict[str, str] = _settings_dict()
    info: dict = _fetch_video(bvid=card.id_value) if card.id_type == "bvid" else _fetch_video(avid=card.id_value)
    card.title = info.get("title", "未知视频")
    owner: dict = info.get("owner", {})
    card.subtitle = f"{owner.get('name', '—')} · {_fmt_dur(info.get('duration', 0))}"
    _delay()
    tags: list = []
    if cfg.get("include_tags") == "true":
        bvid: str = info.get("bvid", card.id_value if card.id_type == "bvid" else "")
        avid: str = str(info.get("aid", card.id_value if card.id_type == "avid" else ""))
        tags = _fetch_video_tags(bvid=bvid, avid=avid)
        if not isinstance(tags, list):
            tags = []
    card.markdown = _md_video(info, tags, cfg)


def _do_fetch_user(card: MdCard) -> None:
    r"""
    获取用户信息并生成 Markdown
    :param: card: Markdown 卡片
    """
    cfg: dict[str, str] = _settings_dict()
    card_data: dict = _fetch_user_card(card.id_value)
    crd: dict = card_data.get("card", {})
    card.title = crd.get("name", "未知用户")
    card.subtitle = f"UID {card.id_value} · 粉丝 {_fmt_num(card_data.get('follower', 0))}"
    _delay()
    upstat: dict = _fetch_user_upstat(card.id_value)
    _delay()
    favorites: list = _fetch_favorites_list(card.id_value)
    fav_contents: dict[int, dict] = {}
    if cfg.get("favorite_detail") == "full" and favorites:
        max_fav: int = 20
        for i, fav in enumerate(favorites[:max_fav]):
            if S._cancel.is_set():
                break
            _delay()
            if fav_id := fav.get("id", 0):
                if fc := _fetch_favorite_content(fav_id, pn=1, ps=20):
                    fav_contents[fav_id] = fc
            S.log("info", f"获取收藏夹 ({i + 1}/{min(len(favorites), max_fav)}): {fav.get('title', '')}")
    card.markdown = _md_user(card_data, upstat, favorites, fav_contents, cfg)


def _do_fetch_article(card: MdCard) -> None:
    r"""
    获取专栏信息并生成 Markdown
    :param: card: Markdown 卡片
    :raise: RuntimeError: 无法获取专栏信息
    """
    cfg: dict[str, str] = _settings_dict()
    info: dict = _fetch_article(card.id_value)
    if not info:
        raise RuntimeError("无法获取专栏信息")
    card.title = info.get("title", "未知专栏")
    card.subtitle = f"cv{card.id_value}"
    card.markdown = _md_article(info, cfg)


def _worker_fn() -> None:
    r"""
    后台 worker 线程函数, 逐个处理获取队列
    """
    while True:
        with S.lock:
            if not S._fetch_queue or S._cancel.is_set():
                S._worker = None
                return
            card_id: str = S._fetch_queue.pop(0)
            card: MdCard | None = S._find(card_id)
            if not card or card.status != "pending":
                continue
            card.status = "fetching"

        S.log("info", f"获取中: {card.input_text}")
        try:
            match card.item_type:
                case "video":
                    _do_fetch_video(card)
                case "user":
                    _do_fetch_user(card)
                case "article":
                    _do_fetch_article(card)
                case _:
                    raise RuntimeError("无法识别的类型")
            with S.lock:
                card.status = "ready"
            S.log("success", f"获取完成: {card.title}")
        except Exception as e:
            with S.lock:
                card.status = "failed"
                card.error = str(e)
            S.log("error", f"获取失败: {card.input_text} — {e}")
        _delay()


def _ensure_worker() -> None:
    r"""
    确保后台 worker 线程正在运行
    """
    with S.lock:
        if S._worker is None or not S._worker.is_alive():
            S._cancel.clear()
            t: threading.Thread = threading.Thread(target=_worker_fn, daemon=True)
            S._worker = t
            t.start()


def get_state() -> dict:
    r"""
    获取当前状态快照
    :return: dict: 状态数据
    """
    return S.snapshot()


def do_parse(text: str) -> dict[str, str]:
    r"""
    解析用户输入文本
    :param: text: 输入文本
    :return: dict[str, str]: 解析结果
    """
    return parse_input(text)


def add_and_fetch(input_text: str) -> dict:
    r"""
    添加获取任务并启动异步获取
    :param: input_text: 用户输入文本
    :return: dict: 添加结果
    """
    parsed: dict[str, str] = parse_input(input_text)
    if parsed["type"] == "unknown":
        return {"ok": False, "error": f"无法识别: {input_text}"}
    card: MdCard = MdCard(
        input_text=input_text, item_type=parsed["type"],
        id_type=parsed["id_type"], id_value=parsed["id_value"],
        title=f"[{_TYPE_LABELS.get(parsed['type'], '?')}] {parsed['id_value']}",
        subtitle="等待获取...", status="pending",
    )
    with S.lock:
        S.cards.append(card)
        S._fetch_queue.append(card.id)
    S.log("info", f"已添加: {input_text} → {_TYPE_LABELS.get(parsed['type'], '?')}")
    _ensure_worker()
    return {"ok": True, "card_id": card.id}


def select_card(card_id: str) -> None:
    r"""
    选中卡片以预览
    :param: card_id: 卡片 ID
    """
    with S.lock:
        S.selected_id = card_id


def export_cards(card_ids: list[str]) -> dict:
    r"""
    导出指定卡片为 Markdown 文件
    :param: card_ids: 卡片 ID 列表
    :return: dict: 导出结果
    """
    output_dir: Path = utils.get_export_path() / utils.get_setting("mdout", "folder")
    output_dir.mkdir(parents=True, exist_ok=True)

    exported: int = 0
    with S.lock:
        targets: list[MdCard] = [c for c in S.cards if c.id in card_ids and c.status == "ready"]

    for card in targets:
        if not card.markdown:
            continue
        fname: str = _sanitize(card.title or "untitled") + ".md"
        out: Path = output_dir / fname
        counter: int = 1
        while out.exists():
            out = output_dir / f"{_sanitize(card.title or 'untitled')}_{counter}.md"
            counter += 1
        try:
            out.write_text(card.markdown, encoding="utf-8")
            with S.lock:
                card.status = "success"
                card.filename = out.name
                S.cards = [c for c in S.cards if c.id != card.id]
                S.completed.append(card)
            exported += 1
            S.log("success", f"已导出: {out.name}")
        except Exception as e:
            with S.lock:
                card.status = "failed"
                card.error = str(e)
            S.log("error", f"导出失败: {card.title} — {e}")

    return {"ok": True, "exported": exported}


def export_all_ready() -> dict:
    r"""
    导出全部就绪的卡片
    :return: dict: 导出结果
    """
    with S.lock:
        ids: list[str] = [c.id for c in S.cards if c.status == "ready"]
    if not ids:
        return {"ok": False, "error": "没有可导出的项目"}
    return export_cards(ids)


def remove_cards(card_ids: list[str]) -> None:
    r"""
    移除指定卡片
    :param: card_ids: 卡片 ID 列表
    """
    ids: set[str] = set(card_ids)
    with S.lock:
        S.cards = [c for c in S.cards if c.id not in ids]
        S._fetch_queue = [fid for fid in S._fetch_queue if fid not in ids]


def clear_cards() -> None:
    r"""
    清空全部卡片和获取队列
    """
    with S.lock:
        S.cards.clear()
        S._fetch_queue.clear()
        S.selected_id = ""
    S.log("info", "已清空获取列表")


def clear_completed() -> None:
    r"""
    清空已完成列表
    """
    with S.lock:
        S.completed.clear()
    S.log("info", "已清空完成列表")
    