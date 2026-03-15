"""MyBiOut! 设置页 —— 服务层 (校验 / 浏览 / 业务逻辑)"""

from pathlib import Path

from mybiout.pages import utils


# ============================== 查询 ==============================


def get_settings() -> dict[str, dict[str, str]]:
    """给页面用的: 取全部设置."""
    return utils.get_all_settings()


# ============================== 保存 (带校验) ==============================


def validate_and_save(section: str, key: str, value: str) -> dict:
    """
    校验后保存单条设置.
    返回 ``{"ok": True}`` 或 ``{"ok": False, "error": "..."}``
    """
    # --- 导出路径 ---
    if section == "export" and key == "path":
        if not value.strip():
            return _err("路径不能空着啊!")
        utils.set_setting(section, key, value.strip())
        return _ok()

    # --- 文件夹名 ---
    if key == "folder" and section in ("localout", "bbdown", "mdout"):
        return _validate_folder(section, value)

    # --- 其余项直接存 ---
    utils.set_setting(section, key, str(value))
    return _ok()


def _validate_folder(section: str, value: str) -> dict:
    name = value.strip()
    if not name:
        return _err("文件夹名不能空着!")

    # 不可和其它模块的文件夹撞
    for other in ("localout", "bbdown", "mdout"):
        if other == section:
            continue
        if utils.get_setting(other, "folder") == name:
            return _err(f"和 {other} 的撞了!")

    # 不可和导出目录下已有的无关文件夹撞
    export_dir = Path(utils.get_setting("export", "path"))
    if export_dir.exists():
        owned = {
            utils.get_setting(s, "folder")
            for s in ("localout", "bbdown", "mdout")
        }
        for item in export_dir.iterdir():
            if item.is_dir() and item.name == name and item.name not in owned:
                return _err(f"那里已经有叫 '{name}' 的了!")

    utils.set_setting(section, "folder", name)
    return _ok()


# ============================== 浏览 / 桌面 ==============================


def browse_folder() -> str | None:
    """弹出系统文件夹选择对话框 (tkinter, 仅 Windows 本机)."""
    try:
        from tkinter import Tk, filedialog

        root = Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        folder = filedialog.askdirectory(title="选一个地方放东西")
        root.destroy()
        return folder if folder else None
    except Exception:
        return None


def get_desktop_path() -> str:
    """桌面下的 MyBiOut! 路径."""
    return str(Path.home() / "Desktop" / "MyBiOut!")


# ============================== 内部 ==============================


def _ok() -> dict:
    return {"ok": True}


def _err(msg: str) -> dict:
    return {"ok": False, "error": msg}