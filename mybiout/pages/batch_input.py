r"""
批量输入解析与构建: 从混排粘贴中抽出链接 / BV / av 等标识

:file: mybiout/pages/batch_input.py
:author: WaterRun
:time: 2026-08-16
"""

import re as 正则

_已知标识: 正则.Pattern[str] = 正则.compile(
    r"(?:https?://[^\s,;，；、|\"'<>]+)"
    r"|(?:b23\.tv/[^\s,;，；、|\"'<>]+)"
    r"|(?:BV[0-9A-Za-z]{10,})"
    r"|(?:av\d+)"
    r"|(?:ep\d+)"
    r"|(?:ss\d+)",
    正则.I,
)
_分界: 正则.Pattern[str] = 正则.compile(r"[\s,;，；、|]+")


def _剥皮(项: str) -> str:
    r"""去掉引号与尾部常见标点。"""
    return (项 or "").strip().strip("\"'`“”‘’").rstrip(").,，。]/")


def 解析批量输入(文本: str) -> list[str]:
    r"""
    从用户粘贴文本中抽出条目, 保序去重。
    优先识别 URL / b23 / BV / av / ep / ss;
    若没有已知标识, 则按逗号、分号、空白、顿号、竖线切开。
    :param 文本: 原始粘贴
    :return: 条目列表
    """
    文本 = (文本 or "").strip()
    if not 文本:
        return []

    命中: list[str] = []
    已见: set[str] = set()
    for 匹配 in _已知标识.finditer(文本):
        项: str = _剥皮(匹配.group(0))
        if not 项:
            continue
        键: str = 项.lower()
        if 键 in 已见:
            continue
        已见.add(键)
        命中.append(项)
    if 命中:
        return 命中

    出: list[str] = []
    for 段 in _分界.split(文本):
        段 = _剥皮(段)
        if not 段:
            continue
        键 = 段.lower()
        if 键 in 已见:
            continue
        已见.add(键)
        出.append(段)
    return 出


def 构建批量文本(项们: list[str]) -> str:
    r"""
    将解析结果重建为每行一条, 便于多行框回填。
    :param 项们: 已解析条目
    :return: 多行文本
    """
    return "\n".join(项们)
