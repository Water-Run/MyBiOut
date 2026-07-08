r"""
ManualScript 手册页服务层, 负责手册展示和「What can I say about」AI 对话功能

:file: mybiout/pages/man/man.py
:author: WaterRun
:time: 2026-04-06
"""

import json as 数据交换
import random as 随机
import re as 正则
import subprocess as 子进程
import sys as 系统
import threading as 线程
import uuid as 唯一编号
from collections.abc import Generator as 生成器
from datetime import datetime as 日期时间
from pathlib import Path as 路径

import httpx as 网络请求

from mybiout.pages import utils as 工具

_程序工具目录: 路径 = 路径(__file__).resolve().parent.parent.parent / "bin"
_胡言数据路径: 路径 = _程序工具目录 / "BullshitGenerator" / "data.json"
_项目根目录: 路径 = 路径(__file__).resolve().parent.parent.parent

_子进程附加参数: dict[str, int] = {}
if 系统.platform == "win32":
    _子进程附加参数["creationflags"] = 0x08000000

_胡言缓存: dict = {}
_上下文缓存: str = ""
_上下文锁: 线程.Lock = 线程.Lock()
_日志列表: list[dict[str, str]] = []
_日志锁: 线程.Lock = 线程.Lock()
_主题占位正则: 正则.Pattern = 正则.compile(r"(?<![A-Za-z0-9_])x(?![A-Za-z0-9_])")
_空白正则: 正则.Pattern = 正则.compile(r"\s+")
_模块术语表: dict[str, list[str]] = {
    "LocalOut": [
        "缓存路径",
        "Android 缓存",
        "ADB 会话",
        "设备授权",
        "包名路径",
        "目录扫描",
        "文件探测",
        "m4s 分片",
        "音视频轨道",
        "FFmpeg 合并",
        "卡片选择",
        "导出目录",
        "本地缓存",
    ],
    "BBDown": [
        "视频链接",
        "登录态",
        "Cookie",
        "清晰度",
        "编码格式",
        "分P列表",
        "字幕轨道",
        "弹幕文件",
        "封面下载",
        "命令退出码",
    ],
    "MdOut": [
        "视频数据",
        "用户数据",
        "专栏文章",
        "Markdown 预览",
        "富文本渲染",
        "字段缺失",
        "文件命名",
        "批量导出",
    ],
    "OhMyConfig": [
        "config.ini",
        "导出根目录",
        "SESSDATA",
        "API Key",
        "模型名称",
        "Base URL",
        "超时设置",
        "明文凭证",
    ],
    "Man": [
        "运行时手册",
        "帮助对话",
        "项目上下文",
        "大模型配置",
        "流式响应",
        "降级路径",
        "Mamble 风格",
    ],
}
_模块动作表: dict[str, list[str]] = {
    "LocalOut": [
        "确认 Android 设备已经允许 ADB 调试",
        "把 PC 缓存、Android 缓存和自定义路径分开扫描",
        "检查缓存目录是否真实可读",
        "确认扫描出来的卡片已经加入导出任务",
        "核对 m4s 分片是否完整",
        "查看 FFmpeg 合并是否真正生成文件",
        "把导出目录里的最终文件作为成功证据",
    ],
    "BBDown": [
        "确认链接能被 BBDown 解析",
        "检查 Cookie 和登录态是否仍然有效",
        "把清晰度、编码、字幕和分P选项分开核对",
        "查看外部命令的退出码和标准错误",
    ],
    "MdOut": [
        "先确认接口返回了可导出的字段",
        "把预览渲染和磁盘导出分开验证",
        "检查文件名是否因为重复或过长被改写",
        "把批量导出的失败项单独复现",
    ],
    "OhMyConfig": [
        "先保存设置再确认下一次调用读取了新值",
        "把敏感字段明文保存的风险说清楚",
        "检查 Base URL、模型名称和 API Key 是否属于同一供应商",
        "把目录选择结果和配置文件内容逐项对齐",
    ],
    "Man": [
        "确认左侧手册和右侧回答都围绕运行时行为",
        "在大模型失败时明确说明已经进入降级路径",
        "把项目上下文是否获取成功写进判断链",
        "让 Mamble 风格服务于事实, 不替代事实",
    ],
}
_模块结构表: dict[str, list[str]] = {
    "LocalOut": [
        "设备连接 -> ADB 授权 -> 缓存路径 -> 卡片选择 -> FFmpeg 合并 -> 导出目录",
        "PC 缓存 -> Android 缓存 -> 自定义路径 -> 扫描结果 -> 导出任务",
        "路径可读 -> 分片完整 -> 任务入队 -> 最终文件出现",
    ],
    "BBDown": [
        "链接解析 -> 登录态 -> 画质编码 -> 分P选择 -> 命令退出码",
        "输入链接 -> 命令构建 -> 下载输出 -> 失败重试",
    ],
    "MdOut": [
        "数据获取 -> 字段校验 -> Markdown 预览 -> 文件写盘",
        "单项预览 -> 批量队列 -> 文件命名 -> 导出结果",
    ],
    "OhMyConfig": [
        "界面填写 -> 保存设置 -> config.ini -> 下一次读取",
        "Key -> Model -> Base URL -> 超时 -> 调用结果",
    ],
    "Man": [
        "用户问题 -> 项目上下文 -> 大模型调用 -> 降级说明",
        "左侧手册 -> 右侧对话 -> 流式输出 -> 日志记录",
    ],
}
_模块句子表: dict[str, list[str]] = {
    "LocalOut": [
        "如果 {主题} 涉及 Android 缓存, 就先看设备授权、包名路径和缓存目录是否真的被扫描到。",
        "LocalOut 的判断顺序应该是缓存路径可读、卡片可见、任务入队、FFmpeg 合并、导出目录出现文件。",
        "扫描不到内容时, PC 缓存、Android 缓存和自定义路径要分开测试, 不能混成一句路径不对。",
        "只要 m4s 分片不完整, 后面的导出提示再热闹也不能算成功。",
    ],
    "BBDown": [
        "BBDown 的问题要从链接解析、登录态、画质编码、分P选择和命令退出码逐项排。",
        "下载失败时, 先看外部命令标准错误, 再看 Cookie、清晰度和 API 模式。",
    ],
    "MdOut": [
        "MdOut 的问题要拆成数据获取、Markdown 预览、文件命名和导出写盘四层。",
        "预览正常不代表导出成功, 导出成功也不代表所有字段都被安全转义。",
    ],
    "OhMyConfig": [
        "OhMyConfig 的问题要从保存动作、config.ini 内容和下一次读取结果三处对齐。",
        "涉及 SESSDATA 或 API Key 时, 明文凭证风险必须直接说清楚。",
    ],
    "Man": [
        "Man 的问题要先看项目上下文是否拿到, 再看大模型配置是否能调用。",
        "如果进入狗屁不通生成器, 它必须像兜底一样工作, 不能冒充真正的大模型回答。",
    ],
}
_关键词术语表: dict[str, list[str]] = {
    "扫描": ["目录扫描", "文件探测", "设备授权", "ADB 会话", "缓存路径"],
    "缓存": ["缓存路径", "Android 缓存", "本地缓存", "m4s 分片", "文件探测"],
    "Android": ["Android 缓存", "ADB 会话", "设备授权", "包名路径", "权限边界"],
    "导出": ["导出目录", "任务队列", "FFmpeg 合并", "最终文件", "文件命名"],
    "下载": ["视频链接", "Cookie", "清晰度", "编码格式", "命令退出码"],
    "Markdown": ["Markdown 预览", "富文本渲染", "字段缺失", "批量导出"],
    "API": ["API Key", "Base URL", "模型名称", "状态码", "返回格式"],
}
_关键词动作表: dict[str, list[str]] = {
    "扫描": ["重新扫描前先确认路径可读", "把自动扫描和自定义路径分开验证", "查看扫描结果是否生成卡片"],
    "缓存": ["确认缓存文件是否仍在磁盘上", "检查缓存目录和权限", "核对 m4s 分片是否完整"],
    "Android": ["确认设备已经授权 ADB", "检查 Android 缓存路径和包名", "把设备连接状态写进判断链"],
    "导出": ["确认最终文件真实出现在导出目录", "检查 FFmpeg 合并结果", "把失败任务单独重试"],
    "下载": ["确认链接解析结果", "检查登录态和命令退出码", "把画质编码选项分开核对"],
    "Markdown": ["检查返回字段和预览渲染", "确认 Markdown 文件真实写盘", "把批量失败项单独复现"],
    "API": ["检查 Key、Model、Base URL 和超时", "查看状态码和返回字段", "确认供应商兼容格式"],
}
_模块禁用词表: dict[str, list[str]] = {
    "LocalOut": ["召回链路", "向量数据库", "嵌入模型", "重排序器", "提示词注入", "全表扫描"],
    "BBDown": ["向量数据库", "嵌入模型", "重排序器", "提示词注入"],
    "MdOut": ["ADB 会话", "设备授权", "m4s 分片"],
}


def _生成编号() -> str:
    return 唯一编号.uuid4().hex[:12]


def _短时间() -> str:
    return 日期时间.now().strftime("%H:%M:%S")


def _记录日志(等级: str, 消息: str) -> None:
    with _日志锁:
        _日志列表.append({"time": _短时间(), "level": 等级, "msg": 消息})
        if len(_日志列表) > 300:
            _日志列表[:] = _日志列表[-200:]


def _加载胡言材料() -> dict:
    global _胡言缓存
    if not _胡言缓存:
        try:
            _胡言缓存 = 数据交换.loads(_胡言数据路径.read_text(encoding="utf-8"))
        except Exception:
            _胡言缓存 = {}
    return _胡言缓存


def _取字符串列表(材料: dict, 名称: str, 默认值: list[str] | None = None) -> list[str]:
    值 = 材料.get(名称, [])
    if isinstance(值, list):
        结果 = [str(条目).strip() for 条目 in 值 if str(条目).strip()]
        if 结果:
            return 结果
    return list(默认值 or [])


def _随机选择(候选列表: list[str], 默认值: str) -> str:
    return 随机.choice(候选列表) if 候选列表 else 默认值


def _识别模块(主题: str) -> str:
    小写主题 = 主题.lower()
    for 模块名 in ["LocalOut", "BBDown", "MdOut", "OhMyConfig", "Man"]:
        if 模块名.lower() in 小写主题:
            return 模块名
    return "通用"


def _取模块提示(材料: dict, 主题: str) -> list[str]:
    提示表 = 材料.get("module_hints", {})
    if not isinstance(提示表, dict):
        return []
    模块名 = _识别模块(主题)
    模块提示 = 提示表.get(模块名, [])
    通用提示 = 提示表.get("通用", [])
    结果: list[str] = []
    for 提示列表 in [模块提示, 通用提示]:
        if isinstance(提示列表, list):
            结果.extend(str(条目).strip() for 条目 in 提示列表 if str(条目).strip())
    return 结果


def _合并唯一列表(*列表组: list[str]) -> list[str]:
    结果: list[str] = []
    已见: set[str] = set()
    for 列表 in 列表组:
        for 条目 in 列表:
            内容 = str(条目).strip()
            if 内容 and 内容 not in 已见:
                已见.add(内容)
                结果.append(内容)
    return 结果


def _构造抽样池(优先列表: list[str], 常规列表: list[str], 权重: int = 5) -> list[str]:
    优先唯一 = _合并唯一列表(优先列表)
    优先集合 = set(优先唯一)
    常规唯一 = [条目 for 条目 in _合并唯一列表(常规列表) if 条目 not in 优先集合]
    加权优先 = [条目 for 条目 in 优先唯一 for 重复编号 in range(max(1, 权重))]
    return 加权优先 + 常规唯一


def _命中关键词素材(主题: str, 素材表: dict[str, list[str]]) -> list[str]:
    小写主题 = 主题.lower()
    结果: list[str] = []
    for 关键词, 素材列表 in 素材表.items():
        if 关键词.lower() in 小写主题:
            结果.extend(素材列表)
    return 结果


def _过滤禁词(候选列表: list[str], 禁词列表: list[str]) -> list[str]:
    if not 禁词列表:
        return 候选列表
    return [条目 for 条目 in 候选列表 if not any(禁词 in 条目 for 禁词 in 禁词列表)]


def _取贴题素材(主题: str, 术语列表: list[str], 动作列表: list[str]) -> tuple[list[str], list[str]]:
    模块名 = _识别模块(主题)
    禁词列表 = _模块禁用词表.get(模块名, [])
    优先术语 = _过滤禁词(
        _合并唯一列表(_模块术语表.get(模块名, []), _命中关键词素材(主题, _关键词术语表)),
        禁词列表,
    )
    优先动作 = _合并唯一列表(_模块动作表.get(模块名, []), _命中关键词素材(主题, _关键词动作表))
    常规术语 = _过滤禁词(术语列表, 禁词列表)
    if 模块名 != "通用" and 优先术语:
        常规术语 = 优先术语
    elif 优先术语:
        常规术语 = _构造抽样池(优先术语, 常规术语, 8)
    if 模块名 != "通用" and 优先动作:
        动作列表 = 优先动作
    elif 优先动作:
        动作列表 = _构造抽样池(优先动作, 动作列表, 8)
    return 常规术语 or 术语列表, 动作列表


def _取贴题结构(主题: str, 结构表: list[str]) -> list[str]:
    模块名 = _识别模块(主题)
    模块结构 = _模块结构表.get(模块名, [])
    if 模块名 != "通用" and 模块结构:
        return 模块结构
    return 结构表


def _取贴题废话(主题: str, 废话素材: list[str]) -> list[str]:
    模块名 = _识别模块(主题)
    禁词列表 = _模块禁用词表.get(模块名, [])
    模块句子 = _模块句子表.get(模块名, [])
    if 模块名 != "通用" and 模块句子:
        模块术语 = _过滤禁词(
            _合并唯一列表(_模块术语表.get(模块名, []), _命中关键词素材(主题, _关键词术语表)),
            禁词列表,
        )
        模块动作 = _合并唯一列表(_模块动作表.get(模块名, []), _命中关键词素材(主题, _关键词动作表))
        组合句子 = [
            f"如果 {{主题}} 涉及{术语}, 那么先{模块动作[编号 % len(模块动作)]}, 再看页面是否给出清楚反馈。"
            for 编号, 术语 in enumerate(模块术语)
            if 模块动作
        ]
        return _合并唯一列表(模块句子, 组合句子)
    关键词列表 = _合并唯一列表(
        _模块术语表.get(模块名, []),
        _命中关键词素材(主题, _关键词术语表),
        [词语 for 词语 in 正则.findall(r"[A-Za-z0-9_\-]+|[\u4e00-\u9fff]{2,}", 主题) if len(词语) > 1],
    )
    可用素材 = _过滤禁词(废话素材, 禁词列表)
    贴题素材 = [
        句子
        for 句子 in 可用素材
        if any(关键词 in 句子 for 关键词 in 关键词列表)
    ]
    return _合并唯一列表(贴题素材, 可用素材)


def _整理句子(文本: str) -> str:
    文本 = _空白正则.sub(" ", str(文本).strip())
    文本 = 文本.replace(" ,", "，").replace(", ", "，").replace(",", "，")
    文本 = 文本.replace(": ", "：").replace(":", "：")
    文本 = 正则.sub(r"([\u4e00-\u9fff])([A-Za-z0-9][A-Za-z0-9.+#_\-]*)", r"\1 \2", 文本)
    文本 = 正则.sub(r"([A-Za-z0-9][A-Za-z0-9.+#_\-]*)([\u4e00-\u9fff])", r"\1 \2", 文本)
    文本 = 正则.sub(r"([\u4e00-\u9fff])\s+([\u4e00-\u9fff])", r"\1\2", 文本)
    文本 = 正则.sub(r"\.\s*$", "。", 文本)
    文本 = 正则.sub(r"\s+([。！？])", r"\1", 文本)
    文本 = 正则.sub(r"[。！？]{2,}", lambda 匹配: 匹配.group(0)[0], 文本)
    if 文本 and 文本[-1] not in "。！？":
        文本 += "。"
    return 文本


def _句子指纹(文本: str) -> str:
    return 正则.sub(r"\s+", "", 文本)


def _填充模板(
    模板: str,
    主题: str,
    角色: str,
    术语: str,
    动作: str,
    前缀: str,
    后缀: str,
) -> str:
    结果 = str(模板)
    替换表 = {
        "{主题}": 主题,
        "{角色}": 角色,
        "{术语}": 术语,
        "{动作}": 动作,
        "{前缀}": 前缀,
        "{后缀}": 后缀,
    }
    for 标记, 内容 in 替换表.items():
        结果 = 结果.replace(标记, 内容)

    结果 = _主题占位正则.sub(主题, 结果)
    结果 = 结果.replace(" a,", f" {前缀},")
    结果 = 结果.replace(" a，", f" {前缀}，")
    结果 = 结果.replace(" a ", f" {前缀} ")
    结果 = 正则.sub(r"。b(?=$|\s)", f"。{后缀}", 结果)
    结果 = 正则.sub(r" b(?=$|\s)", f" {后缀}", 结果)
    return _整理句子(结果)


def _生成一句(
    候选模板: list[str],
    主题: str,
    角色列表: list[str],
    术语列表: list[str],
    动作列表: list[str],
    前缀表: list[str],
    后缀表: list[str],
    已用句子: set[str],
    固定角色: str | None = None,
) -> str:
    默认角色 = 固定角色 or "GPT-5"
    if 固定角色 and 固定角色 not in 角色列表 and 角色列表:
        默认角色 = _随机选择(角色列表, "GPT-5")
    for _ in range(40):
        角色 = 固定角色 or _随机选择(角色列表, 默认角色)
        术语 = _随机选择(术语列表, "上下文窗口")
        动作 = _随机选择(动作列表, "把问题拆成可复现步骤")
        前缀 = _随机选择(前缀表, "曾经说过")
        后缀 = _随机选择(后缀表, "这不禁令我深思")
        模板 = _随机选择(候选模板, "{角色}认为, {主题}需要先看{术语}, 再{动作}。")
        句子 = _填充模板(模板, 主题, 角色, 术语, 动作, 前缀, 后缀)
        指纹 = _句子指纹(句子)
        if len(句子) > 8 and 指纹 not in 已用句子:
            已用句子.add(指纹)
            return 句子
    兜底句 = _整理句子(
        f"{默认角色}认为，{主题}至少要围绕{_随机选择(术语列表, '上下文窗口')}重新检查，"
        f"然后{_随机选择(动作列表, '把问题拆成可复现步骤')}。"
    )
    已用句子.add(_句子指纹(兜底句))
    return 兜底句


def 生成胡言(主题: str, 目标长度: int = 600) -> str:
    材料: dict = _加载胡言材料()
    if not 材料:
        return f"关于「{主题}」, 我实在是无话可说。（BullshitGenerator 数据加载失败）"
    主题 = (主题 or "这个问题").strip() or "这个问题"
    目标长度 = max(260, int(目标长度 or 600))

    名人名言 = _取字符串列表(材料, "famous")
    废话素材 = _取字符串列表(材料, "bosh")
    角色列表 = _取字符串列表(
        材料,
        "speakers",
        ["GPT-5", "Claude", "DeepSeek", "Mimo", "LongCat", "乔布斯", "图灵", "Python"],
    )
    术语列表 = _取字符串列表(材料, "technical_terms", ["上下文窗口", "日志", "配置文件", "导出目录"])
    动作列表 = _取字符串列表(材料, "actions", ["把问题拆成可复现步骤", "检查配置和日志"])
    术语列表, 动作列表 = _取贴题素材(主题, 术语列表, 动作列表)
    废话素材 = _取贴题废话(主题, 废话素材)
    开场表 = _取字符串列表(材料, "openings", [f"首先, {主题}必须被拆成能复现的步骤。"])
    转折表 = _取字符串列表(材料, "transitions", ["其次, {角色}会先检查{术语}, 然后{动作}。"])
    推理表 = _取字符串列表(材料, "reasoning", ["进一步说, {主题}如果缺少{术语}, 判断就会变得很飘。"])
    结构表 = _取字符串列表(材料, "structures", ["现象判断 -> 证据核验 -> 操作步骤 -> 失败兜底"])
    结构表 = _取贴题结构(主题, 结构表)
    后缀表 = _取字符串列表(材料, "after", ["这不禁令我深思。"])
    前缀表 = _取字符串列表(材料, "before", ["曾经说过"])
    模块提示 = _取模块提示(材料, 主题)
    核心角色候选 = [
        角色
        for 角色 in ["GPT-5", "Claude 4 Sonnet", "DeepSeek-R1", "Mimo", "LongCat", "乔布斯", "图灵", "Python"]
        if 角色 in 角色列表
    ]
    核心角色 = _随机选择(核心角色候选 or 角色列表, "GPT-5")
    已用句子: set[str] = set()
    文章段落: list[str] = []
    模块名 = _识别模块(主题)
    角色观点表 = [
        "{角色} 看完 {主题} 后不会先讲玄学, 它会先盯住{术语}, 然后{动作}。",
        "让 {角色} 来复盘 {主题}, 它也得先承认{术语}才是证据, {动作}才是动作。",
        "{角色} 的名字可以很响, 但处理 {主题} 时仍然要回到{术语}和用户可见结果。",
        "如果 {角色} 真要参与 {主题}, 最合理的姿势不是背书, 而是{动作}。",
    ]
    名言扩展表 = 名人名言 if 模块名 == "通用" else 角色观点表

    骨架段落 = [
        [
            "首先, {主题}不是一句万能废话能解决的事, 它需要被拆成现象、证据和动作。",
            *(模块提示[:1] or 开场表[:1]),
            "{角色} {前缀}, 真正的帮助不是把话说长, 而是把失败路径说准。{后缀}",
        ],
        [
            "其次, {角色}会把{术语}放在桌面中央, 因为它决定了{主题}到底有没有证据。",
            *(模块提示[1:2] or 转折表[:1]),
            *_随机选择([废话素材[:1], 推理表[:1]], 推理表[:1]),
        ],
        [
            "进一步说, {主题}如果绕开{术语}, 后面的判断就会像没有路径的目录扫描。",
            "{角色}看见这种场面, 也只能先要求{动作}, 再谈所谓智能化。",
            *(废话素材[1:2] or 推理表[:1]),
        ],
        [
            "最后, {主题}的收束点不是更会说, 而是让{术语}和界面反馈同时变得诚实。",
            "处理时可以按「{术语} -> {动作} -> 用户可见反馈」推进, 不要把所有问题揉成一团。",
            "{角色} 的名字可以很响, 但 {主题} 的结论必须落到{术语}和{动作}上。",
        ],
    ]

    for 段落模板 in 骨架段落:
        句子列表 = [
            _生成一句(
                [段落项],
                主题,
                角色列表,
                术语列表,
                动作列表,
                前缀表,
                后缀表,
                已用句子,
                核心角色,
            )
            for 段落项 in 段落模板
        ]
        文章段落.append("　　" + "".join(句子列表))

    扩展来源 = [
        转折表 + 推理表,
        废话素材 + 名言扩展表,
        [f"换句话说, {{主题}}可以按「{_随机选择(结构表, '现象判断 -> 证据核验 -> 操作步骤 -> 失败兜底')}」推进。"],
        角色观点表 + 废话素材,
    ]
    结果 = "\n\n".join(文章段落)
    while len(结果) < 目标长度:
        句子列表 = [
            _生成一句(
                _随机选择(扩展来源, 推理表),
                主题,
                角色列表,
                术语列表,
                动作列表,
                前缀表,
                后缀表,
                已用句子,
            )
            for _ in range(3)
        ]
        文章段落.insert(-1, "　　" + "".join(句子列表))
        结果 = "\n\n".join(文章段落)
    return 结果


def _取项目上下文() -> str:
    global _上下文缓存
    with _上下文锁:
        if _上下文缓存:
            return _上下文缓存
    try:
        执行结果: 子进程.CompletedProcess = 子进程.run(
            ["pmc", str(_项目根目录)],
            capture_output=True,
            text=True,
            timeout=60,
            encoding="utf-8",
            errors="replace",
            **_子进程附加参数,
        )
        if 执行结果.returncode == 0 and 执行结果.stdout.strip():
            上下文: str = 执行结果.stdout.strip()
            with _上下文锁:
                _上下文缓存 = 上下文
            _记录日志("info", f"pmc 打包成功 ({len(上下文)} 字符)")
            return 上下文
    except FileNotFoundError:
        _记录日志("warn", "pmc 未安装, 无法打包项目代码")
    except 子进程.TimeoutExpired:
        _记录日志("warn", "pmc 执行超时")
    except Exception as e:
        _记录日志("warn", f"pmc 执行异常: {e}")
    return ""


def _构建对话地址(接口基地址: str) -> str:
    基地址: str = (接口基地址 or "https://api.poe.com/v1").strip().rstrip("/")
    if 基地址.endswith("/chat/completions"):
        return 基地址
    if not 基地址.endswith("/v1"):
        基地址 += "/v1"
    return f"{基地址}/chat/completions"


def _构建风格提示() -> str:
    return (
        "【身份与风格】\n"
        "你是 MyBiOut! 的运行时帮助助手, 面向已经打开网页界面的用户, 不讲安装教程。\n"
        "必须使用 Mamble/Mamba 风格: 中文回答, 语气像热血但靠谱的技术老大哥, 自然使用 Man!、What can I say、孩子们、牢大、凌晨四点、曼巴精神、Mamba Out 等项目梗。\n"
        "风格是外壳, 准确性是核心: 不要为了玩梗牺牲步骤、条件、风险说明和错误处理。\n"
        "不要提及任何真实人物姓名, 不要虚构项目没有的按钮、接口或功能。\n"
    )


def _构建产品提示() -> str:
    return (
        "【系统功能地图】\n"
        "1. 首页: 进入 LocalOut、BBDown、MdOut、OhMyConfig 和 Man 页面。\n"
        "2. OhMyConfig: 管理导出根目录、B站 SESSDATA、OpenAI 兼容大模型 API、LocalOut/BBDown/MdOut 各自的目录与行为选项。敏感信息会明文保存在 config.ini, 回答时必须提醒风险。\n"
        "3. LocalOut: 导出已存在的 B 站缓存。支持 PC 桌面端缓存、Android ADB 扫描、自定义本地缓存路径; 扫描后选择卡片、加入任务、导出; 依赖 FFmpeg/biliffm4s 合并 m4s。\n"
        "4. BBDown: 对 BBDown 命令行下载能力做网页封装。可输入 BV/av/ep/ss、完整链接或 b23 短链; 支持画质、编码、API 模式、分P、字幕、弹幕、封面等设置; 任务可取消、重试、清空。\n"
        "5. MdOut: 将视频、用户、专栏文章导出为 Markdown。可预览 Rich/Raw, 可导出单项、批量导出、打开导出目录。\n"
        "6. Man: 左侧是手册, 右侧是大模型助手。大模型配置缺失或调用失败时, 会降级为计算机主题的狗屁不通文章生成器。\n"
    )


def _构建响应提示() -> str:
    return (
        "【回答协议】\n"
        "1. 先判断用户在问哪个模块或哪个常见情况, 直接给可执行步骤。\n"
        "2. 如果是排错, 按「现象判断 -> 需要检查的设置/状态 -> 操作步骤 -> 仍失败怎么办」组织。\n"
        "3. 如果涉及大模型配置, 明确说明 Key、Model、Base URL、超时的作用; Base URL 应是 OpenAI 兼容入口, 可接受 /v1 或 /chat/completions 结尾。\n"
        "4. 如果信息不足, 先说明你缺少什么信息, 再给用户现在就能做的检查项; 不要空泛地说重新安装。\n"
        "5. 如果上下文和用户问题冲突, 以项目上下文为准; 如果上下文没有覆盖, 标明这是基于界面行为的推断。\n"
        "6. 输出应详尽但可读, 优先使用短段落和项目内按钮/字段名。结尾自然带 Mamba Out, 但不要影响技术内容。\n"
    )


def _构建上下文提示(上下文: str) -> str:
    return (
        "【项目上下文】\n"
        "以下是通过 pmc 工具动态打包的项目源代码。回答必须优先依据这些内容:\n\n"
        + (上下文 if 上下文 else "(项目代码未能获取, 只能依据页面已知行为回答; 如需精确代码级判断, 提醒用户检查 pmc 是否可用。)")
    )


def _构建消息(提示词: str, 上下文: str) -> list[dict[str, str]]:
    系统内容: str = "\n\n".join(
        [
            _构建风格提示(),
            _构建产品提示(),
            _构建响应提示(),
            _构建上下文提示(上下文),
            f"【本轮问题】\n用户正在询问: {提示词}\n生成回答时必须把这个问题作为中心, 不要泛泛复述手册。",
        ]
    )
    return [
        {"role": "system", "content": 系统内容},
        {"role": "user", "content": 提示词},
    ]


def _调用大模型(提示词: str, 上下文: str) -> str:
    接口密钥: str = 工具.取接口密钥()
    模型: str = 工具.取接口模型() or "gpt-5.3-codex"
    if not 接口密钥:
        raise RuntimeError("未配置 API Key")

    消息列表: list[dict[str, str]] = _构建消息(提示词, 上下文)
    请求头: dict[str, str] = {
        "Authorization": f"Bearer {接口密钥}",
        "Content-Type": "application/json",
    }
    接口基地址: str = 工具.取接口基地址()
    对话地址: str = _构建对话地址(接口基地址)
    超时秒数: float | None = 工具.取接口超时秒数()

    with 网络请求.Client(timeout=超时秒数) as 客户端:
        响应: 网络请求.Response = 客户端.post(
            对话地址,
            headers=请求头,
            json={"model": 模型, "messages": 消息列表},
        )
        响应.raise_for_status()
        数据: dict = 响应.json()

    # OpenAI chat completions 格式
    选项列表: list = 数据.get("choices", [])
    if 选项列表:
        return 选项列表[0].get("message", {}).get("content", "")

    # Poe responses 格式兼容
    if "output_text" in 数据:
        return 数据["output_text"]
    if "output" in 数据:
        输出内容 = 数据["output"]
        if isinstance(输出内容, list):
            for 条目 in 输出内容:
                if isinstance(条目, dict) and 条目.get("type") == "message":
                    return 条目.get("content", [{}])[0].get("text", "")
        if isinstance(输出内容, str):
            return 输出内容

    return 数据.get("text", str(数据))


def _流式调用大模型(提示词: str, 上下文: str) -> 生成器[str]:
    r"""
    流式调用 LLM, 逐块 yield 内容文本
    """
    接口密钥: str = 工具.取接口密钥()
    模型: str = 工具.取接口模型() or "gpt-5.3-codex"
    if not 接口密钥:
        raise RuntimeError("未配置 API Key")

    消息列表: list[dict[str, str]] = _构建消息(提示词, 上下文)
    请求头: dict[str, str] = {
        "Authorization": f"Bearer {接口密钥}",
        "Content-Type": "application/json",
    }
    接口基地址: str = 工具.取接口基地址()
    对话地址: str = _构建对话地址(接口基地址)
    超时秒数: float | None = 工具.取接口超时秒数()

    with (
        网络请求.Client(timeout=超时秒数) as 客户端,
        客户端.stream(
            "POST",
            对话地址,
            headers=请求头,
            json={"model": 模型, "messages": 消息列表, "stream": True},
        ) as 响应,
    ):
        响应.raise_for_status()
        for 行 in 响应.iter_lines():
            if not 行 or not 行.startswith("data: "):
                continue
            数据文本: str = 行[6:].strip()
            if 数据文本 == "[DONE]":
                break
            try:
                数据块: dict = 数据交换.loads(数据文本)
                增量: dict = 数据块.get("choices", [{}])[0].get("delta", {})
                内容: str = 增量.get("content", "")
                if 内容:
                    yield 内容
            except (数据交换.JSONDecodeError, IndexError, KeyError):
                continue


def 流式对话SSE(提示词: str) -> 生成器[str]:
    r"""
    SSE 格式的流式对话, 供 FastAPI StreamingResponse 使用
    """
    提示词 = 提示词.strip()
    if not 提示词:
        yield f"data: {数据交换.dumps({'error': '请输入问题'})}\n\n"
        return

    _记录日志("info", f"收到流式提问: {提示词[:50]}{'...' if len(提示词) > 50 else ''}")

    接口密钥: str = 工具.取接口密钥()
    if not 接口密钥:
        _记录日志("warn", "未配置 API Key, 降级为狗屁不通文章生成器")
        回复: str = 生成胡言(提示词)
        yield f"data: {数据交换.dumps({'content': 回复, 'source': 'bullshit', 'done': True, 'note': '未配置 API Key'})}\n\n"
        return

    try:
        _记录日志("info", "正在获取项目代码上下文...")
        上下文: str = _取项目上下文()
        _记录日志("info", f"正在流式调用大模型 ({工具.取接口模型() or 'gpt-5.3-codex'})...")

        yield f"data: {数据交换.dumps({'status': 'streaming', 'source': 'llm'})}\n\n"

        for 数据块 in _流式调用大模型(提示词, 上下文):
            yield f"data: {数据交换.dumps({'content': 数据块})}\n\n"

        yield f"data: {数据交换.dumps({'done': True, 'source': 'llm'})}\n\n"
        _记录日志("success", "大模型流式回复完成")

    except Exception as e:
        _记录日志("error", f"大模型调用失败: {e}, 降级为狗屁不通文章生成器")
        回复 = 生成胡言(提示词)
        yield f"data: {数据交换.dumps({'content': 回复, 'source': 'bullshit', 'done': True, 'note': f'API 调用失败 ({e})'})}\n\n"


def 对话(提示词: str, 直接说: bool = False) -> dict:
    提示词 = 提示词.strip()
    if not 提示词:
        return {"ok": False, "error": "请输入问题"}

    _记录日志("info", f"收到提问: {提示词[:50]}{'...' if len(提示词) > 50 else ''}")

    if 直接说:
        _记录日志("info", "直接说模式 → 狗屁不通文章生成器")
        回复: str = 生成胡言(提示词)
        return {"ok": True, "reply": 回复, "source": "bullshit", "note": "「直接说」模式"}

    接口密钥: str = 工具.取接口密钥()
    if not 接口密钥:
        _记录日志("warn", "未配置 API Key, 降级为狗屁不通文章生成器")
        回复 = 生成胡言(提示词)
        return {
            "ok": True,
            "reply": 回复,
            "source": "bullshit",
            "note": "未配置 API Key, 已使用狗屁不通文章生成器代替",
        }

    try:
        _记录日志("info", "正在获取项目代码上下文...")
        上下文: str = _取项目上下文()
        _记录日志("info", f"正在调用大模型 ({工具.取接口模型() or 'gpt-5.3-codex'})...")
        回复 = _调用大模型(提示词, 上下文)
        _记录日志("success", "大模型回复成功")
        return {"ok": True, "reply": 回复, "source": "llm"}
    except Exception as e:
        _记录日志("error", f"大模型调用失败: {e}, 降级为狗屁不通文章生成器")
        回复 = 生成胡言(提示词)
        return {
            "ok": True,
            "reply": 回复,
            "source": "bullshit",
            "note": f"API 调用失败 ({e}), 已使用狗屁不通文章生成器代替",
        }


def 取日志() -> list[dict[str, str]]:
    with _日志锁:
        return list(_日志列表)
