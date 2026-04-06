r"""
MyBiOut! 基础工具模块, 负责配置文件的读写与通用方法

:file: mybiout/pages/utils.py
:author: WaterRun
:time: 2026-04-02
"""

import configparser
from pathlib import Path

_CONFIG_PATH: Path = Path(__file__).resolve().parent.parent / "config.ini"
_DEFAULT_PORT: int = 23333


def get_default_bilibili_pc_cache_path() -> str:
    r"""
    获取默认的哔哩哔哩电脑端缓存路径
    :return: str: 默认缓存路径
    """
    return str(Path.home() / "Videos" / "bilibili")


DEFAULTS: dict[str, dict[str, str]] = {
    "export": {
        "path": r"C:\MyBiOut!",
        "sessdata": "",
    },
    "api": {
        "key": "",
        "model": "",
        "base_url": "https://api.poe.com/v1",
        "timeout": "infinite",
    },
    "localout": {
        "folder": "localout!",
        "bilibili_pc_cache_path": get_default_bilibili_pc_cache_path(),
        "bilibili_pc_cache_optional_when_installed": "true",
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


def load_config() -> configparser.ConfigParser:
    r"""
    读取配置文件, 不存在则使用默认值
    :return: configparser.ConfigParser: 加载后的配置解析器
    """
    cfg: configparser.ConfigParser = configparser.ConfigParser()
    for section, kvs in DEFAULTS.items():
        cfg[section] = dict(kvs)
    if _CONFIG_PATH.exists():
        cfg.read(_CONFIG_PATH, encoding="utf-8")
    return cfg


def save_config(cfg: configparser.ConfigParser) -> None:
    r"""
    将配置写回文件
    :param: cfg: 配置解析器实例
    """
    with open(_CONFIG_PATH, "w", encoding="utf-8") as f:
        f.write("# MyBiOut! 配置文件\n\n")
        cfg.write(f)


def get_all_settings() -> dict[str, dict[str, str]]:
    r"""
    获取全部设置, 按 section → key → value 组织
    :return: dict[str, dict[str, str]]: 全部设置项
    """
    cfg: configparser.ConfigParser = load_config()
    return {sec: dict(cfg[sec]) for sec in cfg.sections()}


def get_setting(section: str, key: str) -> str:
    r"""
    获取单项设置值
    :param: section: 配置分区名
    :param: key: 配置键名
    :return: str: 配置值, 不存在时返回默认值
    """
    cfg: configparser.ConfigParser = load_config()
    fallback: str = DEFAULTS.get(section, {}).get(key, "")
    return cfg.get(section, key, fallback=fallback)


def set_setting(section: str, key: str, value: str) -> None:
    r"""
    保存单项设置值
    :param: section: 配置分区名
    :param: key: 配置键名
    :param: value: 配置值
    """
    cfg: configparser.ConfigParser = load_config()
    if section not in cfg:
        cfg[section] = {}
    cfg[section][key] = value
    save_config(cfg)


def get_export_path() -> Path:
    r"""
    获取导出根路径, 不存在则自动创建
    :return: Path: 导出根目录
    """
    p: Path = Path(get_setting("export", "path"))
    p.mkdir(parents=True, exist_ok=True)
    return p


def get_api_key() -> str:
    r"""
    获取 API Key
    :return: str: API Key 值
    """
    return get_setting("api", "key")


def get_api_model() -> str:
    r"""
    获取 API 模型名称
    :return: str: 模型名称
    """
    return get_setting("api", "model")


def get_port() -> int:
    r"""
    获取默认服务端口号
    :return: int: 端口号
    """
    return _DEFAULT_PORT

def get_api_base_url() -> str:
    r"""
    获取 API 基地址
    :return: str: API 基地址
    """
    return get_setting("api", "base_url") or "https://api.openai.com/v1"


def get_api_timeout_seconds() -> float | None:
    r"""
    获取 API 超时时间（秒）
    :return: float | None: None 表示无限超时
    """
    mode: str = (get_setting("api", "timeout") or "infinite").strip().lower()
    timeout_map: dict[str, float | None] = {
        "infinite": None,
        "8s": 8.0,
        "20s": 20.0,
        "60s": 60.0,
        "100s": 100.0,
        "1000s": 1000.0,
    }
    return timeout_map.get(mode, None)

def get_sessdata() -> str:
    r"""
    获取统一的 SESSDATA (优先共享设置, 兼容旧分区)
    :return: str: SESSDATA 值
    """
    shared: str = get_setting("export", "sessdata").strip()
    if shared:
        return shared
    # 兼容旧配置
    for sec in ("bbdown", "mdout"):
        old: str = get_setting(sec, "sessdata" if sec == "mdout" else "cookie").strip()
        if old:
            return old
    return ""
