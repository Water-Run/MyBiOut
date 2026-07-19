r"""
薄冒烟入口: 保证核心链路可 import / 可加载。
深度用例见 test_pack_* 与 test_app_contracts。
"""

from __future__ import annotations

from pathlib import Path


def test_工程布局完整(工程根: Path) -> None:
    assert (工程根 / "打包.py").is_file()
    assert (工程根 / "mybiout" / "main.py").is_file()
    assert (工程根 / "mybiout" / "pages" / "apis.py").is_file()
    assert (工程根 / "mybiout" / "version.txt").is_file()


def test_打包模块可加载(打包模块) -> None:
    assert hasattr(打包模块, "主程序")
    assert hasattr(打包模块, "执行完整打包")
    assert hasattr(打包模块, "打包进度")
    assert hasattr(打包模块, "快速代码检查")


def test_应用可加载() -> None:
    from mybiout.pages.apis import 应用
    from mybiout import 取版本号

    assert 应用.title
    assert 取版本号()
