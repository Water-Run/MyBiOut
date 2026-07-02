from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAIN_HTML_FILES = [
    ROOT / "mybiout/pages/index.html",
    ROOT / "mybiout/pages/localout/localout.html",
    ROOT / "mybiout/pages/bbdown/bbdown.html",
    ROOT / "mybiout/pages/mdout/mdout.html",
    ROOT / "mybiout/pages/ohmyconfig/ohmyconfig.html",
    ROOT / "mybiout/pages/man/man.html",
]


def _project_text_files() -> list[Path]:
    return [
        path
        for path in [
            *ROOT.glob("*.md"),
            *ROOT.glob("*.toml"),
            *ROOT.glob("*.py"),
            *ROOT.glob("*.txt"),
            *ROOT.rglob("mybiout/**/*.py"),
            *ROOT.rglob("mybiout/**/*.html"),
        ]
        if path.is_file()
    ]


def test_logo_fullres_is_not_referenced_or_shipped() -> None:
    assert (ROOT / "mybiout/assets/logo.png").exists()
    assert not (ROOT / "mybiout/assets/logo-fullres.png").exists()

    offenders = [
        str(path.relative_to(ROOT))
        for path in _project_text_files()
        if "logo-fullres" in path.read_text(encoding="utf-8", errors="ignore")
    ]
    assert offenders == []


def test_main_pages_use_logo_png_favicon_and_have_entrance_animation() -> None:
    for path in MAIN_HTML_FILES:
        html = path.read_text(encoding="utf-8")
        assert "logo.png" in html, path
        assert "mybiout-entry-overlay" in html, path
        assert "mybiout-entry-core" in html, path


def test_entry_animation_is_shared_random_and_logo_free() -> None:
    entry_css = ROOT / "mybiout/assets/entry.css"
    entry_js = ROOT / "mybiout/assets/entry.js"

    assert entry_css.exists()
    assert entry_js.exists()

    js = entry_js.read_text(encoding="utf-8")
    variants = set(re.findall(r"name:\s*['\"]([^'\"]+)['\"]", js))
    assert len(variants) >= 15
    assert "入口变体表" in js
    assert "Math.random" in js
    assert "mybiout-entry-ready" in js

    css = entry_css.read_text(encoding="utf-8")
    assert ".mybiout-entry-overlay" in css
    assert ".mybiout-entry-canvas" in css
    assert "logo.png" not in css

    for path in MAIN_HTML_FILES:
        html = path.read_text(encoding="utf-8")
        assert "/assets/entry.css" in html, path
        assert "/assets/entry.js" in html, path
        overlay_start = html.find('<div class="mybiout-entry-overlay"')
        page_start = html.find('<div class="page"', overlay_start)
        assert overlay_start >= 0 and page_start > overlay_start, path
        overlay = html[overlay_start:page_start]
        assert "logo.png" not in overlay, path
        assert "<img" not in overlay.lower(), path


def test_entry_animation_has_no_visible_text_or_glyph_payloads() -> None:
    entry_css = ROOT / "mybiout/assets/entry.css"
    entry_js = ROOT / "mybiout/assets/entry.js"
    css = entry_css.read_text(encoding="utf-8")
    js = entry_js.read_text(encoding="utf-8")

    assert "signal:" not in js
    assert "textContent" not in js
    assert "data-glyph" not in css
    assert "dataset.glyph" not in js

    visible_english_labels = [
        "AURORA",
        "HYPER",
        "NEON",
        "PLASMA",
        "QUANTUM",
        "PRISM",
        "METEOR",
        "CYBER",
        "MAGNETIC",
        "LASER",
        "PIXEL",
        "LIQUID",
        "VORTEX",
        "SIGNAL",
        "SOLAR",
    ]
    assert not any(label in js for label in visible_english_labels)

    for path in MAIN_HTML_FILES:
        html = path.read_text(encoding="utf-8")
        overlay_start = html.find('<div class="mybiout-entry-overlay"')
        page_start = html.find('<div class="page"', overlay_start)
        assert overlay_start >= 0 and page_start > overlay_start, path
        overlay = html[overlay_start:page_start]
        assert "mybiout-entry-title" not in overlay, path


def test_entry_animation_speed_and_algorithmic_variation_controls() -> None:
    entry_css = ROOT / "mybiout/assets/entry.css"
    entry_js = ROOT / "mybiout/assets/entry.js"
    css = entry_css.read_text(encoding="utf-8")
    js = entry_js.read_text(encoding="utf-8")

    assert re.search(r"入口速度\s*=\s*1\.3\b", js)
    assert "按毫秒加速(" in js
    assert "按秒加速(" in js
    assert "const 生成后 =" in js
    assert "生成变体(" in js
    assert "算法:" in js
    assert "网格:" in js
    assert "density:" in js
    assert "角度:" in js
    assert "种子:" in js

    assert "--entry-overlay-delay" in css
    assert "--entry-overlay-duration" in css
    assert "animation: entryOverlayLeave var(--entry-overlay-duration)" in css


def test_settings_link_is_bold_high_contrast() -> None:
    html = (ROOT / "mybiout/pages/index.html").read_text(encoding="utf-8")
    block_match = re.search(r"\.settings-link\s*\{(?P<body>[\s\S]*?)\}", html)
    assert block_match is not None

    block = block_match.group("body")
    assert re.search(r"font-weight\s*:\s*(800|900|bold)", block)
    assert "background:" in block
    assert "box-shadow:" in block
    assert "text-shadow:" in block


def test_local_docs_and_temp_exports_are_ignored() -> None:
    ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")

    assert "docs/" in ignore
    assert "/tmp/" in ignore
