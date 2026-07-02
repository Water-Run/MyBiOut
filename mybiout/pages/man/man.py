r"""
ManualScript 手册页服务层, 负责手册展示和「What can I say about」AI 对话功能

:file: mybiout/pages/man/man.py
:author: WaterRun
:time: 2026-04-06
"""

import json as 数据交换
import random as 随机
import subprocess as 子进程
import sys as 系统
import threading as 线程
import uuid as 唯一编号
from collections.abc import Generator as 生成器
from datetime import datetime as 日期时间
from pathlib import Path as 路径

import httpx as 网络请求

from mybiout.pages import utils as 工具

_BIN_DIR: 路径 = 路径(__file__).resolve().parent.parent.parent / "bin"
_BS_DATA_PATH: 路径 = _BIN_DIR / "BullshitGenerator" / "data.json"
_PROJECT_ROOT: 路径 = 路径(__file__).resolve().parent.parent.parent.parent

_POPEN_EXTRA: dict[str, int] = {}
if 系统.platform == "win32":
    _POPEN_EXTRA["creationflags"] = 0x08000000

_bs_cache: dict = {}
_context_cache: str = ""
_context_lock: 线程.Lock = 线程.Lock()
_logs: list[dict[str, str]] = []
_logs_lock: 线程.Lock = 线程.Lock()


def _生成编号() -> str:
    return 唯一编号.uuid4().hex[:12]


def _短时间() -> str:
    return 日期时间.now().strftime("%H:%M:%S")


def _记录日志(level: str, msg: str) -> None:
    with _logs_lock:
        _logs.append({"time": _短时间(), "level": level, "msg": msg})
        if len(_logs) > 300:
            _logs[:] = _logs[-200:]


def _加载胡言材料() -> dict:
    global _bs_cache
    if not _bs_cache:
        try:
            _bs_cache = 数据交换.loads(_BS_DATA_PATH.read_text(encoding="utf-8"))
        except Exception:
            _bs_cache = {}
    return _bs_cache


def 生成胡言(topic: str, target_length: int = 600) -> str:
    data: dict = _加载胡言材料()
    if not data:
        return f"关于「{topic}」, 我实在是无话可说。（BullshitGenerator 数据加载失败）"
    famous: list[str] = data.get("famous", [])
    bosh: list[str] = data.get("bosh", [])
    after_list: list[str] = data.get("after", [])
    before_list: list[str] = data.get("before", [])
    article: list[str] = []
    section: str = ""
    section_len: int = 0
    while section_len < target_length:
        r: float = 随机.random() * 100
        if r < 5 and len(section) > 150:
            if section and section[-1] == " ":
                section = section[:-2]
            article.append("　　" + section + "。")
            section = ""
        elif r < 20 and famous:
            quote: str = 随机.choice(famous)
            if before_list:
                quote = quote.replace("a", 随机.choice(before_list))
            if after_list:
                quote = quote.replace("b", 随机.choice(after_list))
            section += quote
            section_len += len(quote)
        elif bosh:
            sentence: str = 随机.choice(bosh).replace("x", topic)
            section += sentence
            section_len += len(sentence)
        else:
            filler: str = f"{topic}确实很重要。"
            section += filler
            section_len += len(filler)
    if section:
        if section and section[-1] == " ":
            section = section[:-2]
        article.append("　　" + section + "。")
    return "\n\n".join(article)


def _取项目上下文() -> str:
    global _context_cache
    with _context_lock:
        if _context_cache:
            return _context_cache
    try:
        result: 子进程.CompletedProcess = 子进程.run(
            ["pmc", str(_PROJECT_ROOT)],
            capture_output=True,
            text=True,
            timeout=60,
            encoding="utf-8",
            errors="replace",
            **_POPEN_EXTRA,
        )
        if result.returncode == 0 and result.stdout.strip():
            ctx: str = result.stdout.strip()
            with _context_lock:
                _context_cache = ctx
            _记录日志("info", f"pmc 打包成功 ({len(ctx)} 字符)")
            return ctx
    except FileNotFoundError:
        _记录日志("warn", "pmc 未安装, 无法打包项目代码")
    except 子进程.TimeoutExpired:
        _记录日志("warn", "pmc 执行超时")
    except Exception as e:
        _记录日志("warn", f"pmc 执行异常: {e}")
    return ""


def _构建对话地址(base_url: str) -> str:
    b: str = (base_url or "https://api.poe.com/v1").strip().rstrip("/")
    if b.endswith("/chat/completions"):
        return b
    if not b.endswith("/v1"):
        b += "/v1"
    return f"{b}/chat/completions"


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


def _构建上下文提示(context: str) -> str:
    return (
        "【项目上下文】\n"
        "以下是通过 pmc 工具动态打包的项目源代码。回答必须优先依据这些内容:\n\n"
        + (context if context else "(项目代码未能获取, 只能依据页面已知行为回答; 如需精确代码级判断, 提醒用户检查 pmc 是否可用。)")
    )


def _构建消息(prompt: str, context: str) -> list[dict[str, str]]:
    system_content: str = "\n\n".join(
        [
            _构建风格提示(),
            _构建产品提示(),
            _构建响应提示(),
            _构建上下文提示(context),
            f"【本轮问题】\n用户正在询问: {prompt}\n生成回答时必须把这个问题作为中心, 不要泛泛复述手册。",
        ]
    )
    return [
        {"role": "system", "content": system_content},
        {"role": "user", "content": prompt},
    ]


def _调用大模型(prompt: str, context: str) -> str:
    api_key: str = 工具.取接口密钥()
    model: str = 工具.取接口模型() or "gpt-5.3-codex"
    if not api_key:
        raise RuntimeError("未配置 API Key")

    messages: list[dict[str, str]] = _构建消息(prompt, context)
    headers: dict[str, str] = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    base_url: str = 工具.取接口基地址()
    chat_url: str = _构建对话地址(base_url)
    timeout_seconds: float | None = 工具.取接口超时秒数()

    with 网络请求.Client(timeout=timeout_seconds) as client:
        r: 网络请求.Response = client.post(
            chat_url,
            headers=headers,
            数据交换={"model": model, "messages": messages},
        )
        r.raise_for_status()
        data: dict = r.json()

    # OpenAI chat completions 格式
    choices: list = data.get("choices", [])
    if choices:
        return choices[0].get("message", {}).get("content", "")

    # Poe responses 格式兼容
    if "output_text" in data:
        return data["output_text"]
    if "output" in data:
        out = data["output"]
        if isinstance(out, list):
            for item in out:
                if isinstance(item, dict) and item.get("type") == "message":
                    return item.get("content", [{}])[0].get("text", "")
        if isinstance(out, str):
            return out

    return data.get("text", str(data))


def _流式调用大模型(prompt: str, context: str) -> 生成器[str]:
    r"""
    流式调用 LLM, 逐块 yield 内容文本
    """
    api_key: str = 工具.取接口密钥()
    model: str = 工具.取接口模型() or "gpt-5.3-codex"
    if not api_key:
        raise RuntimeError("未配置 API Key")

    messages: list[dict[str, str]] = _构建消息(prompt, context)
    headers: dict[str, str] = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    base_url: str = 工具.取接口基地址()
    chat_url: str = _构建对话地址(base_url)
    timeout_seconds: float | None = 工具.取接口超时秒数()

    with (
        网络请求.Client(timeout=timeout_seconds) as client,
        client.stream(
            "POST",
            chat_url,
            headers=headers,
            数据交换={"model": model, "messages": messages, "stream": True},
        ) as response,
    ):
        response.raise_for_status()
        for line in response.iter_lines():
            if not line or not line.startswith("data: "):
                continue
            data_str: str = line[6:].strip()
            if data_str == "[DONE]":
                break
            try:
                chunk: dict = 数据交换.loads(data_str)
                delta: dict = chunk.get("choices", [{}])[0].get("delta", {})
                content: str = delta.get("content", "")
                if content:
                    yield content
            except 数据交换.JSONDecodeError, IndexError, KeyError:
                continue


def 流式对话SSE(prompt: str) -> 生成器[str]:
    r"""
    SSE 格式的流式对话, 供 FastAPI StreamingResponse 使用
    """
    prompt = prompt.strip()
    if not prompt:
        yield f"data: {数据交换.dumps({'error': '请输入问题'})}\n\n"
        return

    _记录日志("info", f"收到流式提问: {prompt[:50]}{'...' if len(prompt) > 50 else ''}")

    api_key: str = 工具.取接口密钥()
    if not api_key:
        _记录日志("warn", "未配置 API Key, 降级为狗屁不通文章生成器")
        reply: str = 生成胡言(prompt)
        yield f"data: {数据交换.dumps({'content': reply, 'source': 'bullshit', 'done': True, 'note': '未配置 API Key'})}\n\n"
        return

    try:
        _记录日志("info", "正在获取项目代码上下文...")
        context: str = _取项目上下文()
        _记录日志("info", f"正在流式调用大模型 ({工具.取接口模型() or 'gpt-5.3-codex'})...")

        yield f"data: {数据交换.dumps({'status': 'streaming', 'source': 'llm'})}\n\n"

        for chunk in _流式调用大模型(prompt, context):
            yield f"data: {数据交换.dumps({'content': chunk})}\n\n"

        yield f"data: {数据交换.dumps({'done': True, 'source': 'llm'})}\n\n"
        _记录日志("success", "大模型流式回复完成")

    except Exception as e:
        _记录日志("error", f"大模型调用失败: {e}, 降级为狗屁不通文章生成器")
        reply = 生成胡言(prompt)
        yield f"data: {数据交换.dumps({'content': reply, 'source': 'bullshit', 'done': True, 'note': f'API 调用失败 ({e})'})}\n\n"


def 对话(prompt: str, force_bs: bool = False) -> dict:
    prompt = prompt.strip()
    if not prompt:
        return {"ok": False, "error": "请输入问题"}

    _记录日志("info", f"收到提问: {prompt[:50]}{'...' if len(prompt) > 50 else ''}")

    if force_bs:
        _记录日志("info", "直接说模式 → 狗屁不通文章生成器")
        reply: str = 生成胡言(prompt)
        return {"ok": True, "reply": reply, "source": "bullshit", "note": "「直接说」模式"}

    api_key: str = 工具.取接口密钥()
    if not api_key:
        _记录日志("warn", "未配置 API Key, 降级为狗屁不通文章生成器")
        reply = 生成胡言(prompt)
        return {
            "ok": True,
            "reply": reply,
            "source": "bullshit",
            "note": "未配置 API Key, 已使用狗屁不通文章生成器代替",
        }

    try:
        _记录日志("info", "正在获取项目代码上下文...")
        context: str = _取项目上下文()
        _记录日志("info", f"正在调用大模型 ({工具.取接口模型() or 'gpt-5.3-codex'})...")
        reply = _调用大模型(prompt, context)
        _记录日志("success", "大模型回复成功")
        return {"ok": True, "reply": reply, "source": "llm"}
    except Exception as e:
        _记录日志("error", f"大模型调用失败: {e}, 降级为狗屁不通文章生成器")
        reply = 生成胡言(prompt)
        return {
            "ok": True,
            "reply": reply,
            "source": "bullshit",
            "note": f"API 调用失败 ({e}), 已使用狗屁不通文章生成器代替",
        }


def 取日志() -> list[dict[str, str]]:
    with _logs_lock:
        return list(_logs)


_uid = _生成编号
_ts = _短时间
_log = _记录日志
_load_bs_data = _加载胡言材料
bullshit_generate = 生成胡言
_get_project_context = _取项目上下文
_build_chat_url = _构建对话地址
_build_style_prompt = _构建风格提示
_build_product_prompt = _构建产品提示
_build_response_prompt = _构建响应提示
_build_context_prompt = _构建上下文提示
_build_messages = _构建消息
_call_llm = _调用大模型
_stream_llm = _流式调用大模型
chat_stream_sse = 流式对话SSE
chat = 对话
get_logs = 取日志
