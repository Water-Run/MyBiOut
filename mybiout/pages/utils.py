"""MyBiOut! 基础工具"""

import configparser
from pathlib import Path

_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.ini"

_DEFAULT_PORT = 23333
_DEFAULT_EXPORT_PATH = "./output"


def load_config() -> configparser.ConfigParser:
    """
    读取配置文件.
    若文件不存在则返回仅含默认值的空配置.
    """
    config = configparser.ConfigParser()
    if _CONFIG_PATH.exists():
        config.read(_CONFIG_PATH, encoding="utf-8")
    return config


def get_export_path(config: configparser.ConfigParser | None = None) -> Path:
    """获取导出路径, 不存在则自动创建"""
    if config is None:
        config = load_config()
    raw = config.get("export", "path", fallback=_DEFAULT_EXPORT_PATH)
    p = Path(raw)
    p.mkdir(parents=True, exist_ok=True)
    return p


def get_api_key(config: configparser.ConfigParser | None = None) -> str:
    """获取 API KEY"""
    if config is None:
        config = load_config()
    return config.get("api", "key", fallback="")


def get_port() -> int:
    """获取默认端口号"""
    return _DEFAULT_PORT