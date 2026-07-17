# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec: 生成 Windows 绿色 onedir 包
# 用法: 在仓库根目录执行
#   pyinstaller packaging/MyBiOut.spec
# 再运行 scripts/assemble_green.py 组装 bin 与说明

from pathlib import Path

from PyInstaller.utils.hooks import collect_all
from PyInstaller.utils.hooks import collect_submodules

根目录 = Path(SPECPATH).resolve().parent
包目录 = 根目录 / "mybiout"

数据文件 = [
    (str(包目录 / "pages"), "mybiout/pages"),
    (str(包目录 / "assets"), "mybiout/assets"),
    (str(包目录 / "config.ini"), "mybiout"),
    (str(包目录 / "bin" / "BullshitGenerator"), "mybiout/bin/BullshitGenerator"),
]

隐藏导入 = [
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
    "mybiout",
    "mybiout.main",
    "mybiout.pages",
    "mybiout.pages.apis",
    "mybiout.pages.utils",
    "mybiout.pages.bbdown.bbdown",
    "mybiout.pages.localout.localout",
    "mybiout.pages.mdout.mdout",
    "mybiout.pages.man.man",
    "mybiout.pages.ohmyconfig.ohmyconfig",
]

for 包名 in ("uvicorn", "fastapi", "starlette", "anyio", "httpx", "webview"):
    try:
        额外数据, 额外二进制, 额外隐藏 = collect_all(包名)
        数据文件 += 额外数据
        隐藏导入 += 额外隐藏
    except Exception:
        隐藏导入 += collect_submodules(包名)

图标路径 = 包目录 / "assets" / "logo.ico"
图标参数 = str(图标路径) if 图标路径.exists() else None

a = Analysis(
    [str(根目录 / "packaging" / "launch.py")],
    pathex=[str(根目录)],
    binaries=[],
    datas=数据文件,
    hiddenimports=隐藏导入,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="MyBiOut",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=图标参数,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="MyBiOut",
)
