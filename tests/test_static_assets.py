from __future__ import annotations

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


def test_local_docs_and_temp_exports_are_ignored() -> None:
    ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")

    assert "docs/" in ignore
    assert "/tmp/" in ignore
