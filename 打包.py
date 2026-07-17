r"""
MyBiOut! 绿色版一键打包: 升版本 → 依赖 → PyInstaller → 组装 → rar
用法: python 打包.py

版本写入 mybiout/version.txt, 格式 YY.MM.DD.当日序号 (如 26.07.17.1)
同日再打包则序号 +1; 页面经 /api/version 动态读取
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

根 = Path(__file__).resolve().parent
包 = 根 / "mybiout"
版本文件 = 包 / "version.txt"
产物名 = "MyBiOut!"
依赖 = [
    "fastapi",
    "uvicorn[standard]",
    "httpx",
    "biliffm4s",
    "pywebview",
    "pyinstaller",
]


def 跑(命令: list[str], **kw) -> None:
    print(">", " ".join(命令))
    结果 = subprocess.run(命令, check=False, **kw)
    if 结果.returncode:
        raise SystemExit(结果.returncode)


def 取版本() -> str:
    if 版本文件.is_file():
        文本 = 版本文件.read_text(encoding="utf-8").strip()
        if 文本:
            return 文本
    return "0.0.0.0"


def 下一日序号版本(旧版本: str) -> str:
    今日前缀 = date.today().strftime("%y.%m.%d")
    序号 = 1
    if 旧版本.startswith(今日前缀 + "."):
        尾 = 旧版本[len(今日前缀) + 1 :]
        if 尾.isdigit():
            序号 = int(尾) + 1
    return f"{今日前缀}.{序号}"


def 写入版本(版本: str) -> None:
    版本文件.write_text(版本 + "\n", encoding="utf-8")


def 升版本() -> str:
    print("\n[0/4] 版本号 → version.txt")
    旧 = 取版本()
    新 = 下一日序号版本(旧)
    写入版本(新)
    print(f"  {旧}  →  {新}")
    return 新


def 找Rar() -> Path | None:
    w = shutil.which("Rar") or shutil.which("rar")
    if w:
        return Path(w)
    for p in (
        Path(r"C:\Program Files\WinRAR\Rar.exe"),
        Path(r"C:\Program Files (x86)\WinRAR\Rar.exe"),
    ):
        if p.is_file():
            return p
    return None


def 装依赖() -> None:
    print("\n[1/4] 依赖")
    跑([sys.executable, "-m", "pip", "install", "-U", *依赖])


def 构建() -> None:
    print("\n[2/4] PyInstaller")
    数据 = [
        f"{包 / 'pages'};mybiout/pages",
        f"{包 / 'assets'};mybiout/assets",
        f"{包 / 'config.ini'};mybiout",
        f"{包 / 'version.txt'};mybiout",
        f"{包 / 'bin' / 'BullshitGenerator'};mybiout/bin/BullshitGenerator",
    ]
    隐藏 = [
        "uvicorn.logging",
        "uvicorn.loops.auto",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.lifespan.on",
        "mybiout",
        "mybiout.main",
        "mybiout.pages.apis",
        "mybiout.pages.utils",
        "mybiout.pages.bbdown.bbdown",
        "mybiout.pages.localout.localout",
        "mybiout.pages.mdout.mdout",
        "mybiout.pages.man.man",
        "mybiout.pages.ohmyconfig.ohmyconfig",
    ]
    参数 = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--windowed",
        "--onedir",
        "--name",
        产物名,
        "--paths",
        str(根),
        "--distpath",
        str(根 / "dist"),
        "--workpath",
        str(根 / "build"),
        "--specpath",
        str(根 / "build"),
    ]
    for d in 数据:
        参数 += ["--add-data", d]
    for h in 隐藏:
        参数 += ["--hidden-import", h]
    for 名 in ("uvicorn", "fastapi", "starlette", "anyio", "httpx", "webview"):
        参数 += ["--collect-all", 名]
    参数.append(str(包 / "main.py"))
    跑(参数, cwd=str(根))


def 组装(版本: str) -> Path:
    print("\n[3/4] 组装绿色目录")
    源 = 根 / "dist" / 产物名
    目标 = 根 / "dist" / "MyBiOut-green"
    if not 源.is_dir():
        raise SystemExit(f"未找到构建输出: {源}")
    if 目标.exists():
        shutil.rmtree(目标)
    shutil.copytree(源, 目标)
    源bin = 包 / "bin"
    if 源bin.is_dir():
        目标bin = 目标 / "bin"
        if 目标bin.exists():
            shutil.rmtree(目标bin)
        shutil.copytree(源bin, 目标bin, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    for 旁路 in ("config.ini", "version.txt"):
        源文件 = 包 / 旁路
        if 源文件.is_file():
            shutil.copy2(源文件, 目标 / 旁路)
    说明 = f"""MyBiOut! 绿色版  v{版本}

1. 双击 MyBiOut!.exe 启动, 关闭窗口即退出
2. Windows 11 x64; 若无窗口请安装 WebView2 Runtime
3. config.ini = 配置; bin/ = BBDown, ffmpeg 等; version.txt = 版本号

可选: MyBiOut!.exe --port 23333  /  --browser

https://github.com/Water-Run/MyBiOut
"""
    (目标 / "使用说明.txt").write_text(说明, encoding="utf-8")
    print(" ", 目标)
    return 目标


def 打rar(绿色: Path, 版本: str) -> Path:
    print("\n[4/4] rar")
    rar = 找Rar()
    if rar is None:
        raise SystemExit("未找到 WinRAR 的 Rar.exe, 请安装后重试")
    发布 = 根 / "dist" / "release"
    发布.mkdir(parents=True, exist_ok=True)
    归档 = 发布 / f"{产物名}-{版本}.rar"
    暂存 = 根 / "dist" / "_rar_stage"
    包目录 = 暂存 / 产物名
    if 暂存.exists():
        shutil.rmtree(暂存)
    shutil.copytree(绿色, 包目录, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    if 归档.exists():
        归档.unlink()
    跑([str(rar), "a", "-r", "-m5", "-y", str(归档), 产物名], cwd=str(暂存))
    shutil.rmtree(暂存, ignore_errors=True)
    print(f"  {归档}  ({归档.stat().st_size / 1024 / 1024:.1f} MB)")
    return 归档


def main() -> None:
    if sys.platform != "win32":
        raise SystemExit("仅支持 Windows")
    版本 = 升版本()
    装依赖()
    构建()
    绿色 = 组装(版本)
    归档 = 打rar(绿色, 版本)
    print(f"\n完成  v{版本}\n  绿色: {绿色}\n  发布: {归档}")


if __name__ == "__main__":
    main()
