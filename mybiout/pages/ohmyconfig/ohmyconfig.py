r"""
MyBiOut! 设置页服务层, 负责设置的校验、浏览与业务逻辑

:file: mybiout/pages/ohmyconfig/ohmyconfig.py
:author: WaterRun
:time: 2026-04-07
"""

import json
import os
import sys
from contextlib import suppress
from pathlib import Path

from mybiout.pages import utils

type SettingResult = dict[str, bool | str]

_ALLOWED_BOOL: set[str] = {"true", "false"}
_ALLOWED_INCOMPLETE_TITLE_ACTION: set[str] = {"partial_or_folder", "folder_only", "skip"}
_ALLOWED_NAME_PARTS: set[str] = {"bv", "title", "up", "group", "part", "publish_time", "export_time"}
_ALLOWED_FAVORITE_DETAIL: set[str] = {"basic", "full"}
_ALLOWED_REQUEST_DELAY: set[str] = {"0.3", "0.5", "1.0", "2.0"}
_ALLOWED_API_TIMEOUT: set[str] = {"infinite", "8s", "20s", "60s", "100s", "1000s"}


def get_settings() -> dict[str, dict[str, str]]:
    r"""
    获取全部设置项
    :return: dict[str, dict[str, str]]: 全部设置
    """
    return utils.get_all_settings()


def validate_and_save(section: str, key: str, value: str) -> SettingResult:
    r"""
    校验后保存单条设置
    :param: section: 配置分区名
    :param: key: 配置键名
    :param: value: 配置值
    :return: SettingResult: 包含 ok 和可选 error 的结果字典
    """
    match (section, key):
        case ("export", "path"):
            if not value.strip():
                return _err("路径不能空着啊!")
            utils.set_setting(section, key, value.strip())
            return _ok()

        case ("localout" | "bbdown" | "mdout", "folder"):
            return _validate_folder(section, value)

        case ("localout", "bilibili_pc_cache_optional_when_installed"):
            return _save_bool(section, key, value)

        case ("localout", "bilibili_pc_cache_path"):
            utils.set_setting(section, key, value.strip())
            return _ok()

        case ("localout", "ffmpeg_concurrent"):
            v = value.strip()
            if not v.isdigit() or not (1 <= int(v) <= 32):
                return _err("ffmpeg并发范围建议 1~32")
            utils.set_setting(section, key, v)
            return _ok()

        case ("localout", "name_parts"):
            parts: list[str] = [x.strip() for x in value.split(",") if x.strip()]
            if not parts:
                return _err("命名至少勾一个吧!")
            if unknown := [x for x in parts if x not in _ALLOWED_NAME_PARTS]:
                return _err(f"出现了未知命名项: {', '.join(unknown)}")
            utils.set_setting(section, key, ",".join(parts))
            return _ok()

        case ("localout", "incomplete_title_action"):
            v = value.strip()
            if v not in _ALLOWED_INCOMPLETE_TITLE_ACTION:
                return _err("标题补全策略值不合法")
            utils.set_setting(section, key, v)
            return _ok()

        case ("localout", "crawler_fallback"):
            v = value.strip().lower()
            if v not in {"disabled", "1s", "2s", "5s"}:
                return _err("爬虫超时选项只能为 disabled / 1s / 2s / 5s")
            utils.set_setting(section, key, v)
            return _ok()

        case ("bbdown", "download_danmaku" | "skip_subtitle" | "skip_cover" | "use_aria2c"):
            return _save_bool(section, key, value)

        case ("bbdown", "cookie"):
            utils.set_setting(section, key, value.strip())
            return _ok()

        case ("bbdown", "encoding_priority" | "quality_priority" | "file_pattern" | "multi_file_pattern"):
            utils.set_setting(section, key, value.strip())
            return _ok()

        case ("mdout", "include_cover" | "include_tags" | "include_stats"):
            return _save_bool(section, key, value)

        case ("mdout", "sessdata"):
            utils.set_setting(section, key, value.strip())
            return _ok()

        case ("mdout", "favorite_detail"):
            v = value.strip()
            if v not in _ALLOWED_FAVORITE_DETAIL:
                return _err("收藏夹详情只能是 basic / full")
            utils.set_setting(section, key, v)
            return _ok()

        case ("mdout", "request_delay"):
            v = value.strip()
            if v not in _ALLOWED_REQUEST_DELAY:
                return _err("请求间隔只能是 0.3 / 0.5 / 1.0 / 2.0")
            utils.set_setting(section, key, v)
            return _ok()

        case ("api", "key" | "model"):
            utils.set_setting(section, key, value.strip())
            return _ok()

        case ("api", "base_url"):
            v: str = value.strip()
            if not v:
                return _err("API 地址不能为空")
            if not (v.startswith("http://") or v.startswith("https://")):
                return _err("API 地址需以 http:// 或 https:// 开头")
            utils.set_setting(section, key, v.rstrip("/"))
            return _ok()

        case ("api", "timeout"):
            v: str = value.strip().lower()
            if v not in _ALLOWED_API_TIMEOUT:
                return _err("超时选项不合法")
            utils.set_setting(section, key, v)
            return _ok()

        case _:
            utils.set_setting(section, key, str(value))
            return _ok()


def _save_bool(section: str, key: str, value: str) -> SettingResult:
    r"""
    校验并保存布尔型设置
    :param: section: 配置分区名
    :param: key: 配置键名
    :param: value: 待校验值
    :return: SettingResult: 保存结果
    """
    v: str = value.strip().lower()
    if v not in _ALLOWED_BOOL:
        return _err("开关值不对劲, 只能 true/false")
    utils.set_setting(section, key, v)
    return _ok()


def _validate_folder(section: str, value: str) -> SettingResult:
    r"""
    校验并保存文件夹名称, 检查冲突
    :param: section: 配置分区名
    :param: value: 文件夹名称
    :return: SettingResult: 保存结果
    """
    name: str = value.strip()
    if not name:
        return _err("文件夹名不能空着!")

    for other in ("localout", "bbdown", "mdout"):
        if other != section and utils.get_setting(other, "folder") == name:
            return _err(f"和 {other} 的撞了!")

    export_path_str: str = utils.get_setting("export", "path").strip()
    if export_path_str:
        try:
            export_dir: Path = Path(export_path_str)
            if export_dir.exists():
                owned: set[str] = {utils.get_setting(s, "folder") for s in ("localout", "bbdown", "mdout")}
                for item in export_dir.iterdir():
                    if item.is_dir() and item.name == name and item.name not in owned:
                        return _err(f"那里已经有叫 '{name}' 的了!")
        except Exception:
            pass

    utils.set_setting(section, "folder", name)
    return _ok()


def browse_folder() -> str | None:
    r"""
    弹出系统文件夹选择对话框
    :return: str | None: 选中的路径, 取消时返回 None
    """
    try:
        from tkinter import Tk, filedialog

        root: Tk = Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        folder: str = filedialog.askdirectory(title="选一个地方放东西")
        root.destroy()
        return folder if folder else None
    except Exception:
        return None


def get_desktop_path() -> str:
    r"""
    获取桌面下的 MyBiOut! 路径
    :return: str: 桌面导出路径
    """
    return str(Path.home() / "Desktop" / "MyBiOut!")


def get_default_bili_pc_cache_path() -> str:
    r"""
    获取默认哔哩哔哩电脑端缓存路径
    :return: str: 默认缓存路径
    """
    return utils.get_default_bilibili_pc_cache_path()


def _ok() -> SettingResult:
    r"""
    构建成功结果
    :return: SettingResult: 成功结果字典
    """
    return {"ok": True}


def _err(msg: str) -> SettingResult:
    r"""
    构建失败结果
    :param: msg: 错误信息
    :return: SettingResult: 失败结果字典
    """
    return {"ok": False, "error": msg}


def reset_all() -> dict[str, bool]:
    r"""
    恢复全部默认设置
    :return: dict: 操作结果
    """
    utils.reset_all_settings()
    return {"ok": True}


def _sess_from_cookiejar(jar) -> str | None:
    try:
        for c in jar:
            if c.name == "SESSDATA" and "bilibili.com" in (c.domain or "") and c.value:
                return c.value
    except Exception:
        pass
    return None


def _fast_copy_file(src: Path, dst: Path) -> bool:
    r"""
    快速尝试复制文件，允许共享读取。
    如果文件被进程独占锁定，且拥有管理员权限，则尝试使用 shadowcopy 影子拷贝复制，避免挂起。
    """
    try:
        import win32con
        import win32file

        handle = win32file.CreateFile(
            str(src),
            win32con.GENERIC_READ,
            win32con.FILE_SHARE_READ | win32con.FILE_SHARE_WRITE | win32con.FILE_SHARE_DELETE,
            None,
            win32con.OPEN_EXISTING,
            win32con.FILE_ATTRIBUTE_NORMAL,
            None,
        )
        with dst.open("wb") as f_out:
            while True:
                _err, data = win32file.ReadFile(handle, 64 * 1024)
                if not data:
                    break
                f_out.write(data)
        win32file.CloseHandle(handle)
        return True
    except Exception:
        # 如果共享读取失败（如 Chrome 独占锁定），尝试使用 shadowcopy（需要管理员权限）
        try:
            import shadowcopy.shadow as sha

            sha.shadow_copy(str(src), str(dst))
            return True
        except Exception:
            try:
                import shutil

                shutil.copy2(src, dst)
                return True
            except Exception:
                return False


def _auto_get_sessdata_from_browsers(user_agent: str | None = None) -> str | None:
    r"""
    从本地浏览器数据库快速尝试获取 SESSDATA（不卡顿，不使用 shadowcopy）。
    如果遇到数据库被独占锁定，或检测到 v20 (App-Bound Encryption)，则立即跳过。
    """
    import base64
    import sqlite3
    import tempfile

    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        return None

    # 定义各个主流浏览器的 User Data 路径
    browser_dirs = {
        "edge": Path(local_app_data) / "Microsoft" / "Edge" / "User Data",
        "chrome": Path(local_app_data) / "Google" / "Chrome" / "User Data",
        "brave": Path(local_app_data) / "BraveSoftware" / "Brave-Browser" / "User Data",
        "opera": Path(local_app_data) / "Opera Software" / "Opera Stable",
        "vivaldi": Path(local_app_data) / "Vivaldi" / "User Data",
    }

    # 1. 识别当前浏览器优先级
    current_browser = None
    if user_agent:
        ua = user_agent.lower()
        if "edg/" in ua or "edge" in ua:
            current_browser = "edge"
        elif "opr/" in ua or "opera" in ua:
            current_browser = "opera"
        elif "vivaldi" in ua:
            current_browser = "vivaldi"
        elif "firefox" in ua:
            current_browser = "firefox"
        elif "brave" in ua:
            current_browser = "brave"
        elif "chrome" in ua and not any(x in ua for x in ["edg/", "edge", "opr/", "opera", "vivaldi", "brave"]):
            current_browser = "chrome"

    browser_order = []
    if current_browser and current_browser in browser_dirs:
        browser_order.append(current_browser)

    default_order = ["chrome", "edge", "brave", "opera", "vivaldi"]
    for b in default_order:
        if b not in browser_order:
            browser_order.append(b)

    # 2. 尝试从 Chromium 系浏览器读取
    for name in browser_order:
        user_data_dir = browser_dirs[name]
        if not user_data_dir.exists():
            continue

        # 获取解密 Key
        local_state_path = user_data_dir / "Local State"
        if not local_state_path.exists():
            continue

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp_file:
            tmp_path = Path(tmp_file.name)
        try:
            if not _fast_copy_file(local_state_path, tmp_path):
                continue
            with tmp_path.open(encoding="utf-8") as f:
                local_state = json.loads(f.read())
            encrypted_key = base64.b64decode(local_state["os_crypt"]["encrypted_key"])[5:]
            import win32crypt

            decrypted_key = win32crypt.CryptUnprotectData(encrypted_key, None, None, None, 0)[1]
        except Exception:
            continue
        finally:
            if tmp_path.exists():
                tmp_path.unlink()

        # 扫描所有可能的 Cookies 数据库位置
        profiles = (
            list(user_data_dir.glob("Default/Network/Cookies"))
            + list(user_data_dir.glob("Profile */Network/Cookies"))
            + list(user_data_dir.glob("Default/Cookies"))
            + list(user_data_dir.glob("Profile */Cookies"))
            + list(user_data_dir.glob("Network/Cookies"))
            + list(user_data_dir.glob("Cookies"))
        )

        for db_path in profiles:
            if not db_path.exists():
                continue
            with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp_file:
                tmp_db_path = Path(tmp_file.name)
            try:
                if _fast_copy_file(db_path, tmp_db_path):
                    conn = sqlite3.connect(tmp_db_path)
                    cursor = conn.cursor()
                    cursor.execute(
                        "SELECT encrypted_value FROM cookies WHERE host_key LIKE '%bilibili.com' AND name = 'SESSDATA'"
                    )
                    row = cursor.fetchone()
                    if row:
                        enc_val = row[0]
                        # 只尝试解密 v10/v11，v20 则直接放弃（交给引导登录）
                        if enc_val.startswith(b"v10") or enc_val.startswith(b"v11"):
                            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

                            iv = enc_val[3:15]
                            ciphertext = enc_val[15:]
                            aesgcm = AESGCM(decrypted_key)
                            decrypted = aesgcm.decrypt(iv, ciphertext, None)
                            s = decrypted.decode("utf-8")
                            if s:
                                conn.close()
                                return s
                    conn.close()
            except Exception:
                pass
            finally:
                if tmp_db_path.exists():
                    tmp_db_path.unlink()

    # 3. 尝试从 Firefox 读取 (Firefox cookies 无加密)
    app_data = os.environ.get("APPDATA")
    if app_data:
        firefox_dir = Path(app_data) / "Mozilla" / "Firefox"
        if firefox_dir.exists():
            profiles_dir = firefox_dir / "Profiles"
            if profiles_dir.exists():
                for profile in profiles_dir.iterdir():
                    db_path = profile / "cookies.sqlite"
                    if not db_path.exists():
                        continue
                    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp_file:
                        tmp_db_path = Path(tmp_file.name)
                    try:
                        if _fast_copy_file(db_path, tmp_db_path):
                            conn = sqlite3.connect(tmp_db_path)
                            cursor = conn.cursor()
                            cursor.execute(
                                "SELECT value FROM moz_cookies WHERE host LIKE '%bilibili.com' AND name = 'SESSDATA'"
                            )
                            row = cursor.fetchone()
                            if row and row[0]:
                                val = row[0]
                                conn.close()
                                return val
                            conn.close()
                    except Exception:
                        pass
                    finally:
                        if tmp_db_path.exists():
                            tmp_db_path.unlink()

    return None


def _auto_get_sessdata_via_login(user_agent: str | None = None, timeout_sec: int = 180) -> str | None:
    r"""
    打开可视化登录页，引导用户登录后自动读取 SESSDATA。
    使用持久化的浏览器 User Data Profile 目录，避免每次都打开全新的“隐私窗口”需要重新登录。
    """
    try:
        import time

        from playwright.sync_api import sync_playwright  # type: ignore
    except Exception:
        return None

    # 从 User-Agent 识别目标浏览器
    browser_type = "chromium"
    channel = None
    if user_agent:
        ua = user_agent.lower()
        if "edg/" in ua or "edge" in ua:
            browser_type = "chromium"
            channel = "msedge"
        elif "firefox" in ua:
            browser_type = "firefox"
        elif "chrome" in ua:
            if not any(x in ua for x in ["edg/", "edge", "opr/", "opera", "vivaldi", "brave"]):
                browser_type = "chromium"
                channel = "chrome"

    # 使用持久化 profile 路径，存在 MyBiOut 根目录下的 auth_profile 中
    auth_profile_dir = Path(__file__).resolve().parent.parent / "auth_profile"
    auth_profile_dir.mkdir(parents=True, exist_ok=True)
    ud = str(auth_profile_dir)

    try:
        with sync_playwright() as p:
            context = None
            if browser_type == "firefox":
                with suppress(Exception):
                    context = p.firefox.launch_persistent_context(
                        user_data_dir=ud,
                        headless=False,
                        viewport={"width": 1280, "height": 800},
                    )

            if context is None:
                try:
                    context = p.chromium.launch_persistent_context(
                        user_data_dir=ud,
                        channel=channel,
                        headless=False,
                        viewport={"width": 1280, "height": 800},
                    )
                except Exception:
                    context = p.chromium.launch_persistent_context(
                        user_data_dir=ud,
                        headless=False,
                        viewport={"width": 1280, "height": 800},
                    )

            page = context.new_page()
            page.goto("https://www.bilibili.com", wait_until="domcontentloaded")

            with suppress(Exception):
                page.evaluate(
                    """() => {
                        const d=document.createElement('div');
                        d.style.cssText='position:fixed;z-index:999999;top:10px;left:10px;padding:8px 12px;background:#fb7299;color:#fff;font-size:14px;border-radius:6px;font-family:sans-serif;box-shadow:0 2px 10px rgba(0,0,0,0.2);';
                        d.textContent='请在此窗口完成B站登录，登录成功后可自动关闭';
                        document.body.appendChild(d);
                    }"""
                )

            deadline = time.time() + max(30, timeout_sec)
            while time.time() < deadline:
                cookies = context.cookies("https://www.bilibili.com")
                for c in cookies:
                    if c.get("name") == "SESSDATA" and c.get("value"):
                        val = c["value"]
                        context.close()
                        return val
                time.sleep(1.0)

            context.close()
    except Exception:
        return None
    return None


def _auto_get_sessdata_via_elevation(user_agent: str | None = None) -> tuple[str | None, str | None]:
    r"""
    通过 UAC 提权启动 cookie_helper.py 进行抓取。
    返回值: (sessdata, error_code)
    error_code: None / "denied" (提权被拒绝) / "failed" (读取失败)
    """
    if s := _auto_get_sessdata_from_browsers(user_agent):
        return s, None

    import ctypes
    import tempfile
    import time

    try:
        is_admin = ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        is_admin = False

    if is_admin:
        # 如果当前已经是管理员权限，直接读取即可
        s = _auto_get_sessdata_from_browsers(user_agent)
        return s, None if s else "failed"

    # 创建一个临时文件来接收 Cookie
    temp_dir = tempfile.gettempdir()
    temp_out = Path(temp_dir) / f"mybiout_cookie_{int(time.time())}.txt"
    helper_path = Path(__file__).resolve().parent / "cookie_helper.py"

    args = f'"{helper_path}" --out "{temp_out}"'
    if user_agent:
        # 过滤特殊字符防止参数注入
        cleaned_ua = "".join(c for c in user_agent if c.isalnum() or c in " ._()/;,-")
        args += f' --ua "{cleaned_ua}"'

    try:
        # 触发 UAC 弹窗运行提权助手
        ret = ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, args, None, 0)
        if int(ret) <= 32:
            return None, "failed"

        # 轮询等待临时文件被写入（最长等待 8 秒）
        start_time = time.time()
        while time.time() - start_time < 8.0:
            if temp_out.exists():
                try:
                    sessdata = temp_out.read_text(encoding="utf-8").strip()
                    temp_out.unlink()
                    if sessdata:
                        return sessdata, None
                except Exception:
                    pass
            time.sleep(0.25)

        return None, "failed"
    except Exception as e:
        # 捕捉提权取消/拒绝错误 (ERROR_CANCELLED = 1223)
        if getattr(e, "winerror", None) == 1223 or "1223" in str(e):
            return None, "denied"
        return None, "failed"
    finally:
        if temp_out.exists():
            with suppress(Exception):
                temp_out.unlink()


def auto_get_sessdata(user_agent: str | None = None) -> str | None:
    r"""
    自动获取 SESSDATA:
    1) 首先尝试在当前普通进程中快速抓取本机浏览器 Cookie
    2) 如果失败（如数据库锁定且无管理员权限），则尝试启动管理员权限 of cookie_helper.py 进行抓取 (UAC 提权)
    3) 如果仍然失败，则打开可视化登录窗口引导用户登录后抓取
    """
    # 1. 尝试直接以普通权限读取
    if s := _auto_get_sessdata_from_browsers(user_agent):
        return s

    # 2. 普通权限读取失败，尝试以管理员权限启动 cookie_helper.py 进行抓取 (UAC 弹窗)
    s, _ = _auto_get_sessdata_via_elevation(user_agent)
    if s:
        return s

    # 3. 提权失败（或用户点击拒绝），最后退回到可视化 Playwright 登录
    return _auto_get_sessdata_via_login(user_agent=user_agent, timeout_sec=180)
