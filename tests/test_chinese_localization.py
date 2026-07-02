from __future__ import annotations

import ast
import re
from pathlib import Path

from fastapi.testclient import TestClient

from mybiout.pages.apis import app

ROOT = Path(__file__).resolve().parent.parent


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


def test_core_business_names_are_chinese_with_english_compatibility_aliases() -> None:
    from mybiout import main as 主入口
    from mybiout.pages import utils as 工具
    from mybiout.pages.ohmyconfig import ohmyconfig as 设置页

    assert 工具.get_setting is 工具.取设置
    assert 工具.set_setting is 工具.设设置
    assert 工具.get_all_settings is 工具.取全部设置
    assert 设置页.validate_and_save is 设置页.校验并保存
    assert 设置页.get_settings is 设置页.取设置
    assert 主入口.main is 主入口.主程序
    assert 主入口._EnvItem is 主入口._环境项
    assert 主入口._get_startup_blockers is 主入口._取启动阻断项
    assert 主入口._ROTORS is 主入口._旋翼帧

    assert {"取设置", "设设置", "重置全部设置"} <= _函数名("mybiout/pages/utils.py")
    assert {"校验并保存", "浏览文件夹", "自动获取会话数据"} <= _函数名(
        "mybiout/pages/ohmyconfig/ohmyconfig.py"
    )
    assert {"首页", "取设置接口", "本地导出状态"} <= _函数名("mybiout/pages/apis.py")
    assert {"_环境项", "_服务启动状态", "_播放动画", "主程序"} <= _函数名("mybiout/main.py")


def test_feature_modules_use_chinese_service_names_with_compatibility_aliases() -> None:
    from mybiout.pages.bbdown import bbdown as 下载页
    from mybiout.pages.localout import localout as 本地页
    from mybiout.pages.man import man as 手册页
    from mybiout.pages.mdout import mdout as 文档页

    assert 本地页.VideoCard is 本地页.视频卡片
    assert 本地页.get_state is 本地页.取状态
    assert 本地页.add_source is 本地页.添加来源
    assert 下载页.BBDownTask is 下载页.下载任务
    assert 下载页.get_state is 下载页.取状态
    assert 下载页.add_task is 下载页.添加任务
    assert 文档页.MdCard is 文档页.文档卡片
    assert 文档页.add_and_fetch is 文档页.添加并获取
    assert 手册页.chat is 手册页.对话
    assert 手册页._build_messages is 手册页._构建消息

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
    client = TestClient(app, raise_server_exceptions=False)

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
