r"""
apis.py 全部端点的 HTTP 契约测试

覆盖范围:
  - 6 个页面路由 (GET /)
  - 11 个设置/工具路由 (/api/settings /api/setting /api/browse-folder /api/desktop-path
                          /api/default-bili-pc-cache-path /api/reset-all-settings
                          /api/open-explorer /api/auto-sessdata /api/mdout/open-folder
                          /api/man/chat /api/man/chat-stream)
  - 19 个 LocalOut 路由
  - 9 个 BBDown 路由
  - 9 个 MdOut 路由

:file: tests/test_api_contract.py
:author: WaterRun
:time: 2026-07-08
"""

from __future__ import annotations

import json
from contextlib import suppress as 忽略异常
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from mybiout.pages import utils as 工具
from mybiout.pages.apis import 应用
from mybiout.pages.bbdown import bbdown as 下载页
from mybiout.pages.localout import localout as 本地页
from mybiout.pages.mdout import mdout as 文档页
from mybiout.pages.ohmyconfig import ohmyconfig as 设置页

# ===== 夹具 =====


@pytest.fixture
def 客户端() -> TestClient:
    r"""
    提供 raise_server_exceptions=False 的 TestClient
    """
    return TestClient(应用, raise_server_exceptions=False)


# 隔离配置 由 tests/conftest.py 的 autouse 夹具提供


@pytest.fixture(autouse=True)
def 清理全局状态() -> None:
    r"""
    每个测试前后清理 LocalOut/BBDown/MdOut 全局状态, 避免测试间污染
    """
    本地页.状态.来源卡片列表.clear()
    本地页.状态.任务卡片列表.clear()
    本地页.状态.完成卡片列表.clear()
    本地页.状态.日志列表.clear()
    本地页.状态.扫描状态 = "idle"
    本地页.状态.扫描进度 = 0.0
    本地页.状态.导出状态 = "idle"
    本地页.状态.导出进度 = 0.0
    本地页.状态.导出总数 = 0
    本地页.状态.导出完成数 = 0
    本地页.状态._已知键集合.clear()
    本地页.状态._可用键集合.clear()
    本地页.状态._扫描取消.clear()
    本地页.状态._扫描暂停.clear()
    本地页.状态._导出取消.clear()

    下载页.状态.任务列表.clear()
    下载页.状态.完成列表.clear()
    下载页.状态.日志列表.clear()
    下载页.状态._取消标记.clear()
    下载页.状态._进程 = None

    文档页.状态.卡片列表.clear()
    文档页.状态.完成列表.clear()
    文档页.状态.日志列表.clear()
    文档页.状态.选中编号 = ""
    文档页.状态._获取队列.clear()
    文档页.状态._取消标记.clear()

    yield


# ===== 页面路由 =====


@pytest.mark.parametrize("路径", ["/", "/ohmyconfig", "/localout", "/bbdown", "/mdout", "/man"])
def test_页面路由返回200_html(客户端: TestClient, 路径: str) -> None:
    r"""
    6 个页面路由均返回 200 + text/html
    """
    响应 = 客户端.get(路径)
    assert 响应.status_code == 200, 路径
    assert "text/html" in 响应.headers["content-type"], 路径


# ===== 设置相关 =====


def test_取设置接口_返回全部分区(客户端: TestClient) -> None:
    r"""
    /api/settings 返回 export/api/localout/bbdown/mdout 五个分区
    """
    响应 = 客户端.get("/api/settings")
    assert 响应.status_code == 200
    数据 = 响应.json()
    assert {"export", "api", "localout", "bbdown", "mdout"} <= set(数据.keys())


def test_保存设置_合法值返回200(客户端: TestClient) -> None:
    r"""
    /api/setting 接受合法 ffmpeg_concurrent 值
    """
    响应 = 客户端.post(
        "/api/setting",
        json={"section": "localout", "key": "ffmpeg_concurrent", "value": "5"},
    )
    assert 响应.status_code == 200
    assert 响应.json() == {"ok": True}
    写入: dict[str, str] = 工具.取全部设置()
    assert 写入["localout"]["ffmpeg_concurrent"] == "5"


def test_保存设置_非法值返回400(客户端: TestClient) -> None:
    r"""
    ffmpeg_concurrent=99 超出 1~32 范围
    """
    响应 = 客户端.post(
        "/api/setting",
        json={"section": "localout", "key": "ffmpeg_concurrent", "value": "99"},
    )
    assert 响应.status_code == 400
    数据 = 响应.json()
    assert 数据["ok"] is False
    assert "ffmpeg" in 数据["error"]


def test_保存设置_非法JSON返回400(客户端: TestClient) -> None:
    r"""
    损坏的 JSON 请求体走自定义异常处理
    """
    响应 = 客户端.post(
        "/api/setting",
        content="{bad json",
        headers={"content-type": "application/json"},
    )
    assert 响应.status_code == 400
    assert 响应.json() == {"ok": False, "error": "请求体不是合法 JSON"}


def test_保存设置_非字典体返回400(客户端: TestClient) -> None:
    r"""
    合法 JSON 但不是对象 → 200/400 取决于校验;
    当前实现对非对象 body 不会 raise _无效JSON请求体, 而是返回空字典走默认分支
    """
    响应 = 客户端.post(
        "/api/setting",
        json=["not", "a", "dict"],
    )
    # 列表 body 被 _读取数据字典 转为空字典 → 落到 case _ 接受, 返回 200
    assert 响应.status_code == 200


def test_浏览文件夹_空环境返回200(客户端: TestClient) -> None:
    r"""
    无显示器环境 tkinter 会失败, 端点仍返回 200 ok:false
    """
    响应 = 客户端.post("/api/browse-folder")
    assert 响应.status_code == 200
    # 在 headless CI 中返回 ok:false
    数据 = 响应.json()
    assert "ok" in 数据


def test_桌面路径接口_返回路径(客户端: TestClient) -> None:
    r"""
    /api/desktop-path 返回桌面下的 MyBiOut! 路径
    """
    响应 = 客户端.get("/api/desktop-path")
    assert 响应.status_code == 200
    数据 = 响应.json()
    assert "path" in 数据
    assert "Desktop" in 数据["path"] or "桌面" in 数据["path"]


def test_默认哔哩电脑缓存路径接口(客户端: TestClient) -> None:
    r"""
    /api/default-bili-pc-cache-path 返回 Videos/bilibili
    """
    响应 = 客户端.get("/api/default-bili-pc-cache-path")
    assert 响应.status_code == 200
    数据 = 响应.json()
    assert "bilibili" in 数据["path"]


def test_重置全部设置接口(客户端: TestClient) -> None:
    r"""
    /api/reset-all-settings 恢复默认值
    """
    # 先污染配置
    客户端.post(
        "/api/setting",
        json={"section": "api", "key": "key", "value": "污染值"},
    )
    assert 工具.取设置("api", "key") == "污染值"

    响应 = 客户端.post("/api/reset-all-settings")
    assert 响应.status_code == 200
    assert 响应.json() == {"ok": True}
    assert 工具.取设置("api", "key") == ""


# ===== LocalOut 路由 =====


def test_本地导出状态(客户端: TestClient) -> None:
    r"""
    /api/localout/state 返回完整快照
    """
    响应 = 客户端.get("/api/localout/state")
    assert 响应.status_code == 200
    数据 = 响应.json()
    必含键: set[str] = {
        "source_cards",
        "task_cards",
        "completed_cards",
        "logs",
        "available_keys",
        "scan_status",
        "scan_progress",
        "export_status",
        "export_progress",
        "export_total",
        "export_done",
    }
    assert 必含键 <= set(数据.keys())
    assert 数据["scan_status"] == "idle"
    assert 数据["export_status"] == "idle"


def test_本地导出环境状态(客户端: TestClient) -> None:
    r"""
    /api/localout/env-status 报告 ADB/biliffm4s/httpx 可用性
    """
    响应 = 客户端.get("/api/localout/env-status")
    assert 响应.status_code == 200
    数据 = 响应.json()
    assert {"adb", "biliffm4s", "httpx"} <= set(数据.keys())
    assert "available" in 数据["adb"]
    assert "available" in 数据["biliffm4s"]
    assert "available" in 数据["httpx"]


def test_本地导出可用来源(客户端: TestClient) -> None:
    r"""
    /api/localout/available-sources 包含 sources 和 warnings
    """
    响应 = 客户端.get("/api/localout/available-sources")
    assert 响应.status_code == 200
    数据 = 响应.json()
    assert "sources" in 数据
    assert "warnings" in 数据
    assert isinstance(数据["sources"], list)
    assert isinstance(数据["warnings"], list)
    # 浏览按钮是固定项
    编号列表: list[str] = [项.get("id", "") for 项 in 数据["sources"]]
    assert "browse" in 编号列表


def test_本地导出浏览本地(客户端: TestClient) -> None:
    r"""
    /api/localout/browse-local 端点存在
    """
    响应 = 客户端.post("/api/localout/browse-local")
    assert 响应.status_code == 200
    assert "ok" in 响应.json()


def test_本地导出添加来源_未知类型(客户端: TestClient) -> None:
    r"""
    非 pc/drive/adb/local 类型被拒绝
    """
    响应 = 客户端.post(
        "/api/localout/add-source",
        json={"source_type": "bogus", "path": ""},
    )
    assert 响应.status_code == 200
    数据 = 响应.json()
    assert 数据["ok"] is False
    assert "未知" in 数据["error"]


def test_本地导出添加来源_缺路径(客户端: TestClient) -> None:
    r"""
    pc/drive/local 必须有真实目录
    """
    响应 = 客户端.post(
        "/api/localout/add-source",
        json={"source_type": "pc", "path": ""},
    )
    assert 响应.status_code == 200
    数据 = 响应.json()
    assert 数据["ok"] is False
    assert "路径不存在" in 数据["error"]


def test_本地导出添加来源_ADB缺序列号(客户端: TestClient) -> None:
    r"""
    adb 类型必须提供序列号
    """
    响应 = 客户端.post(
        "/api/localout/add-source",
        json={"source_type": "adb", "serial": ""},
    )
    assert 响应.status_code == 200
    数据 = 响应.json()
    assert 数据["ok"] is False
    assert "序列号" in 数据["error"]


def test_本地导出添加来源_ADB未知包名(客户端: TestClient) -> None:
    r"""
    adb 包名必须是白名单内
    """
    响应 = 客户端.post(
        "/api/localout/add-source",
        json={"source_type": "adb", "serial": "X", "package": "unknown.pkg"},
    )
    assert 响应.status_code == 200
    数据 = 响应.json()
    assert 数据["ok"] is False
    assert "未知" in 数据["error"]


def test_本地导出添加来源_已有扫描返回错误(客户端: TestClient) -> None:
    r"""
    已有扫描进行中时拒绝新扫描
    """
    本地页.状态.扫描状态 = "scanning"
    响应 = 客户端.post(
        "/api/localout/add-source",
        json={"source_type": "pc", "path": str(Path.cwd().resolve())},
    )
    assert 响应.status_code == 200
    数据 = 响应.json()
    assert 数据["ok"] is False
    assert "扫描" in 数据["error"]
    本地页.状态.扫描状态 = "idle"  # 显式复位


@pytest.mark.parametrize("动作", ["pause-scan", "resume-scan", "cancel-scan", "cancel-export"])
def test_本地导出扫描控制_返回200(客户端: TestClient, 动作: str) -> None:
    r"""
    4 个扫描/导出控制端点
    """
    响应 = 客户端.post(f"/api/localout/{动作}")
    assert 响应.status_code == 200
    assert 响应.json() == {"ok": True}


@pytest.mark.parametrize("动作", [
    "add-to-tasks",
    "remove-source",
    "remove-tasks",
    "clear-source",
    "clear-tasks",
    "clear-completed",
])
def test_本地导出任务管理_返回200(客户端: TestClient, 动作: str) -> None:
    r"""
    6 个任务管理端点
    """
    响应 = 客户端.post(f"/api/localout/{动作}", json={})
    assert 响应.status_code == 200
    assert "ok" in 响应.json()


def test_本地导出开始导出_空任务(客户端: TestClient) -> None:
    r"""
    没有待导出任务时返回 ok:false
    """
    响应 = 客户端.post("/api/localout/start-export", json={})
    assert 响应.status_code == 200
    数据 = 响应.json()
    assert 数据["ok"] is False


def test_本地导出开始导出_已有导出返回错误(客户端: TestClient) -> None:
    r"""
    正在导出时拒绝再次启动
    """
    本地页.状态.导出状态 = "exporting"
    响应 = 客户端.post("/api/localout/start-export", json={"card_ids": ["x"]})
    assert 响应.status_code == 200
    数据 = 响应.json()
    assert 数据["ok"] is False
    assert "导出" in 数据["error"]


def test_本地导出封面_不存在返回404(客户端: TestClient) -> None:
    r"""
    不存在的 card_id 走 404 分支
    """
    响应 = 客户端.get("/api/localout/cover/not-exists-id-xyz")
    assert 响应.status_code == 404


# ===== BBDown 路由 =====


def test_下载状态(客户端: TestClient) -> None:
    r"""
    /api/bbdown/state 返回 tasks/completed/logs/is_downloading
    """
    响应 = 客户端.get("/api/bbdown/state")
    assert 响应.status_code == 200
    数据 = 响应.json()
    必含键: set[str] = {"tasks", "completed", "logs", "is_downloading"}
    assert 必含键 <= set(数据.keys())
    assert 数据["is_downloading"] is False


def test_下载环境检查(客户端: TestClient) -> None:
    r"""
    /api/bbdown/env-check 报告 BBDown/ffmpeg/SESSDATA 状态
    """
    响应 = 客户端.get("/api/bbdown/env-check")
    assert 响应.status_code == 200
    数据 = 响应.json()
    必含键: set[str] = {"bbdown_available", "bbdown_path", "ffmpeg_available", "ffmpeg_path", "has_sessdata"}
    assert 必含键 <= set(数据.keys())


def test_下载添加任务_空URL返回400(客户端: TestClient) -> None:
    r"""
    空 URL 被拒绝, 走 400
    """
    响应 = 客户端.post("/api/bbdown/add", json={"url": ""})
    assert 响应.status_code == 400
    assert 响应.json()["ok"] is False


def test_下载添加任务_合法URL(客户端: TestClient) -> None:
    r"""
    合法 URL; 若 BBDown 不在 PATH/wheel 内, 返回 400 ok:false
    若可用则返回 200 + task_id. 两种结果均视为端点工作正常
    """
    响应 = 客户端.post(
        "/api/bbdown/add",
        json={"url": "https://www.bilibili.com/video/BV1xx411c7mD"},
    )
    assert 响应.status_code in (200, 400)
    数据 = 响应.json()
    if 响应.status_code == 200:
        assert 数据["ok"] is True
        assert "task_id" in 数据
    else:
        assert 数据["ok"] is False


def test_下载取消当前(客户端: TestClient) -> None:
    r"""
    /api/bbdown/cancel 即使没有运行中的任务也返回 200
    """
    响应 = 客户端.post("/api/bbdown/cancel")
    assert 响应.status_code == 200
    assert 响应.json() == {"ok": True}


def test_下载重试任务_不存在(客户端: TestClient) -> None:
    r"""
    重试不存在的任务返回 ok:false
    """
    响应 = 客户端.post("/api/bbdown/retry", json={"task_id": "nonexistent"})
    assert 响应.status_code == 200
    数据 = 响应.json()
    assert 数据["ok"] is False


@pytest.mark.parametrize("动作", [
    "remove",
    "clear-completed",
    "clear-failed",
    "clear-queue",
])
def test_下载任务管理_返回200(客户端: TestClient, 动作: str) -> None:
    r"""
    4 个 BBDown 任务管理端点
    """
    响应 = 客户端.post(f"/api/bbdown/{动作}", json={"task_id": "x"})
    assert 响应.status_code == 200
    assert "ok" in 响应.json()


# ===== MdOut 路由 =====


def test_文档导出状态(客户端: TestClient) -> None:
    r"""
    /api/mdout/state 返回完整卡片列表
    """
    响应 = 客户端.get("/api/mdout/state")
    assert 响应.status_code == 200
    数据 = 响应.json()
    必含键: set[str] = {"cards", "completed", "logs", "selected_id", "selected_markdown"}
    assert 必含键 <= set(数据.keys())


def test_文档导出解析_空文本(客户端: TestClient) -> None:
    r"""
    空字符串 → unknown
    """
    响应 = 客户端.post("/api/mdout/parse", json={"text": ""})
    assert 响应.status_code == 200
    assert 响应.json()["type"] == "unknown"


def test_文档导出解析_裸BV号(客户端: TestClient) -> None:
    r"""
    纯 BV 号文本
    """
    响应 = 客户端.post("/api/mdout/parse", json={"text": "BV1xx411c7mD"})
    assert 响应.status_code == 200
    数据 = 响应.json()
    assert 数据["type"] == "video"
    assert 数据["id_type"] == "bvid"
    assert 数据["id_value"] == "BV1xx411c7mD"


def test_文档导出解析_完整BV链接(客户端: TestClient) -> None:
    r"""
    完整 BV 链接
    """
    响应 = 客户端.post(
        "/api/mdout/parse",
        json={"text": "https://www.bilibili.com/video/BV1xx411c7mD?p=1"},
    )
    assert 响应.status_code == 200
    数据 = 响应.json()
    assert 数据["type"] == "video"
    assert 数据["id_value"] == "BV1xx411c7mD"


def test_文档导出解析_裸AV号(客户端: TestClient) -> None:
    r"""
    纯 av 号
    """
    响应 = 客户端.post("/api/mdout/parse", json={"text": "av1700000001"})
    assert 响应.status_code == 200
    数据 = 响应.json()
    assert 数据["type"] == "video"
    assert 数据["id_type"] == "avid"
    assert 数据["id_value"] == "1700000001"


def test_文档导出解析_专栏(客户端: TestClient) -> None:
    r"""
    cv 专栏
    """
    响应 = 客户端.post(
        "/api/mdout/parse",
        json={"text": "https://www.bilibili.com/read/cv12345678"},
    )
    assert 响应.status_code == 200
    数据 = 响应.json()
    assert 数据["type"] == "article"
    assert 数据["id_value"] == "12345678"


def test_文档导出解析_用户空间(客户端: TestClient) -> None:
    r"""
    space.bilibili.com/UID
    """
    响应 = 客户端.post(
        "/api/mdout/parse",
        json={"text": "https://space.bilibili.com/114514"},
    )
    assert 响应.status_code == 200
    数据 = 响应.json()
    assert 数据["type"] == "user"
    assert 数据["id_value"] == "114514"


def test_文档导出解析_纯数字视为UID(客户端: TestClient) -> None:
    r"""
    1-15 位纯数字 → user
    """
    响应 = 客户端.post("/api/mdout/parse", json={"text": "12345"})
    assert 响应.status_code == 200
    assert 响应.json()["type"] == "user"


def test_文档导出解析_完全无法识别(客户端: TestClient) -> None:
    r"""
    既非 URL 也非 BV/av/cv/UID 的字符串
    """
    响应 = 客户端.post("/api/mdout/parse", json={"text": "随机文本XYZ"})
    assert 响应.status_code == 200
    assert 响应.json()["type"] == "unknown"


def test_文档导出添加_无法识别返回400(客户端: TestClient) -> None:
    r"""
    无法识别的输入 → 400
    """
    响应 = 客户端.post("/api/mdout/add", json={"text": "随机文本XYZ"})
    assert 响应.status_code == 400
    assert 响应.json()["ok"] is False


def test_文档导出添加_合法BV返回200(客户端: TestClient) -> None:
    r"""
    合法 BV → 200 + card_id (后台异步获取, 状态可能 pending 也可能 ready)
    """
    响应 = 客户端.post("/api/mdout/add", json={"text": "BV1xx411c7mD"})
    assert 响应.status_code == 200
    数据 = 响应.json()
    assert 数据["ok"] is True
    assert "card_id" in 数据


@pytest.mark.parametrize("动作", [
    "select",
    "export",
    "export-all",
    "remove",
    "clear",
    "clear-completed",
])
def test_文档导出操作_返回200(客户端: TestClient, 动作: str) -> None:
    r"""
    6 个 MdOut 操作端点
    """
    响应 = 客户端.post(f"/api/mdout/{动作}", json={"card_ids": []})
    assert 响应.status_code == 200
    assert "ok" in 响应.json()


def test_文档导出全部_无就绪返回okfalse(客户端: TestClient) -> None:
    r"""
    没有 ready 卡片时返回 ok:false
    """
    响应 = 客户端.post("/api/mdout/export-all")
    assert 响应.status_code == 200
    数据 = 响应.json()
    assert 数据["ok"] is False


def test_文档导出打开目录(客户端: TestClient) -> None:
    r"""
    /api/mdout/open-folder 至少返回 200 (在 Windows 上可调起 explorer, 在 CI 静默失败)
    """
    响应 = 客户端.post("/api/mdout/open-folder")
    assert 响应.status_code == 200
    数据 = 响应.json()
    assert "ok" in 数据


# ===== Man 路由 =====


def test_手册对话_空提示词返回200(客户端: TestClient) -> None:
    r"""
    空 prompt → ok:false
    """
    响应 = 客户端.post("/api/man/chat", json={"prompt": ""})
    assert 响应.status_code == 200
    数据 = 响应.json()
    assert 数据["ok"] is False


def test_手册对话_直接说模式触发bullshit(客户端: TestClient) -> None:
    r"""
    force_bs=True 走狗屁不通生成器
    """
    响应 = 客户端.post(
        "/api/man/chat",
        json={"prompt": "测试问题", "force_bs": True},
    )
    assert 响应.status_code == 200
    数据 = 响应.json()
    assert 数据["ok"] is True
    assert 数据["source"] == "bullshit"


def test_手册流式对话_空提示词返回error事件(客户端: TestClient) -> None:
    r"""
    /api/man/chat-stream 空 prompt → SSE 事件含 error
    """
    响应 = 客户端.post("/api/man/chat-stream", json={"prompt": ""})
    assert 响应.status_code == 200
    assert "text/event-stream" in 响应.headers["content-type"]
    文本: str = 响应.text
    assert "data:" in 文本
    # 解析首个 data 行
    首行: str = next(行 for 行 in 文本.split("\n") if 行.startswith("data:"))
    负载: dict = json.loads(首行[5:].strip())
    assert "error" in 负载


def test_手册流式对话_无APIKey降级bullshit(客户端: TestClient) -> None:
    r"""
    未配置 API Key 时, 流式对话走降级路径 → source:bullshit
    """
    响应 = 客户端.post(
        "/api/man/chat-stream",
        json={"prompt": "LocalOut 怎么用"},
    )
    assert 响应.status_code == 200
    文本: str = 响应.text
    # 找 done 行确认 source 字段
    assert "bullshit" in 文本
    # 解析所有 data 行
    负载列表: list[dict] = []
    for 行 in 文本.split("\n"):
        if 行.startswith("data:"):
            with 忽略异常(json.JSONDecodeError):
                负载列表.append(json.loads(行[5:].strip()))
    完成事件: dict = next((p for p in 负载列表 if p.get("done")), {})
    assert 完成事件.get("source") == "bullshit"


# ===== 工具路由 =====


def test_打开资源管理器_空路径(客户端: TestClient) -> None:
    r"""
    /api/open-explorer 空 path → ok:false
    """
    响应 = 客户端.post("/api/open-explorer", json={"path": ""})
    assert 响应.status_code == 200
    数据 = 响应.json()
    assert 数据["ok"] is False


def test_打开资源管理器_不存在路径(客户端: TestClient) -> None:
    r"""
    /api/open-explorer 不存在的 path → ok:false
    """
    响应 = 客户端.post(
        "/api/open-explorer",
        json={"path": "Z:/nope/nope/nope/xyz"},
    )
    assert 响应.status_code == 200
    数据 = 响应.json()
    assert 数据["ok"] is False


@pytest.mark.parametrize("动作", ["check_direct", "check_elevated"])
def test_自动会话数据_拒绝旧的浏览器提取动作(客户端: TestClient, 动作: str) -> None:
    r"""
    旧的 check_direct / check_elevated 动作必须返回 status:failed
    """
    响应 = 客户端.post("/api/auto-sessdata", json={"action": 动作})
    assert 响应.status_code == 200
    数据 = 响应.json()
    assert 数据["status"] == "failed"
    assert "sessdata" not in 数据


def test_自动会话数据_未指定动作走launch_login(
    客户端: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    r"""
    默认 action=launch_login, 缺 playwright 时返回 failed
    """
    monkeypatch.setattr(设置页, "通过登录自动取会话数据", lambda *_a, **_kw: None)
    响应 = 客户端.post("/api/auto-sessdata", json={})
    assert 响应.status_code == 200
    数据 = 响应.json()
    assert 数据["status"] == "failed"


# ===== 全局: 路由元信息完整性 =====


def test_有body的POST端点拒绝非法JSON(客户端: TestClient) -> None:
    r"""
    有 Request body 参数的 POST 端点对损坏的 JSON body 返回 400 (走 _无效JSON请求体 处理器)
    下列端点 body 非必填或无 body 参数, 不在此覆盖:
      /api/browse-folder, /api/localout/browse-local, /api/localout/pause-scan,
      /api/localout/resume-scan, /api/localout/cancel-scan, /api/localout/clear-source,
      /api/localout/clear-tasks, /api/localout/clear-completed, /api/localout/cancel-export,
      /api/bbdown/cancel, /api/bbdown/clear-completed, /api/bbdown/clear-failed,
      /api/bbdown/clear-queue, /api/mdout/export-all, /api/mdout/clear,
      /api/mdout/clear-completed, /api/reset-all-settings
    """
    有body路径: list[str] = [
        "/api/setting",
        "/api/localout/add-source",
        "/api/localout/add-to-tasks",
        "/api/localout/remove-source",
        "/api/localout/remove-tasks",
        "/api/localout/start-export",
        "/api/bbdown/add",
        "/api/bbdown/retry",
        "/api/bbdown/remove",
        "/api/mdout/parse",
        "/api/mdout/add",
        "/api/mdout/select",
        "/api/mdout/export",
        "/api/mdout/remove",
        "/api/man/chat",
        "/api/man/chat-stream",
        "/api/open-explorer",
        "/api/auto-sessdata",
    ]
    for 路径 in 有body路径:
        响应 = 客户端.post(
            路径,
            content="{not valid",
            headers={"content-type": "application/json"},
        )
        # 不应该返回 500; 400 走 _无效JSON请求体 处理器
        assert 响应.status_code == 400, f"{路径} 返回 {响应.status_code}"


def test_所有路径参数都是ascii安全(客户端: TestClient) -> None:
    r"""
    FastAPI 路径参数名必须为 ASCII, 避免某些 ASGI 服务器兼容问题
    """
    for 路由 in 应用.routes:
        路径: str = getattr(路由, "path", "")
        for 参数名 in __import__("re").findall(r"\{([^}]+)\}", 路径):
            assert 参数名.isascii(), f"非 ASCII 路径参数: {路径} -> {参数名}"
