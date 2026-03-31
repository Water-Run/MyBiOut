r"""
MyBiOut! 设置页服务层, 负责设置的校验、浏览与业务逻辑

:file: mybiout/pages/ohmyconfig/ohmyconfig.py
:author: WaterRun
:time: 2026-03-31
"""

from pathlib import Path

from mybiout.pages import utils

type SettingResult = dict[str, bool | str]

_ALLOWED_BOOL: set[str] = {"true", "false"}
_ALLOWED_SCAN_INTERVAL: set[str] = {"1s", "8s", "45s"}
_ALLOWED_INCOMPLETE_TITLE_ACTION: set[str] = {"partial_or_folder", "folder_only", "skip"}
_ALLOWED_NAME_PARTS: set[str] = {"bv", "title", "up", "group", "part", "publish_time", "export_time"}
_ALLOWED_FAVORITE_DETAIL: set[str] = {"basic", "full"}
_ALLOWED_REQUEST_DELAY: set[str] = {"0.3", "0.5", "1.0", "2.0"}
_ALLOWED_API_TIMEOUT: set[str] = {"infinite", "8s", "20s", "60s", "100s", "1000s"}


def get_settings() -> dict[str, dict[str, str]]:
    r"""
    获取全部设置项
    :return: dict[str, dict[str, str]]: 全部设置
    """
    return utils.get_all_settings()


def validate_and_save(section: str, key: str, value: str) -> SettingResult:
    r"""
    校验后保存单条设置
    :param: section: 配置分区名
    :param: key: 配置键名
    :param: value: 配置值
    :return: SettingResult: 包含 ok 和可选 error 的结果字典
    """
    match (section, key):
        case ("export", "path"):
            if not value.strip():
                return _err("路径不能空着啊!")
            utils.set_setting(section, key, value.strip())
            return _ok()

        case ("localout" | "bbdown" | "mdout", "folder"):
            return _validate_folder(section, value)

        case ("localout", "scan_android" | "bilibili_pc_cache_optional_when_installed"):
            return _save_bool(section, key, value)

        case ("localout", "bilibili_pc_cache_path"):
            utils.set_setting(section, key, value.strip())
            return _ok()

        case ("localout", "scan_interval"):
            v: str = value.strip()
            if v not in _ALLOWED_SCAN_INTERVAL:
                return _err("扫描间隔只能是 1s / 8s / 45s")
            utils.set_setting(section, key, v)
            return _ok()

        case ("localout", "ffmpeg_concurrent"):
            v = value.strip()
            if not v.isdigit() or not (1 <= int(v) <= 32):
                return _err("ffmpeg并发范围建议 1~32")
            utils.set_setting(section, key, v)
            return _ok()

        case ("localout", "name_parts"):
            parts: list[str] = [x.strip() for x in value.split(",") if x.strip()]
            if not parts:
                return _err("命名至少勾一个吧!")
            if unknown := [x for x in parts if x not in _ALLOWED_NAME_PARTS]:
                return _err(f"出现了未知命名项: {', '.join(unknown)}")
            utils.set_setting(section, key, ",".join(parts))
            return _ok()

        case ("localout", "incomplete_title_action"):
            v = value.strip()
            if v not in _ALLOWED_INCOMPLETE_TITLE_ACTION:
                return _err("标题补全策略值不合法")
            utils.set_setting(section, key, v)
            return _ok()

        case ("bbdown", "download_danmaku" | "skip_subtitle" | "skip_cover" | "use_aria2c"):
            return _save_bool(section, key, value)

        case ("bbdown", "cookie"):
            utils.set_setting(section, key, value.strip())
            return _ok()

        case ("bbdown", "encoding_priority" | "quality_priority" | "file_pattern" | "multi_file_pattern"):
            utils.set_setting(section, key, value.strip())
            return _ok()

        case ("mdout", "include_cover" | "include_tags" | "include_stats"):
            return _save_bool(section, key, value)

        case ("mdout", "sessdata"):
            utils.set_setting(section, key, value.strip())
            return _ok()

        case ("mdout", "favorite_detail"):
            v = value.strip()
            if v not in _ALLOWED_FAVORITE_DETAIL:
                return _err("收藏夹详情只能是 basic / full")
            utils.set_setting(section, key, v)
            return _ok()

        case ("mdout", "request_delay"):
            v = value.strip()
            if v not in _ALLOWED_REQUEST_DELAY:
                return _err("请求间隔只能是 0.3 / 0.5 / 1.0 / 2.0")
            utils.set_setting(section, key, v)
            return _ok()
        
        case ("api", "key" | "model"):
            utils.set_setting(section, key, value.strip())
            return _ok()

        case ("api", "base_url"):
            v: str = value.strip()
            if not v:
                return _err("API 地址不能为空")
            if not (v.startswith("http://") or v.startswith("https://")):
                return _err("API 地址需以 http:// 或 https:// 开头")
            utils.set_setting(section, key, v.rstrip("/"))
            return _ok()

        case ("api", "timeout"):
            v: str = value.strip().lower()
            if v not in _ALLOWED_API_TIMEOUT:
                return _err("超时选项不合法")
            utils.set_setting(section, key, v)
            return _ok()

        case _:
            utils.set_setting(section, key, str(value))
            return _ok()


def _save_bool(section: str, key: str, value: str) -> SettingResult:
    r"""
    校验并保存布尔型设置
    :param: section: 配置分区名
    :param: key: 配置键名
    :param: value: 待校验值
    :return: SettingResult: 保存结果
    """
    v: str = value.strip().lower()
    if v not in _ALLOWED_BOOL:
        return _err("开关值不对劲, 只能 true/false")
    utils.set_setting(section, key, v)
    return _ok()


def _validate_folder(section: str, value: str) -> SettingResult:
    r"""
    校验并保存文件夹名称, 检查冲突
    :param: section: 配置分区名
    :param: value: 文件夹名称
    :return: SettingResult: 保存结果
    """
    name: str = value.strip()
    if not name:
        return _err("文件夹名不能空着!")

    for other in ("localout", "bbdown", "mdout"):
        if other != section and utils.get_setting(other, "folder") == name:
            return _err(f"和 {other} 的撞了!")

    export_dir: Path = Path(utils.get_setting("export", "path"))
    if export_dir.exists():
        owned: set[str] = {utils.get_setting(s, "folder") for s in ("localout", "bbdown", "mdout")}
        for item in export_dir.iterdir():
            if item.is_dir() and item.name == name and item.name not in owned:
                return _err(f"那里已经有叫 '{name}' 的了!")

    utils.set_setting(section, "folder", name)
    return _ok()


def browse_folder() -> str | None:
    r"""
    弹出系统文件夹选择对话框
    :return: str | None: 选中的路径, 取消时返回 None
    """
    try:
        from tkinter import Tk, filedialog
        root: Tk = Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        folder: str = filedialog.askdirectory(title="选一个地方放东西")
        root.destroy()
        return folder if folder else None
    except Exception:
        return None


def get_desktop_path() -> str:
    r"""
    获取桌面下的 MyBiOut! 路径
    :return: str: 桌面导出路径
    """
    return str(Path.home() / "Desktop" / "MyBiOut!")


def get_default_bili_pc_cache_path() -> str:
    r"""
    获取默认哔哩哔哩电脑端缓存路径
    :return: str: 默认缓存路径
    """
    return utils.get_default_bilibili_pc_cache_path()


def _ok() -> SettingResult:
    r"""
    构建成功结果
    :return: SettingResult: 成功结果字典
    """
    return {"ok": True}


def _err(msg: str) -> SettingResult:
    r"""
    构建失败结果
    :param: msg: 错误信息
    :return: SettingResult: 失败结果字典
    """
    return {"ok": False, "error": msg}
