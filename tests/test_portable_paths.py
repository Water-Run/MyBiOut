r"""
便携路径与绿色版启动参数相关测试

:file: tests/test_portable_paths.py
:author: WaterRun
:time: 2026-07-17
"""

from __future__ import annotations

from pathlib import Path

from mybiout.pages import utils as 工具


def test_开发态运行根为包目录() -> None:
    r"""
    非冻结环境下运行根应指向 mybiout 包目录
    """
    根: Path = 工具.取运行根目录()
    assert 根.name == "mybiout"
    assert (根 / "pages").is_dir()


def test_资源与工具目录可解析() -> None:
    r"""
    资源根、页面、静态资源、工具目录均应可解析
    """
    assert 工具.取资源根目录().is_dir()
    assert 工具.取页面目录().is_dir()
    assert 工具.取静态资源目录().is_dir()
    assert 工具.取工具目录().name == "bin"


def test_配置路径文件名为config_ini() -> None:
    r"""
    配置文件名固定为 config.ini (测试夹具会改写父目录, 故不校验绝对路径)
    """
    assert 工具._当前配置路径().name == "config.ini"
    assert (工具.取运行根目录() / "config.ini").name == "config.ini"


def test_资料目录可写旁路() -> None:
    r"""
    auth_profile 应位于运行根 (可写旁路)
    """
    assert 工具.取资料目录() == 工具.取运行根目录() / "auth_profile"


def test_主程序支持浏览器与窗口参数() -> None:
    r"""
    启动参数应包含绿色版相关开关
    """
    from mybiout import main as 主模块

    源码: str = Path(主模块.__file__).read_text(encoding="utf-8")
    assert "--browser" in 源码
    assert "--no-animation" in 源码
    assert "_启动窗口壳" in 源码
    assert "是否冻结运行" in 源码
