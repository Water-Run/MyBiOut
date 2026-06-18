r"""
Mock ADB 逻辑：可作为独立脚本 (python fake_adb.py ...) 运行,
也可作为 Python 模块被测试代码直接调用 (run(args, root))。

行为映射:
  adb devices -l                    → 输出预定义设备列表
  adb -s SER shell ls -1a PATH     → 列出样例树中 PATH 下的条目
  adb -s SER shell stat -c %s ...  → 输出样例树中各文件大小
  adb -s SER pull REMOTE LOCAL     → 从样例树复制 REMOTE 到 LOCAL

样例根目录可通过环境变量 MYBIOUT_FAKE_ADB_ROOT 传递 (脚本模式),
或作为参数传入 (模块模式)。
"""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

SERIAL: str = "emulator-5554"
MODEL: str = "MockPixel"

DEVICES_OUTPUT: str = (
    "List of devices attached\n"
    f"{SERIAL}\tdevice product:mock_model model:{MODEL} device:mock_device\n"
)


def _resolve_remote(remote: str, root: Path) -> Path:
    r"""
    将远端路径 (/sdcard/...) 解析为样例根下的相对路径
    """
    rel: str = remote
    if rel.startswith("/sdcard/"):
        rel = rel[len("/sdcard/"):]
    elif rel.startswith("/"):
        rel = rel[1:]
    return root / rel


def _split_shell_args(parts: list[str]) -> list[str]:
    r"""
    将 production code 中以单字符串传入的 shell 命令拆分为多个参数
    例如 ["ls -1a '/sdcard/...'"] -> ["ls", "-1a", "/sdcard/..."]
    """
    out: list[str] = []
    for p in parts:
        if " " in p or "\t" in p:
            try:
                out.extend(shlex.split(p))
            except ValueError:
                out.append(p)
        else:
            out.append(p)
    return out


def _shell_ls(parts: list[str], root: Path) -> tuple[int, str, str]:
    expanded: list[str] = _split_shell_args(parts)
    path_arg: str = ""
    for i, p in enumerate(expanded):
        if p == "ls":
            if i + 1 < len(expanded):
                path_arg = expanded[-1]
            break
    target: Path = _resolve_remote(path_arg, root)
    if not target.exists():
        return 1, "", f"ls: cannot access '{path_arg}': No such file or directory"
    if target.is_file():
        return 0, target.name + "\n", ""
    names: list[str] = [e.name for e in sorted(target.iterdir())]
    return 0, "\n".join(names) + ("\n" if names else ""), ""


def _shell_stat(parts: list[str], root: Path) -> tuple[int, str, str]:
    expanded: list[str] = _split_shell_args(parts)
    out: list[str] = []
    rc: int = 0
    for p in expanded:
        if p == "stat" or p.startswith("-"):
            continue
        if "/" in p:
            target: Path = _resolve_remote(p, root)
            if target.exists() and target.is_file():
                out.append(str(target.stat().st_size))
            else:
                rc = 1
    return rc, "\n".join(out) + ("\n" if out else ""), ""


def _cmd_pull(parts: list[str], root: Path) -> tuple[int, str, str]:
    if len(parts) < 2:
        return 1, "", "pull: missing args"
    remote_arg: str = parts[0]
    local_arg: str = parts[1]
    src: Path = _resolve_remote(remote_arg, root)
    dst: Path = Path(local_arg)
    if not src.exists() or not src.is_file():
        return 1, "", f"adb: error: failed to stat remote object '{remote_arg}'"
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return 0, "", ""


def run(args: list[str], root: Path) -> subprocess.CompletedProcess:
    r"""
    纯 Python 模拟 adb 行为, 供测试代码直接调用

    :param: args: 调用 adb 时传入的 argv (不含 adb 自身, 但可能含 -s serial)
    :param: root: 样例缓存根目录
    :return: subprocess.CompletedProcess
    """
    filtered: list[str] = []
    skip_next: bool = False
    for a in args:
        if skip_next:
            skip_next = False
            continue
        if a == "-s":
            skip_next = True
            continue
        filtered.append(a)

    if "devices" in filtered:
        return subprocess.CompletedProcess(args, 0, DEVICES_OUTPUT, "")
    if "shell" in filtered:
        shell_args: list[str] = list(filtered[filtered.index("shell") + 1:])
        expanded: list[str] = _split_shell_args(shell_args)
        joined: str = " ".join(expanded)
        if "ls" in expanded or "ls" in joined:
            rc, out, err = _shell_ls(shell_args, root)
            return subprocess.CompletedProcess(args, rc, out, err)
        if "stat" in expanded or "stat" in joined:
            rc, out, err = _shell_stat(shell_args, root)
            return subprocess.CompletedProcess(args, rc, out, err)
        return subprocess.CompletedProcess(args, 1, "", f"unsupported shell cmd: {shell_args}")
    if "pull" in filtered:
        rc, out, err = _cmd_pull(list(filtered[filtered.index("pull") + 1:]), root)
        return subprocess.CompletedProcess(args, rc, out, err)
    return subprocess.CompletedProcess(args, 1, "", f"unsupported cmd: {args}")


def main() -> int:
    argv: list[str] = sys.argv[1:]
    raw: str = os.environ.get("MYBIOUT_FAKE_ADB_ROOT", "")
    if not raw:
        print("MYBIOUT_FAKE_ADB_ROOT not set", file=sys.stderr)
        return 2
    cp: subprocess.CompletedProcess = run(argv, Path(raw))
    sys.stdout.write(cp.stdout)
    sys.stderr.write(cp.stderr)
    sys.stdout.flush()
    sys.stderr.flush()
    return cp.returncode


if __name__ == "__main__":
    sys.exit(main())
