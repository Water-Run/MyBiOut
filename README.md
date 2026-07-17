# `MyBiOut`

`MyBiOut`, 即`My-Bilibili-Output`, "导出我的哔哩哔哩", 一个综合性的, 一站式开箱即用哔哩哔哩导出工具集.  

![Logo](./mybiout/assets/logo.png)

支持的功能包括:  

- **本地缓存导出**: 导出本地的哔哩哔哩视频(包括哔哩哔哩客户端的缓存和连接的Android手机的缓存), 包括爬虫获取标题等元信息  
- **可视化BBDown封装**: 下载指定链接的哔哩哔哩视频  
- **Markdown导出**: 包括导出专栏和格式化导出用户元数据(如收藏等)  

> **推荐普通用户使用绿色版**: 解压后双击 `MyBiOut.exe` 即可, 无需安装 Python.  
> 目标环境: **Windows 11 x64** (兼容 Windows 10 x64 + WebView2).

项目依赖以下开源项目:  

- [biliffm4s](https://github.com/Water-Run/-m4s-Python-biliffm4s/blob/master/biliffm4s/biliffm4s.py): 对`ffmpeg`的封装  
- [BBDown](https://github.com/nilaoda/BBDown): 知名哔哩哔哩下载工具  
- [pywebview](https://pywebview.flowrl.com/): 内嵌 Web 窗口套壳  

> 项目仅可在 Windows x64 环境下运行  

---

## 绿色版 (推荐 · 双击运行)

1. 从 [GitHub Releases](https://github.com/Water-Run/MyBiOut/releases) 下载绿色包 zip  
2. 解压到任意目录 (可放 U 盘, 删除文件夹即卸载)  
3. 双击 **`MyBiOut.exe`**  
4. 关闭窗口即退出  

内嵌窗口基于系统 **WebView2**. Windows 11 一般已自带; 若窗口无法打开, 请安装 [WebView2 Runtime](https://developer.microsoft.com/microsoft-edge/webview2/).  

绿色包旁路目录:

| 路径 | 说明 |
|---|---|
| `config.ini` | 配置 (与 pip 版语义相同) |
| `bin/` | `BBDown.exe` / `ffmpeg` 等外部工具 |
| `auth_profile/` | 扫码登录可选资料目录 |

可选命令行:

```cmd
MyBiOut.exe --port 2026
MyBiOut.exe --browser
MyBiOut.exe --browser --no-animation
```

- `--browser`: 使用系统浏览器而非内嵌窗口  
- `--port`: 指定本地端口 (默认 `23333`)  
- `--no-animation`: 跳过终端启动动画  

本地服务仍绑定 `http://127.0.0.1:端口`, **HTTP/API 协议与网页版一致**.  

详细说明见 [docs/绿色版.md](./docs/绿色版.md).  

### 自行构建绿色包

```powershell
powershell -ExecutionPolicy Bypass -File scripts/build_green.ps1
```

产出目录: `dist/MyBiOut-green/`  

---

## 开发者 / pip 安装

需要标准 Python 环境 (**3.14+**, Windows x64). 项目发布在 PyPI:

```cmd
pip install mybiout
```

启动 (不区分大小写):

```cmd
MyBiOut!
```

或:

```cmd
python -m mybiout
```

默认在本机 `23333` 端口启动服务, 并优先打开**内嵌 Web 窗口**; 若未安装 `pywebview` 则回退系统浏览器.  
保持进程运行以维持服务; 关闭窗口 (或终端 `Ctrl+C`) 即退出.  

手动访问:

```url
http://localhost:23333
```

切换端口:

```cmd
MyBiOut! --port 2026
```

强制系统浏览器模式:

```cmd
MyBiOut! --browser
```

---

## 测试

```cmd
pip install -e ".[dev]"
pytest
```

- Windows 11  
- 小米13(Hyper OS 3), 一加8(原生Android 15)

---

## 协议与实现边界

重构为绿色版时 **不改变** 既有页面路由与 `/api/*` 契约; 契约测试见 `tests/test_api_contract.py`.  
变更的是启动方式、窗口壳与便携路径解析, 详见 [docs/绿色版.md](./docs/绿色版.md).  
