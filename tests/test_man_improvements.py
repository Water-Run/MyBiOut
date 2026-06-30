from __future__ import annotations

import json
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


def test_man_prompt_contains_complete_runtime_guidance_and_mamble_style() -> None:
    messages = man._build_messages("LocalOut 扫描不到安卓缓存怎么办", "fake project context")
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
