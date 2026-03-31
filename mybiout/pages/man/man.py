r"""
ManualScript 手册页服务层, 负责手册展示和「What can I say about」AI 对话功能

:file: mybiout/pages/man/man.py
:author: WaterRun
:time: 2026-03-31
"""

import json
import random
import subprocess
import sys
import threading
import uuid
from datetime import datetime
from pathlib import Path

import httpx

from mybiout.pages import utils

_BIN_DIR: Path = Path(__file__).resolve().parent.parent.parent / "bin"
_BS_DATA_PATH: Path = _BIN_DIR / "BullshitGenerator" / "data.json"
_PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent.parent.parent

_POPEN_EXTRA: dict[str, int] = {}
if sys.platform == "win32":
    _POPEN_EXTRA["creationflags"] = 0x08000000

_bs_cache: dict = {}
_context_cache: str = ""
_context_lock: threading.Lock = threading.Lock()
_logs: list[dict[str, str]] = []
_logs_lock: threading.Lock = threading.Lock()


def _uid() -> str:
    r"""
    生成 12 位唯一标识
    :return: str: UUID 前 12 位
    """
    return uuid.uuid4().hex[:12]


def _ts() -> str:
    r"""
    获取当前时间短格式
    :return: str: HH:MM:SS
    """
    return datetime.now().strftime("%H:%M:%S")


def _log(level: str, msg: str) -> None:
    r"""
    记录手册页日志
    :param: level: 日志级别
    :param: msg: 日志消息
    """
    with _logs_lock:
        _logs.append({"time": _ts(), "level": level, "msg": msg})
        if len(_logs) > 300:
            _logs[:] = _logs[-200:]


def _load_bs_data() -> dict:
    r"""
    加载狗屁不通文章生成器数据
    :return: dict: 生成器数据字典
    """
    global _bs_cache
    if not _bs_cache:
        try:
            _bs_cache = json.loads(_BS_DATA_PATH.read_text(encoding="utf-8"))
        except Exception:
            _bs_cache = {}
    return _bs_cache


def bullshit_generate(topic: str, target_length: int = 600) -> str:
    r"""
    使用狗屁不通文章生成器根据主题生成文本
    :param: topic: 主题
    :param: target_length: 目标字符长度
    :return: str: 生成的文本
    """
    data: dict = _load_bs_data()
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
        r: float = random.random() * 100
        if r < 5 and len(section) > 150:
            if section and section[-1] == " ":
                section = section[:-2]
            article.append("　　" + section + "。")
            section = ""
        elif r < 20 and famous:
            quote: str = random.choice(famous)
            if before_list:
                quote = quote.replace("a", random.choice(before_list))
            if after_list:
                quote = quote.replace("b", random.choice(after_list))
            section += quote
            section_len += len(quote)
        elif bosh:
            sentence: str = random.choice(bosh).replace("x", topic)
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


def _get_project_context() -> str:
    r"""
    调用 pmc 工具打包项目源代码作为上下文
    :return: str: 项目代码文本, 获取失败返回空字符串
    """
    global _context_cache
    with _context_lock:
        if _context_cache:
            return _context_cache

    try:
        result: subprocess.CompletedProcess = subprocess.run(
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
            _log("info", f"pmc 打包成功 ({len(ctx)} 字符)")
            return ctx
    except FileNotFoundError:
        _log("warn", "pmc 未安装, 无法打包项目代码")
    except subprocess.TimeoutExpired:
        _log("warn", "pmc 执行超时")
    except Exception as e:
        _log("warn", f"pmc 执行异常: {e}")
    return ""

def _build_chat_url(base_url: str) -> str:
    r"""
    规范化并构造 chat completions URL
    :param: base_url: 配置的 API 地址
    :return: str: 完整 chat completions 地址
    """
    b: str = (base_url or "https://api.openai.com/v1").strip().rstrip("/")
    if b.endswith("/chat/completions"):
        return b
    if not b.endswith("/v1"):
        b += "/v1"
    return f"{b}/chat/completions"

def _call_llm(prompt: str, context: str) -> str:
    r"""
    调用 OpenAI 兼容 API 获取回答
    :param: prompt: 用户提问
    :param: context: 项目代码上下文
    :return: str: 模型回复文本
    :raise: RuntimeError: API Key 未配置
    :raise: httpx.HTTPStatusError: API 调用失败
    """
    api_key: str = utils.get_api_key()
    model: str = utils.get_api_model() or "gpt-4o-mini"

    if not api_key:
        raise RuntimeError("未配置 API Key")

    system_content: str = (
        "你是 MyBiOut! 项目的 AI 助手, 以 Mamba Mentality 的精神回答问题。"
        "以下是通过 pmc 工具打包的项目完整源代码作为参考:\n\n"
        + (context if context else "(项目代码未能获取, 请根据已有知识回答)")
        + "\n\n请根据用户的问题, 结合项目代码给出准确、有帮助的中文回答。"
    )

    messages: list[dict[str, str]] = [
        {"role": "system", "content": system_content},
        {"role": "user", "content": prompt},
    ]

    headers: dict[str, str] = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    base_url: str = utils.get_api_base_url()
    chat_url: str = _build_chat_url(base_url)
    timeout_seconds: float | None = utils.get_api_timeout_seconds()

    with httpx.Client(timeout=timeout_seconds) as client:
        r: httpx.Response = client.post(
            chat_url,
            headers=headers,
            json={"model": model, "messages": messages},
        )


def chat(prompt: str, force_bs: bool = False) -> dict:
    r"""
    处理对话请求, 根据配置决定使用大模型或狗屁不通文章生成器
    :param: prompt: 用户输入的提问
    :param: force_bs: 是否强制使用狗屁不通文章生成器
    :return: dict: 包含 ok/reply/source/note 的结果字典
    """
    prompt = prompt.strip()
    if not prompt:
        return {"ok": False, "error": "请输入问题"}

    _log("info", f"收到提问: {prompt[:50]}{'...' if len(prompt) > 50 else ''}")

    if force_bs:
        _log("info", "直接说模式 → 狗屁不通文章生成器")
        reply: str = bullshit_generate(prompt)
        return {"ok": True, "reply": reply, "source": "bullshit", "note": "「直接说」模式"}

    api_key: str = utils.get_api_key()
    if not api_key:
        _log("warn", "未配置 API Key, 降级为狗屁不通文章生成器")
        reply = bullshit_generate(prompt)
        return {
            "ok": True,
            "reply": reply,
            "source": "bullshit",
            "note": "未配置 API Key, 已使用狗屁不通文章生成器代替",
        }

    try:
        _log("info", "正在获取项目代码上下文...")
        context: str = _get_project_context()
        _log("info", f"正在调用大模型 ({utils.get_api_model() or 'gpt-4o-mini'})...")
        reply = _call_llm(prompt, context)
        _log("success", "大模型回复成功")
        return {"ok": True, "reply": reply, "source": "llm"}
    except Exception as e:
        _log("error", f"大模型调用失败: {e}, 降级为狗屁不通文章生成器")
        reply = bullshit_generate(prompt)
        return {
            "ok": True,
            "reply": reply,
            "source": "bullshit",
            "note": f"API 调用失败 ({e}), 已使用狗屁不通文章生成器代替",
        }


def get_logs() -> list[dict[str, str]]:
    r"""
    获取手册页日志列表
    :return: list[dict[str, str]]: 日志列表
    """
    with _logs_lock:
        return list(_logs)
    