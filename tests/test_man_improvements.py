from __future__ import annotations

import json
import re
from pathlib import Path

from mybiout.pages.man import man

ROOT = Path(__file__).resolve().parent.parent


def test_manual_page_is_runtime_help_not_install_notes() -> None:
    html = (ROOT / "mybiout/pages/man/man.html").read_text(encoding="utf-8")

    assert "pip install" not in html
    assert "常见情况" in html
    assert "LocalOut 使用流程" in html
    assert "BBDown 使用流程" in html
    assert "MdOut 使用流程" in html
    assert "大模型配置与响应" in html


def test_bullshit_generator_uses_computer_ai_source_material() -> None:
    data = json.loads((ROOT / "mybiout/bin/BullshitGenerator/data.json").read_text(encoding="utf-8"))
    famous_text = "\n".join(data["famous"])
    required_names = [
        "OpenAI",
        "Claude",
        "DeepSeek",
        "Mimo",
        "ChatGPT",
        "GPT-5",
        "Gemini",
        "Anthropic",
        "Meta AI",
        "Llama",
        "Qwen",
        "Kimi",
        "豆包",
        "通义千问",
        "文心一言",
        "Microsoft Copilot",
        "GitHub Copilot",
        "Perplexity",
        "Midjourney",
        "Stable Diffusion",
    ]

    assert all(name in famous_text for name in required_names)
    assert len(data["famous"]) >= 40
    assert len(data["bosh"]) >= 70
    assert any("编译器" in item for item in data["bosh"])
    assert any("上下文窗口" in item for item in data["bosh"])
    assert any("向量数据库" in item for item in data["bosh"])


def test_bullshit_generator_has_hundreds_of_diverse_speakers() -> None:
    data = json.loads((ROOT / "mybiout/bin/BullshitGenerator/data.json").read_text(encoding="utf-8"))
    speakers = data.get("speakers", [])
    speaker_text = "\n".join(speakers)
    total_material_count = sum(len(value) for value in data.values() if isinstance(value, list))

    expected_groups = [
        ["GPT-4", "GPT-5", "Claude", "DeepSeek", "Mimo", "LongCat", "Gemini", "Llama", "Qwen", "Kimi"],
        ["乔布斯", "比尔盖茨", "库克", "黄仁勋", "图灵", "Ada Lovelace", "Linus Torvalds", "Grace Hopper"],
        ["OpenAI", "Anthropic", "Google", "Microsoft", "Apple", "NVIDIA", "三星", "Meta", "阿里云", "腾讯云"],
        ["Python", "Rust", "Go", "JavaScript", "TypeScript", "MySQL", "PostgreSQL", "Redis", "SQLite", "MongoDB"],
        ["Linux", "Git", "Docker", "Kubernetes", "Nginx", "FastAPI", "React", "Vue", "Kafka", "Elasticsearch"],
    ]

    assert len(speakers) >= 260
    assert total_material_count >= 650
    for group in expected_groups:
        assert sum(name in speaker_text for name in group) >= len(group) - 1


def test_fallback_bullshit_generation_is_structured_varied_and_topic_aware() -> None:
    man.随机.seed(20260702)
    reply = man.生成胡言("LocalOut 扫描不到 Android 缓存怎么办", 目标长度=1100)
    paragraphs = [paragraph for paragraph in reply.split("\n\n") if paragraph.strip()]
    sentences = [part.strip() for part in re.split(r"[。！？\n]+", reply) if len(part.strip()) > 8]

    assert len(reply) >= 1100
    assert len(paragraphs) >= 4
    assert "LocalOut" in reply
    assert "扫描" in reply or "缓存" in reply
    assert any(name in reply for name in ["GPT-5", "Claude", "DeepSeek", "Mimo", "LongCat", "乔布斯", "图灵", "Python"])
    assert any(word in reply for word in ["首先", "其次", "进一步说", "换句话说", "最后"])
    assert len(sentences) >= 12
    assert len(set(sentences)) / len(sentences) > 0.75
    assert reply.count("最后") <= 2
    assert not re.search(r"[\u4e00-\u9fff] [\u4e00-\u9fff]", reply)


def test_fallback_generation_prefers_module_terms_over_unrelated_jargon() -> None:
    man.随机.seed(20260702)
    reply = man.生成胡言("LocalOut 扫描不到 Android 缓存怎么办", 目标长度=1100)
    localout_terms = [
        "LocalOut",
        "Android",
        "缓存",
        "ADB",
        "设备授权",
        "缓存路径",
        "自定义路径",
        "卡片",
        "FFmpeg",
        "导出目录",
        "m4s",
    ]
    unrelated_terms = [
        "召回链路",
        "向量数据库",
        "嵌入模型",
        "重排序器",
        "全表扫描",
        "提示词注入",
        "上下文窗口很大",
        "供应商响应",
        "超时设置",
        "取消信号",
        "异常分支里的回复也做成中文",
        "成功提示延迟",
    ]

    assert sum(term in reply for term in localout_terms) >= 7
    assert sum(term in reply for term in unrelated_terms) <= 1


def test_man_prompt_contains_complete_runtime_guidance_and_mamble_style() -> None:
    messages = man._构建消息("LocalOut 扫描不到安卓缓存怎么办", "fake project context")
    system = messages[0]["content"]

    assert "Mamble" in system
    assert "Mamba" in system
    assert "LocalOut" in system
    assert "BBDown" in system
    assert "MdOut" in system
    assert "OhMyConfig" in system
    assert "大模型配置" in system
    assert "如果信息不足" in system
    assert "fake project context" in system
    assert messages[1] == {"role": "user", "content": "LocalOut 扫描不到安卓缓存怎么办"}


def test_man_llm_request_keeps_httpx_json_keyword(monkeypatch) -> None:
    seen: dict = {}

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"choices": [{"message": {"content": "运行时回答"}}]}

    class FakeClient:
        def __init__(self, *, timeout) -> None:
            seen["timeout"] = timeout

        def __enter__(self):
            return self

        def __exit__(self, *_exc) -> None:
            return None

        def post(self, url, *, headers, json):
            seen["url"] = url
            seen["headers"] = headers
            seen["json"] = json
            return FakeResponse()

    monkeypatch.setattr(man.工具, "取接口密钥", lambda: "key")
    monkeypatch.setattr(man.工具, "取接口模型", lambda: "model")
    monkeypatch.setattr(man.工具, "取接口基地址", lambda: "https://example.test/v1")
    monkeypatch.setattr(man.工具, "取接口超时秒数", lambda: 12.0)
    monkeypatch.setattr(man.网络请求, "Client", FakeClient)

    reply = man._调用大模型("怎么用 Man", "项目上下文")

    assert reply == "运行时回答"
    assert seen["json"]["model"] == "model"
    assert seen["json"]["messages"][1] == {"role": "user", "content": "怎么用 Man"}


def test_man_stream_request_keeps_httpx_json_keyword(monkeypatch) -> None:
    seen: dict = {}

    class FakeStreamResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_exc) -> None:
            return None

        def raise_for_status(self) -> None:
            return None

        def iter_lines(self):
            yield 'data: {"choices":[{"delta":{"content":"片段"}}]}'
            yield "data: [DONE]"

    class FakeClient:
        def __init__(self, *, timeout) -> None:
            seen["timeout"] = timeout

        def __enter__(self):
            return self

        def __exit__(self, *_exc) -> None:
            return None

        def stream(self, method, url, *, headers, json):
            seen["method"] = method
            seen["url"] = url
            seen["headers"] = headers
            seen["json"] = json
            return FakeStreamResponse()

    monkeypatch.setattr(man.工具, "取接口密钥", lambda: "key")
    monkeypatch.setattr(man.工具, "取接口模型", lambda: "model")
    monkeypatch.setattr(man.工具, "取接口基地址", lambda: "https://example.test/v1")
    monkeypatch.setattr(man.工具, "取接口超时秒数", lambda: 12.0)
    monkeypatch.setattr(man.网络请求, "Client", FakeClient)

    chunks = list(man._流式调用大模型("怎么用 Man", "项目上下文"))

    assert chunks == ["片段"]
    assert seen["method"] == "POST"
    assert seen["json"]["stream"] is True
    assert seen["json"]["messages"][1] == {"role": "user", "content": "怎么用 Man"}
