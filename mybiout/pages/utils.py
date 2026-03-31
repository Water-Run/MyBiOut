"""MyBiOut! 基础工具 —— 配置读写与通用方法"""

import configparser
from pathlib import Path

_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.ini"
_DEFAULT_PORT = 23333

# ============================== 默认值辅助 ==============================


def get_default_bilibili_pc_cache_path() -> str:
    """默认的哔哩哔哩电脑端缓存路径: C:\\Users\\[用户名]\\Videos\\bilibili"""
    return str(Path.home() / "Videos" / "bilibili")


# ============================== 默认值 ==============================

DEFAULTS: dict[str, dict[str, str]] = {
    "export": {
        "path": r"C:\MyBiOut!",
    },
    "api": {
        "key": "",
        "model": "",
    },
    "localout": {
        "folder": "localout!",
        "scan_android": "true",
        "bilibili_pc_cache_path": get_default_bilibili_pc_cache_path(),
        "bilibili_pc_cache_optional_when_installed": "true",
        "scan_interval": "1s",
        "name_parts": "title",
        "incomplete_title_action": "partial_or_folder",
        "ffmpeg_concurrent": "3",
    },
    "bbdown": {
        "folder": "bbdown!",
        "cookie": "",
        "encoding_priority": "",
        "quality_priority": "",
        "download_danmaku": "false",
        "skip_subtitle": "false",
        "skip_cover": "false",
        "file_pattern": "<videoTitle>",
        "multi_file_pattern": "<videoTitle>/[P<pageNumberWithZero>]<pageTitle>",
        "use_aria2c": "false",
    },
    "mdout": {
        "folder": "mdout!",
        "sessdata": "",
        "include_cover": "true",
        "include_tags": "true",
        "include_stats": "true",
        "favorite_detail": "basic",
        "request_delay": "0.5",
    },
}

# ============================== 读写 ==============================


def load_config() -> configparser.ConfigParser:
    """读取配置文件, 不存在则全部走默认值."""
    cfg = configparser.ConfigParser()
    for section, kvs in DEFAULTS.items():
        cfg[section] = dict(kvs)
    if _CONFIG_PATH.exists():
        cfg.read(_CONFIG_PATH, encoding="utf-8")
    return cfg


def save_config(cfg: configparser.ConfigParser) -> None:
    """将配置写回文件."""
    with open(_CONFIG_PATH, "w", encoding="utf-8") as f:
        f.write("# MyBiOut! 配置文件\n\n")
        cfg.write(f)


# ============================== 查 / 改 ==============================


def get_all_settings() -> dict[str, dict[str, str]]:
    """返回全部设置, 按 section→key→value 组织."""
    cfg = load_config()
    return {sec: dict(cfg[sec]) for sec in cfg.sections()}


def get_setting(section: str, key: str) -> str:
    """取一项."""
    cfg = load_config()
    fallback = DEFAULTS.get(section, {}).get(key, "")
    return cfg.get(section, key, fallback=fallback)


def set_setting(section: str, key: str, value: str) -> None:
    """存一项."""
    cfg = load_config()
    if section not in cfg:
        cfg[section] = {}
    cfg[section][key] = value
    save_config(cfg)


# ============================== 便捷方法 ==============================


def get_export_path() -> Path:
    """获取导出根路径, 不存在则创建."""
    p = Path(get_setting("export", "path"))
    p.mkdir(parents=True, exist_ok=True)
    return p


def get_api_key() -> str:
    return get_setting("api", "key")


def get_api_model() -> str:
    return get_setting("api", "model")


def get_port() -> int:
    return _DEFAULT_PORT
