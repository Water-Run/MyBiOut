"""MdOut! — Markdown 导出 服务层"""

import re
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path

import httpx

from mybiout.pages import utils

# ============================== 常量 ==============================

_BILI_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.bilibili.com",
    "Origin": "https://www.bilibili.com",
}

_URL_PATTERNS: list[tuple[re.Pattern, str, str]] = [
    (re.compile(r"(?:https?://)?(?:www\.)?bilibili\.com/video/(BV[\w]{10,})", re.I), "video", "bvid"),
    (re.compile(r"^(BV[\w]{10,})$", re.I), "video", "bvid"),
    (re.compile(r"(?:https?://)?(?:www\.)?bilibili\.com/video/av(\d+)", re.I), "video", "avid"),
    (re.compile(r"^av(\d+)$", re.I), "video", "avid"),
    (re.compile(r"(?:https?://)?(?:www\.)?bilibili\.com/read/cv(\d+)", re.I), "article", "cvid"),
    (re.compile(r"^cv(\d+)$", re.I), "article", "cvid"),
    (re.compile(r"(?:https?://)?space\.bilibili\.com/(\d+)", re.I), "user", "mid"),
]

_TYPE_LABELS = {"video": "视频", "user": "用户", "article": "专栏", "unknown": "未知"}


# ============================== 工具 ==============================


def _uid() -> str:
    return uuid.uuid4().hex[:12]


def _ts() -> str:
    return datetime.now().strftime("%H:%M:%S")


def _ts_full() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _sanitize(name: str) -> str:
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name)
    name = name.strip(". ")
    return name[:200] if name else "untitled"


def _fmt_num(n: int) -> str:
    if n is None:
        return "0"
    if n >= 100_000_000:
        return f"{n / 100_000_000:.1f}亿"
    if n >= 10_000:
        return f"{n / 10_000:.1f}万"
    return str(n)


def _fmt_dur(seconds: int) -> str:
    h, m, s = seconds // 3600, (seconds % 3600) // 60, seconds % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _fmt_ts(ts: int) -> str:
    if not ts:
        return ""
    try:
        return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return ""


# ============================== HTTP ==============================


def _client() -> httpx.Client:
    sessdata = utils.get_setting("mdout", "sessdata").strip()
    cookies = {}
    if sessdata:
        cookies["SESSDATA"] = sessdata
    return httpx.Client(
        headers=_BILI_HEADERS,
        cookies=cookies,
        timeout=20.0,
        follow_redirects=True,
    )


def _delay():
    try:
        d = float(utils.get_setting("mdout", "request_delay") or "0.5")
    except ValueError:
        d = 0.5
    time.sleep(max(0.1, d))


# ============================== URL 解析 ==============================


def parse_input(text: str) -> dict:
    text = text.strip()
    if not text:
        return {"type": "unknown", "id_type": "", "id_value": "", "label": ""}

    # b23 短链先解析
    b23 = re.match(r"(?:https?://)?b23\.tv/([\w]+)", text, re.I)
    if b23:
        try:
            with _client() as c:
                r = c.head(f"https://b23.tv/{b23.group(1)}")
                real_url = str(r.headers.get("location", r.url))
                return parse_input(real_url)
        except Exception:
            return {"type": "unknown", "id_type": "", "id_value": text, "label": "短链解析失败"}

    for pattern, item_type, id_type in _URL_PATTERNS:
        m = pattern.search(text)
        if m:
            return {"type": item_type, "id_type": id_type, "id_value": m.group(1), "label": _TYPE_LABELS[item_type]}

    # 纯数字 → 用户 UID
    if re.match(r"^\d{1,15}$", text):
        return {"type": "user", "id_type": "mid", "id_value": text, "label": "用户"}

    return {"type": "unknown", "id_type": "", "id_value": text, "label": "无法识别"}


# ============================== Bilibili API ==============================


def _api_get(path: str, params: dict) -> dict:
    with _client() as c:
        r = c.get(f"https://api.bilibili.com{path}", params=params)
        data = r.json()
    if data.get("code") != 0:
        raise RuntimeError(data.get("message", "API 未知错误"))
    return data.get("data", {})


def _api_get_safe(path: str, params: dict) -> dict:
    try:
        return _api_get(path, params)
    except Exception:
        return {}


def _fetch_video(bvid: str = "", avid: str = "") -> dict:
    params = {}
    if bvid:
        params["bvid"] = bvid
    elif avid:
        params["aid"] = avid
    return _api_get("/x/web-interface/view", params)


def _fetch_video_tags(bvid: str = "", avid: str = "") -> list:
    params = {}
    if bvid:
        params["bvid"] = bvid
    elif avid:
        params["aid"] = avid
    return _api_get_safe("/x/tag/archive/tags", params) or []


def _fetch_user_card(mid: str) -> dict:
    return _api_get("/x/web-interface/card", {"mid": mid, "photo": "true"})


def _fetch_user_upstat(mid: str) -> dict:
    return _api_get_safe("/x/space/upstat", {"mid": mid})


def _fetch_favorites_list(mid: str) -> list:
    data = _api_get_safe("/x/v3/fav/folder/created/list-all", {"up_mid": mid})
    if isinstance(data, dict):
        return data.get("list", []) or []
    return []


def _fetch_favorite_content(media_id: int, pn: int = 1, ps: int = 20) -> dict:
    return _api_get_safe(
        "/x/v3/fav/resource/list",
        {"media_id": media_id, "pn": pn, "ps": ps},
    )


def _fetch_article(cvid: str) -> dict:
    return _api_get_safe("/x/article/viewinfo", {"id": cvid})


# ============================== Markdown 生成器 ==============================


def _md_video(info: dict, tags: list, cfg: dict) -> str:
    title = info.get("title", "未知标题")
    bvid = info.get("bvid", "")
    avid = info.get("aid", "")
    desc = info.get("desc", "")
    owner = info.get("owner", {})
    stat = info.get("stat", {})
    pages = info.get("pages", [])
    pubdate = info.get("pubdate", 0)
    duration = info.get("duration", 0)
    tname = info.get("tname", "")
    pic = info.get("pic", "")

    L: list[str] = []
    L.append(f"# {title}\n")
    L.append(f"> {bvid} | av{avid}")
    L.append(f"> 导出时间: {_ts_full()}\n")

    if cfg.get("include_cover") == "true" and pic:
        L.append(f"![封面]({pic})\n")

    L.append("## 基本信息\n")
    L.append("| 项目 | 内容 |")
    L.append("|------|------|")
    L.append(f"| UP主 | [{owner.get('name', '—')}](https://space.bilibili.com/{owner.get('mid', '')}) |")
    L.append(f"| 发布时间 | {_fmt_ts(pubdate)} |")
    L.append(f"| 分区 | {tname} |")
    L.append(f"| 时长 | {_fmt_dur(duration)} |")
    L.append(f"| 链接 | https://www.bilibili.com/video/{bvid} |")
    L.append("")

    if cfg.get("include_stats") == "true":
        L.append("## 数据统计\n")
        L.append("| 指标 | 数值 |")
        L.append("|------|------|")
        for k, label in [
            ("view", "播放"), ("danmaku", "弹幕"), ("reply", "评论"),
            ("like", "点赞"), ("coin", "投币"), ("favorite", "收藏"), ("share", "转发"),
        ]:
            L.append(f"| {label} | {_fmt_num(stat.get(k, 0))} |")
        L.append("")

    if desc:
        L.append("## 简介\n")
        L.append(desc + "\n")

    if cfg.get("include_tags") == "true" and tags:
        tag_list = tags if isinstance(tags, list) else []
        tag_strs = [f"`{t.get('tag_name', '')}`" for t in tag_list if t.get("tag_name")]
        if tag_strs:
            L.append("## 标签\n")
            L.append(" ".join(tag_strs) + "\n")

    if len(pages) > 1:
        L.append("## 分P列表\n")
        L.append("| P | 标题 | 时长 |")
        L.append("|---|------|------|")
        for p in pages:
            L.append(f"| P{p.get('page', '')} | {p.get('part', '')} | {_fmt_dur(p.get('duration', 0))} |")
        L.append("")

    L.append("---")
    L.append(f"*由 MyBiOut! MdOut 导出于 {_ts_full()}*")
    return "\n".join(L)


def _md_user(card_data: dict, upstat: dict, favorites: list, fav_contents: dict, cfg: dict) -> str:
    card = card_data.get("card", {})
    name = card.get("name", "未知用户")
    mid = card.get("mid", "")
    sign = card.get("sign", "")
    level = card.get("level_info", {}).get("current_level", 0)
    face = card.get("face", "")
    sex = card.get("sex", "")
    fans = card_data.get("follower", 0) or card.get("fans", 0)
    friend = card.get("attention", 0) or card.get("friend", 0)
    archive_count = card_data.get("archive_count", 0)
    like_num = card_data.get("like_num", 0)

    official = card.get("Official", {})
    official_title = official.get("title", "") if official else ""

    L: list[str] = []
    L.append(f"# {name}\n")
    L.append(f"> UID: {mid}")
    L.append(f"> 导出时间: {_ts_full()}\n")

    if cfg.get("include_cover") == "true" and face:
        L.append(f"![头像]({face})\n")

    L.append("## 基本信息\n")
    L.append("| 项目 | 内容 |")
    L.append("|------|------|")
    L.append(f"| 昵称 | {name} |")
    L.append(f"| UID | {mid} |")
    if sex and sex != "保密":
        L.append(f"| 性别 | {sex} |")
    L.append(f"| 等级 | Lv.{level} |")
    if official_title:
        L.append(f"| 认证 | {official_title} |")
    if sign:
        L.append(f"| 签名 | {sign} |")
    L.append(f"| 空间链接 | https://space.bilibili.com/{mid} |")
    L.append("")

    if cfg.get("include_stats") == "true":
        L.append("## 数据统计\n")
        L.append("| 指标 | 数值 |")
        L.append("|------|------|")
        L.append(f"| 粉丝 | {_fmt_num(fans)} |")
        L.append(f"| 关注 | {_fmt_num(friend)} |")
        L.append(f"| 投稿视频 | {archive_count} |")
        if like_num:
            L.append(f"| 获赞 | {_fmt_num(like_num)} |")
        if upstat:
            av = upstat.get("archive", {}).get("view", 0)
            arv = upstat.get("article", {}).get("view", 0)
            if av:
                L.append(f"| 视频总播放 | {_fmt_num(av)} |")
            if arv:
                L.append(f"| 文章总阅读 | {_fmt_num(arv)} |")
        L.append("")

    if favorites:
        L.append("## 收藏夹\n")
        detail = cfg.get("favorite_detail", "basic")
        for fav in favorites:
            fav_id = fav.get("id", 0)
            fav_title = fav.get("title", "未命名")
            fav_count = fav.get("media_count", 0)
            L.append(f"### {fav_title}\n")
            L.append(f"共 {fav_count} 个内容\n")

            if detail == "full" and fav_id in fav_contents:
                content = fav_contents[fav_id]
                medias = content.get("medias") or []
                if medias:
                    L.append("| # | 标题 | UP主 | BV号 |")
                    L.append("|---|------|------|------|")
                    for idx, m in enumerate(medias, 1):
                        mt = (m.get("title") or "—").replace("|", "\\|")
                        mu = (m.get("upper", {}).get("name") or "—").replace("|", "\\|")
                        mb = m.get("bvid") or "—"
                        L.append(f"| {idx} | {mt} | {mu} | {mb} |")
                    total = content.get("info", {}).get("media_count", fav_count)
                    if len(medias) < total:
                        L.append(f"\n*（仅显示前 {len(medias)} 项，共 {total} 项）*")
                    L.append("")

    L.append("---")
    L.append(f"*由 MyBiOut! MdOut 导出于 {_ts_full()}*")
    return "\n".join(L)


def _md_article(info: dict, cfg: dict) -> str:
    title = info.get("title", "未知专栏")
    stats = info.get("stats", {})
    mid = info.get("mid", "")
    author = info.get("author_name", "") or str(mid)
    banner = info.get("banner_url", "")
    publish = info.get("publish_time", 0)

    L: list[str] = []
    L.append(f"# {title}\n")
    L.append(f"> 专栏 cv{info.get('id', '')}")
    L.append(f"> 导出时间: {_ts_full()}\n")

    if cfg.get("include_cover") == "true" and banner:
        L.append(f"![头图]({banner})\n")

    L.append("## 基本信息\n")
    L.append("| 项目 | 内容 |")
    L.append("|------|------|")
    if author:
        L.append(f"| 作者 | {author} |")
    if publish:
        L.append(f"| 发布时间 | {_fmt_ts(publish)} |")
    if mid:
        L.append(f"| 链接 | https://www.bilibili.com/read/cv{info.get('id', '')} |")
    L.append("")

    if cfg.get("include_stats") == "true" and stats:
        L.append("## 数据统计\n")
        L.append("| 指标 | 数值 |")
        L.append("|------|------|")
        for k, label in [
            ("view", "阅读"), ("like", "点赞"), ("reply", "评论"),
            ("favorite", "收藏"), ("coin", "投币"), ("share", "转发"),
        ]:
            L.append(f"| {label} | {_fmt_num(stats.get(k, 0))} |")
        L.append("")

    L.append("---")
    L.append(f"*由 MyBiOut! MdOut 导出于 {_ts_full()}*")
    return "\n".join(L)


# ============================== MdCard ==============================


class MdCard:
    __slots__ = (
        "id", "input_text", "item_type", "id_type", "id_value",
        "title", "subtitle", "markdown", "status", "error", "filename",
    )

    def __init__(self, **kw):
        self.id: str = kw.get("id", _uid())
        self.input_text: str = kw.get("input_text", "")
        self.item_type: str = kw.get("item_type", "unknown")
        self.id_type: str = kw.get("id_type", "")
        self.id_value: str = kw.get("id_value", "")
        self.title: str = kw.get("title", "")
        self.subtitle: str = kw.get("subtitle", "")
        self.markdown: str = kw.get("markdown", "")
        self.status: str = kw.get("status", "pending")
        self.error: str = kw.get("error", "")
        self.filename: str = kw.get("filename", "")

    def to_dict(self) -> dict:
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
        }


# ============================== 全局状态 ==============================


class _State:
    def __init__(self):
        self.lock = threading.RLock()
        self.cards: list[MdCard] = []
        self.completed: list[MdCard] = []
        self.logs: list[dict] = []
        self.selected_id: str = ""
        self._fetch_queue: list[str] = []
        self._worker: threading.Thread | None = None
        self._cancel = threading.Event()

    def log(self, level: str, msg: str):
        with self.lock:
            self.logs.append({"time": _ts(), "level": level, "msg": msg})
            if len(self.logs) > 500:
                self.logs = self.logs[-300:]

    def snapshot(self) -> dict:
        with self.lock:
            sel_md = ""
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
        for c in self.cards:
            if c.id == card_id:
                return c
        return None


S = _State()


# ============================== 获取 Worker ==============================


def _settings_dict() -> dict:
    return {
        "include_cover": utils.get_setting("mdout", "include_cover"),
        "include_tags": utils.get_setting("mdout", "include_tags"),
        "include_stats": utils.get_setting("mdout", "include_stats"),
        "favorite_detail": utils.get_setting("mdout", "favorite_detail"),
    }


def _do_fetch_video(card: MdCard):
    cfg = _settings_dict()
    if card.id_type == "bvid":
        info = _fetch_video(bvid=card.id_value)
    else:
        info = _fetch_video(avid=card.id_value)
    card.title = info.get("title", "未知视频")
    owner = info.get("owner", {})
    card.subtitle = f"{owner.get('name', '—')} · {_fmt_dur(info.get('duration', 0))}"
    _delay()
    tags = []
    if cfg.get("include_tags") == "true":
        bvid = info.get("bvid", card.id_value if card.id_type == "bvid" else "")
        avid = str(info.get("aid", card.id_value if card.id_type == "avid" else ""))
        tags = _fetch_video_tags(bvid=bvid, avid=avid)
        if not isinstance(tags, list):
            tags = []
    card.markdown = _md_video(info, tags, cfg)


def _do_fetch_user(card: MdCard):
    cfg = _settings_dict()
    card_data = _fetch_user_card(card.id_value)
    crd = card_data.get("card", {})
    card.title = crd.get("name", "未知用户")
    card.subtitle = f"UID {card.id_value} · 粉丝 {_fmt_num(card_data.get('follower', 0))}"
    _delay()
    upstat = _fetch_user_upstat(card.id_value)
    _delay()
    favorites = _fetch_favorites_list(card.id_value)
    fav_contents: dict[int, dict] = {}
    if cfg.get("favorite_detail") == "full" and favorites:
        max_fav = 20
        for i, fav in enumerate(favorites[:max_fav]):
            if S._cancel.is_set():
                break
            _delay()
            fav_id = fav.get("id", 0)
            if fav_id:
                fc = _fetch_favorite_content(fav_id, pn=1, ps=20)
                if fc:
                    fav_contents[fav_id] = fc
            S.log("info", f"获取收藏夹 ({i + 1}/{min(len(favorites), max_fav)}): {fav.get('title', '')}")
    card.markdown = _md_user(card_data, upstat, favorites, fav_contents, cfg)


def _do_fetch_article(card: MdCard):
    cfg = _settings_dict()
    info = _fetch_article(card.id_value)
    if not info:
        raise RuntimeError("无法获取专栏信息")
    card.title = info.get("title", "未知专栏")
    card.subtitle = f"cv{card.id_value}"
    card.markdown = _md_article(info, cfg)


def _worker_fn():
    while True:
        card_id = None
        with S.lock:
            if not S._fetch_queue or S._cancel.is_set():
                S._worker = None
                return
            card_id = S._fetch_queue.pop(0)
            card = S._find(card_id)
            if not card or card.status != "pending":
                continue
            card.status = "fetching"

        S.log("info", f"获取中: {card.input_text}")
        try:
            if card.item_type == "video":
                _do_fetch_video(card)
            elif card.item_type == "user":
                _do_fetch_user(card)
            elif card.item_type == "article":
                _do_fetch_article(card)
            else:
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


def _ensure_worker():
    with S.lock:
        if S._worker is None or not S._worker.is_alive():
            S._cancel.clear()
            t = threading.Thread(target=_worker_fn, daemon=True)
            S._worker = t
            t.start()


# ============================== 公共 API ==============================


def get_state() -> dict:
    return S.snapshot()


def do_parse(text: str) -> dict:
    return parse_input(text)


def add_and_fetch(input_text: str) -> dict:
    parsed = parse_input(input_text)
    if parsed["type"] == "unknown":
        return {"ok": False, "error": f"无法识别: {input_text}"}
    card = MdCard(
        input_text=input_text,
        item_type=parsed["type"],
        id_type=parsed["id_type"],
        id_value=parsed["id_value"],
        title=f"[{_TYPE_LABELS.get(parsed['type'], '?')}] {parsed['id_value']}",
        subtitle="等待获取...",
        status="pending",
    )
    with S.lock:
        S.cards.append(card)
        S._fetch_queue.append(card.id)
    S.log("info", f"已添加: {input_text} → {_TYPE_LABELS.get(parsed['type'], '?')}")
    _ensure_worker()
    return {"ok": True, "card_id": card.id}


def select_card(card_id: str):
    with S.lock:
        S.selected_id = card_id


def get_markdown(card_id: str) -> str:
    with S.lock:
        c = S._find(card_id)
        if c:
            return c.markdown
    return ""


def export_cards(card_ids: list[str]) -> dict:
    export_root = utils.get_export_path()
    folder = utils.get_setting("mdout", "folder")
    output_dir = export_root / folder
    output_dir.mkdir(parents=True, exist_ok=True)

    exported = 0
    with S.lock:
        targets = [c for c in S.cards if c.id in card_ids and c.status == "ready"]

    for card in targets:
        if not card.markdown:
            continue
        fname = _sanitize(card.title or "untitled") + ".md"
        out = output_dir / fname
        counter = 1
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
    with S.lock:
        ids = [c.id for c in S.cards if c.status == "ready"]
    if not ids:
        return {"ok": False, "error": "没有可导出的项目"}
    return export_cards(ids)


def remove_cards(card_ids: list[str]):
    ids = set(card_ids)
    with S.lock:
        S.cards = [c for c in S.cards if c.id not in ids]
        S._fetch_queue = [fid for fid in S._fetch_queue if fid not in ids]


def clear_cards():
    with S.lock:
        S.cards.clear()
        S._fetch_queue.clear()
        S.selected_id = ""
    S.log("info", "已清空获取列表")


def clear_completed():
    with S.lock:
        S.completed.clear()
    S.log("info", "已清空完成列表")
    