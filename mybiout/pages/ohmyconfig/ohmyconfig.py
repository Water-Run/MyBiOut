"""MyBiOut! 设置页 —— 服务层 (校验 / 浏览 / 业务逻辑)"""

from pathlib import Path

from mybiout.pages import utils


# ============================== 查询 ==============================


def get_settings() -> dict[str, dict[str, str]]:
    """给页面用的: 取全部设置."""
    return utils.get_all_settings()


# ============================== 保存 (带校验) ==============================


_ALLOWED_BOOL = {"true", "false"}
_ALLOWED_SCAN_INTERVAL = {"1s", "8s", "45s"}
_ALLOWED_INCOMPLETE_TITLE_ACTION = {
    "partial_or_folder",
    "folder_only",
    "skip",
}
_ALLOWED_NAME_PARTS = {
    "bv",
    "title",
    "up",
    "group",
    "part",
    "publish_time",
    "export_time",
}
_ALLOWED_FAVORITE_DETAIL = {"basic", "full"}
_ALLOWED_REQUEST_DELAY = {"0.3", "0.5", "1.0", "2.0"}


def validate_and_save(section: str, key: str, value: str) -> dict:
    """
    校验后保存单条设置.
    返回 ``{"ok": True}`` 或 ``{"ok": False, "error": "..."}``
    """
    # --- 导出路径 ---
    if section == "export" and key == "path":
        if not value.strip():
            return _err("路径不能空着啊!")
        utils.set_setting(section, key, value.strip())
        return _ok()

    # --- 文件夹名 ---
    if key == "folder" and section in ("localout", "bbdown", "mdout"):
        return _validate_folder(section, value)

    # --- localout: 布尔项 ---
    if section == "localout" and key in ("scan_android", "bilibili_pc_cache_optional_when_installed"):
        v = value.strip().lower()
        if v not in _ALLOWED_BOOL:
            return _err("开关值不对劲, 只能 true/false")
        utils.set_setting(section, key, v)
        return _ok()

    # --- localout: PC 缓存路径 ---
    if section == "localout" and key == "bilibili_pc_cache_path":
        utils.set_setting(section, key, value.strip())
        return _ok()

    # --- localout: 扫描间隔 ---
    if section == "localout" and key == "scan_interval":
        v = value.strip()
        if v not in _ALLOWED_SCAN_INTERVAL:
            return _err("扫描间隔只能是 1s / 8s / 45s")
        utils.set_setting(section, key, v)
        return _ok()

    # --- localout: ffmpeg 并发 ---
    if section == "localout" and key == "ffmpeg_concurrent":
        v = value.strip()
        if not v.isdigit():
            return _err("ffmpeg并发得是数字")
        n = int(v)
        if n < 1 or n > 32:
            return _err("ffmpeg并发范围建议 1~32")
        utils.set_setting(section, key, str(n))
        return _ok()

    # --- localout: 命名包含项 ---
    if section == "localout" and key == "name_parts":
        parts = [x.strip() for x in value.split(",") if x.strip()]
        if not parts:
            return _err("命名至少勾一个吧!")
        unknown = [x for x in parts if x not in _ALLOWED_NAME_PARTS]
        if unknown:
            return _err(f"出现了未知命名项: {', '.join(unknown)}")
        utils.set_setting(section, key, ",".join(parts))
        return _ok()

    # --- localout: 标题信息不完整策略 ---
    if section == "localout" and key == "incomplete_title_action":
        v = value.strip()
        if v not in _ALLOWED_INCOMPLETE_TITLE_ACTION:
            return _err("标题补全策略值不合法")
        utils.set_setting(section, key, v)
        return _ok()

    # --- bbdown: 布尔项 ---
    if section == "bbdown" and key in ("download_danmaku", "skip_subtitle", "skip_cover", "use_aria2c"):
        v = value.strip().lower()
        if v not in _ALLOWED_BOOL:
            return _err("开关值不对劲, 只能 true/false")
        utils.set_setting(section, key, v)
        return _ok()

    # --- bbdown: cookie ---
    if section == "bbdown" and key == "cookie":
        utils.set_setting(section, key, value.strip())
        return _ok()

    # --- bbdown: 文本项 (encoding_priority, quality_priority, file_pattern, multi_file_pattern) ---
    if section == "bbdown" and key in (
        "encoding_priority", "quality_priority",
        "file_pattern", "multi_file_pattern",
    ):
        utils.set_setting(section, key, value.strip())
        return _ok()

    # --- mdout: 布尔项 ---
    if section == "mdout" and key in ("include_cover", "include_tags", "include_stats"):
        v = value.strip().lower()
        if v not in _ALLOWED_BOOL:
            return _err("开关值不对劲, 只能 true/false")
        utils.set_setting(section, key, v)
        return _ok()

    # --- mdout: sessdata ---
    if section == "mdout" and key == "sessdata":
        utils.set_setting(section, key, value.strip())
        return _ok()

    # --- mdout: favorite_detail ---
    if section == "mdout" and key == "favorite_detail":
        v = value.strip()
        if v not in _ALLOWED_FAVORITE_DETAIL:
            return _err("收藏夹详情只能是 basic / full")
        utils.set_setting(section, key, v)
        return _ok()

    # --- mdout: request_delay ---
    if section == "mdout" and key == "request_delay":
        v = value.strip()
        if v not in _ALLOWED_REQUEST_DELAY:
            return _err("请求间隔只能是 0.3 / 0.5 / 1.0 / 2.0")
        utils.set_setting(section, key, v)
        return _ok()

    # --- 其余项直接存 ---
    utils.set_setting(section, key, str(value))
    return _ok()


def _validate_folder(section: str, value: str) -> dict:
    name = value.strip()
    if not name:
        return _err("文件夹名不能空着!")

    # 不可和其它模块的文件夹撞
    for other in ("localout", "bbdown", "mdout"):
        if other == section:
            continue
        if utils.get_setting(other, "folder") == name:
            return _err(f"和 {other} 的撞了!")

    # 不可和导出目录下已有的无关文件夹撞
    export_dir = Path(utils.get_setting("export", "path"))
    if export_dir.exists():
        owned = {
            utils.get_setting(s, "folder")
            for s in ("localout", "bbdown", "mdout")
        }
        for item in export_dir.iterdir():
            if item.is_dir() and item.name == name and item.name not in owned:
                return _err(f"那里已经有叫 '{name}' 的了!")

    utils.set_setting(section, "folder", name)
    return _ok()


# ============================== 浏览 / 桌面 ==============================


def browse_folder() -> str | None:
    """弹出系统文件夹选择对话框 (tkinter, 仅 Windows 本机)."""
    try:
        from tkinter import Tk, filedialog

        root = Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        folder = filedialog.askdirectory(title="选一个地方放东西")
        root.destroy()
        return folder if folder else None
    except Exception:
        return None


def get_desktop_path() -> str:
    """桌面下的 MyBiOut! 路径."""
    return str(Path.home() / "Desktop" / "MyBiOut!")


def get_default_bili_pc_cache_path() -> str:
    """默认哔哩哔哩电脑端缓存路径."""
    return utils.get_default_bilibili_pc_cache_path()


# ============================== 内部 ==============================


def _ok() -> dict:
    return {"ok": True}


def _err(msg: str) -> dict:
    return {"ok": False, "error": msg}
