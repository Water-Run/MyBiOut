from __future__ import annotations

import ast
import re
from pathlib import Path

from fastapi.testclient import TestClient

from mybiout.pages.apis import 应用

ROOT = Path(__file__).resolve().parent.parent

_内联事件函数正则 = re.compile(
    r"\b(?:onclick|ondblclick|onchange|oninput|onblur|onkeydown)=\"[^\"]*?([\w\u4e00-\u9fff]+)\s*\("
)
_允许英文定义名 = {"format_help"}


def _树(path: str) -> ast.Module:
    return ast.parse((ROOT / path).read_text(encoding="utf-8"))


def _导入别名(path: str) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for node in ast.walk(_树(path)):
        if isinstance(node, ast.Import):
            for alias in node.names:
                aliases[alias.name] = alias.asname or alias.name
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for alias in node.names:
                aliases[f"{module}.{alias.name}"] = alias.asname or alias.name
    return aliases


def _函数名(path: str) -> set[str]:
    return {
        node.name
        for node in ast.walk(_树(path))
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef)
    }


def _英文标识符(path: Path) -> list[tuple[int, str, str]]:
    语法树 = ast.parse(path.read_text(encoding="utf-8"))
    结果: list[tuple[int, str, str]] = []
    for 节点 in ast.walk(语法树):
        if (
            isinstance(节点, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef)
            and 节点.name.isascii()
            and any(字符.isalpha() for 字符 in 节点.name)
            and not (节点.name.startswith("__") and 节点.name.endswith("__"))
            and 节点.name not in _允许英文定义名
        ):
            结果.append((节点.lineno, "定义", 节点.name))
        elif (
            isinstance(节点, ast.Name)
            and isinstance(节点.ctx, ast.Store | ast.Param)
            and 节点.id.isascii()
            and any(字符.isalpha() for 字符 in 节点.id)
            and not (节点.id.startswith("__") and 节点.id.endswith("__"))
        ):
            结果.append((节点.lineno, "名称", 节点.id))
        elif (
            isinstance(节点, ast.arg)
            and 节点.arg.isascii()
            and any(字符.isalpha() for 字符 in 节点.arg)
            and not (节点.arg.startswith("__") and 节点.arg.endswith("__"))
        ):
            结果.append((节点.lineno, "参数", 节点.arg))
    return 结果


def _中文内联事件函数(html: str) -> set[str]:
    return {name for name in _内联事件函数正则.findall(html) if re.search(r"[\u4e00-\u9fff]", name)}


def test_mybiout_python_identifiers_are_chinese() -> None:
    残留: dict[str, list[tuple[int, str, str]]] = {}
    for 路径对象 in sorted((ROOT / "mybiout").rglob("*.py")):
        if "__pycache__" in 路径对象.parts:
            continue
        当前残留 = _英文标识符(路径对象)
        if 当前残留:
            残留[str(路径对象.relative_to(ROOT))] = 当前残留

    assert 残留 == {}


def test_chinese_inline_event_handlers_are_exported_to_window() -> None:
    pages = [
        "mybiout/pages/bbdown/bbdown.html",
        "mybiout/pages/localout/localout.html",
        "mybiout/pages/man/man.html",
        "mybiout/pages/mdout/mdout.html",
        "mybiout/pages/ohmyconfig/ohmyconfig.html",
    ]

    missing_by_page: dict[str, list[str]] = {}
    for path in pages:
        html = (ROOT / path).read_text(encoding="utf-8")
        missing = sorted(
            name for name in _中文内联事件函数(html) if f"window.{name} =" not in html
        )
        if missing:
            missing_by_page[path] = missing

    assert missing_by_page == {}


def test_python_core_modules_use_chinese_import_aliases() -> None:
    expected = {
        "mybiout/__init__.py": {"sys": "系统"},
        "hatch_build.py": {"sys": "系统"},
        "mybiout/pages/utils.py": {
            "configparser": "配置解析器",
            "os": "系统",
            "tempfile": "临时文件",
            "threading": "线程",
            "contextlib.suppress": "忽略异常",
            "pathlib.Path": "路径",
        },
        "mybiout/pages/apis.py": {
            "pathlib.Path": "路径",
            "typing.Any": "任意",
            "fastapi.FastAPI": "快速应用",
            "fastapi.Path": "路径参数",
            "fastapi.Request": "请求",
            "fastapi.Response": "响应",
            "fastapi.responses.HTMLResponse": "网页响应",
            "fastapi.responses.JSONResponse": "数据响应",
            "fastapi.staticfiles.StaticFiles": "静态文件",
        },
    }

    for path, aliases in expected.items():
        actual = _导入别名(path)
        for imported, chinese_alias in aliases.items():
            assert actual.get(imported) == chinese_alias, f"{path}: {imported}"


def test_core_business_names_are_chinese() -> None:
    from mybiout import main as 主入口
    from mybiout.pages import utils as 工具
    from mybiout.pages.ohmyconfig import ohmyconfig as 设置页

    assert callable(工具.取设置)
    assert callable(工具.设设置)
    assert callable(工具.取全部设置)
    assert callable(设置页.校验并保存)
    assert callable(设置页.取设置)
    assert callable(主入口.主程序)
    assert 主入口._环境项("ffmpeg", True, "").可用 is True
    assert 主入口._取启动阻断项([]) == []
    assert 主入口._旋翼帧

    assert {"取设置", "设设置", "重置全部设置"} <= _函数名("mybiout/pages/utils.py")
    assert {"校验并保存", "浏览文件夹", "自动获取会话数据"} <= _函数名(
        "mybiout/pages/ohmyconfig/ohmyconfig.py"
    )
    assert {"首页", "取设置接口", "本地导出状态"} <= _函数名("mybiout/pages/apis.py")
    assert {"_环境项", "_服务启动状态", "_播放动画", "主程序"} <= _函数名("mybiout/main.py")


def test_main_startup_internals_keep_chinese_names() -> None:
    source = (ROOT / "mybiout/main.py").read_text(encoding="utf-8")

    forbidden = [
        "_BIN_DIR",
        "_CSI",
        "_HIDE_CUR",
        "_SHOW_CUR",
        "_CLR_SCR",
        "_RST",
        "_BOLD",
        "_BR_L",
        "_BR_M",
        "_BR_H",
        "_SPARK",
        "_MAX_PARTICLES",
        "ffmpeg_found",
        "bbdown_found",
        "biliffm4s_found",
        "for c in checks",
    ]
    for name in forbidden:
        assert name not in source, name

    expected = [
        "_取程序工具目录",
        "_控制序列引导",
        "_隐藏光标",
        "_显示光标",
        "_清屏",
        "_重置样式",
        "_加粗样式",
        "_盲文低密度",
        "_盲文中密度",
        "_盲文高密度",
        "_闪光字符",
        "_最大粒子数",
        "找到FFmpeg",
        "找到BBDown",
        "找到biliffm4s",
        "for 检查项 in 检查列表",
    ]
    for name in expected:
        assert name in source, name


def test_feature_modules_use_chinese_service_names() -> None:
    from mybiout.pages.bbdown import bbdown as 下载页
    from mybiout.pages.localout import localout as 本地页
    from mybiout.pages.man import man as 手册页
    from mybiout.pages.mdout import mdout as 文档页

    assert 本地页.视频卡片
    assert callable(本地页.取状态)
    assert callable(本地页.添加来源)
    assert 下载页.下载任务
    assert callable(下载页.取状态)
    assert callable(下载页.添加任务)
    assert 文档页.文档卡片
    assert callable(文档页.添加并获取)
    assert callable(手册页.对话)
    assert callable(手册页._构建消息)

    assert {"视频卡片", "_本地状态", "_扫描ADB设备", "添加来源", "开始导出"} <= _函数名(
        "mybiout/pages/localout/localout.py"
    )
    assert {"下载任务", "_下载状态", "_构建命令", "添加任务", "环境检查"} <= _函数名(
        "mybiout/pages/bbdown/bbdown.py"
    )
    assert {"文档卡片", "_文档状态", "添加并获取", "导出卡片", "取导出文件夹路径"} <= _函数名(
        "mybiout/pages/mdout/mdout.py"
    )
    assert {"生成胡言", "_构建消息", "_调用大模型", "流式对话SSE", "对话"} <= _函数名(
        "mybiout/pages/man/man.py"
    )


def test_external_http_contract_remains_unchanged() -> None:
    client = TestClient(应用, raise_server_exceptions=False)

    for path in ["/", "/localout", "/bbdown", "/mdout", "/ohmyconfig", "/man"]:
        response = client.get(path)
        assert response.status_code == 200, path
        assert "text/html" in response.headers["content-type"], path

    settings = client.get("/api/settings")
    assert settings.status_code == 200
    payload = settings.json()
    assert {"export", "api", "localout", "bbdown", "mdout"} <= set(payload)
    assert "path" in payload["export"]
    assert "folder" in payload["localout"]
    assert "folder" in payload["bbdown"]
    assert "folder" in payload["mdout"]

    invalid = client.post("/api/setting", content="{bad json", headers={"content-type": "application/json"})
    assert invalid.status_code == 400
    assert invalid.json() == {"ok": False, "error": "请求体不是合法 JSON"}

    missing_cover = client.get("/api/localout/cover/not-found")
    assert missing_cover.status_code == 404


def test_api_routes_import_chinese_implementations_without_renaming_paths() -> None:
    source = (ROOT / "mybiout/pages/apis.py").read_text(encoding="utf-8")

    assert '@应用.post("/api/man/chat")' in source
    assert '@应用.post("/api/man/chat-stream")' in source
    assert "/api/man/对话" not in source
    assert "from mybiout.pages.ohmyconfig.ohmyconfig import 取设置" in source
    assert "from mybiout.pages.localout.localout import 添加来源" in source
    assert "from mybiout.pages.bbdown.bbdown import 添加任务" in source
    assert "from mybiout.pages.mdout.mdout import 添加并获取" in source
    assert "from mybiout.pages.man.man import 对话" in source
    assert "from mybiout.pages.ohmyconfig import ohmyconfig as 设置模块" in source

    assert "import get_settings" not in source
    assert "import validate_and_save" not in source
    assert "import get_state" not in source
    assert "import add_task" not in source
    assert "import chat_stream_sse" not in source
    assert not re.search(r"from mybiout\.pages\..* import [A-Za-z_]+$", source, flags=re.MULTILINE)


def test_fastapi_path_parameter_names_are_framework_safe() -> None:
    不安全路径: list[str] = []
    for 路由 in 应用.routes:
        路径文本 = getattr(路由, "path", "")
        for 参数名 in re.findall(r"{([^}]+)}", 路径文本):
            if not 参数名.isascii():
                不安全路径.append(路径文本)

    assert 不安全路径 == []


def test_entry_animation_internal_script_names_are_chinese() -> None:
    js = (ROOT / "mybiout/assets/entry.js").read_text(encoding="utf-8")

    assert "const 入口速度 = 1.3" in js
    assert "const 入口变体表 = [" in js
    assert "function 生成变体(" in js
    assert "function 按毫秒加速(" in js
    assert "function 绘制模式(" in js
    assert "function 随机数(" in js

    assert "ENTRY_SPEED" not in js
    assert "ENTRY_VARIANTS" not in js
    assert "function generateVariant(" not in js
    assert "function speedMs(" not in js


def test_home_animation_uses_chinese_internal_names_but_keeps_dom_contract() -> None:
    html = (ROOT / "mybiout/pages/index.html").read_text(encoding="utf-8")

    assert 'id="github-btn"' in html
    assert 'id="overlay-t1"' in html
    assert 'id="overlay-t2"' in html
    assert 'id="flash-overlay"' in html
    assert "document.getElementById('github-btn')" in html
    assert "window.addEventListener('resize'" in html

    assert "class 爆裂粒子" in html
    assert "class 冲击波" in html
    assert "function 环形爆裂(" in html
    assert "function 彩屑爆裂(" in html
    assert "function 播放动画(" in html
    assert "function 结束动画(" in html
    assert "requestAnimationFrame(震动步进)" in html

    assert "class Burst" not in html
    assert "function playAnim(" not in html
    assert "requestAnimationFrame(step)" not in html
    assert "github-按钮" not in html
    assert "overlay-文字一" not in html
    assert "闪白-overlay" not in html


def test_settings_page_script_uses_chinese_names_and_keeps_legacy_hooks() -> None:
    html = (ROOT / "mybiout/pages/ohmyconfig/ohmyconfig.html").read_text(encoding="utf-8")

    assert "function 显示提示(" in html
    assert "async function 接口读取(" in html
    assert "async function 保存设置(" in html
    assert "async function 重置文件夹(" in html
    assert "window.showToast = 显示提示" in html
    assert "window.saveSetting = 保存设置" in html
    assert "window.resetFolder = 重置文件夹" in html

    assert "function showToast(" not in html
    assert "async function apiGet(" not in html
    assert "async function saveSetting(" not in html
    assert "function resetFolder(" not in html


def test_feature_page_inline_scripts_use_chinese_window_hooks() -> None:
    bbdown = (ROOT / "mybiout/pages/bbdown/bbdown.html").read_text(encoding="utf-8")
    mdout = (ROOT / "mybiout/pages/mdout/mdout.html").read_text(encoding="utf-8")
    man = (ROOT / "mybiout/pages/man/man.html").read_text(encoding="utf-8")

    assert "async function 添加任务(" in bbdown
    assert "window.addTask = 添加任务" in bbdown
    assert "function 渲染任务(" in bbdown
    assert "window.cancelCurrent = 取消当前" in bbdown
    assert "window.retryTask = 重试任务" in bbdown
    assert "const 取元素 = id => document.getElementById(id)" in bbdown
    assert "取元素('bg-cv')" in bbdown
    assert "let 星星组 = []" in bbdown

    assert "function 打开面板(" in mdout
    assert "window.openPanel = 打开面板" in mdout
    assert "async function 添加并获取(" in mdout
    assert "window.exportSelected = 导出选中" in mdout
    assert "function 渲染网格(" in mdout
    assert "const 面板配置 = {" in mdout
    assert "const 已选编号 = new Set()" in mdout
    assert "function 提示(" in mdout
    assert "function 转义属性(" in mdout
    assert 'id="bg-cv"' in mdout
    assert ">原文</button>" in mdout
    assert "'富文本'" in mdout

    assert "function 添加用户消息(" in man
    assert "async function 发送对话(" in man
    assert "window.sendChat = 发送对话" in man
    assert "function 渲染Markdown(" in man
    assert "function 初始化背景(" in man
    assert "const 取元素 = id => document.getElementById(id)" in man
    assert "function 提示(" in man
    assert "function 转义网页(" in man
    assert 'id="bg-cv"' in man

    assert "window.addTask = async function" not in bbdown
    assert "const $ = id => document.getElementById(id)" not in bbdown
    assert "window.openPanel = function" not in mdout
    assert "window.sendChat = async function" not in man
    assert "function escH(" not in mdout
    assert "function escAttr(" not in mdout
    assert "function toast(" not in mdout
    assert "function escH(" not in man
    assert "function toast(" not in man
    assert ">Raw</button>" not in mdout
    assert "'Rich'" not in mdout


def test_localout_inline_script_uses_chinese_window_hooks() -> None:
    html = (ROOT / "mybiout/pages/localout/localout.html").read_text(encoding="utf-8")

    assert "async function 切换下拉(" in html
    assert "window.toggleDD = 切换下拉" in html
    assert "async function 添加来源(" in html
    assert "window.doAddSource = 添加来源" in html
    assert "function 渲染卡片(" in html
    assert "function 更新进度(" in html
    assert "async function 轮询(" in html
    assert "window.startExport = 开始导出" in html
    assert "const 已选来源 = new Set(), 已选任务 = new Set()" in html
    assert "const 取元素 = id => document.getElementById(id)" in html
    assert "取元素('bg-cv')" in html

    assert "async function toggleDD(" not in html
    assert "async function doAddSource(" not in html
    assert "function cardHtml(" not in html
    assert "function updateProgress(" not in html
    assert "selSrc" not in html
    assert "selTask" not in html
    assert "const $ = id => document.getElementById(id)" not in html
