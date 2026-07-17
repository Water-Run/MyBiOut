# `MyBiOut`

`MyBiOut`, 即`My-Bilibili-Output`, "导出我的哔哩哔哩", 一个综合性的, 一站式开箱即用哔哩哔哩导出工具集.  

![Logo](./mybiout/assets/logo.png)

**发行形态: 仅绿色版** — 解压后双击 `MyBiOut.exe` 即可使用, 无需安装 Python.  
目标环境: **Windows 11 x64** (兼容 Windows 10 x64 + WebView2).

支持的功能包括:  

- **本地缓存导出**: 导出本地的哔哩哔哩视频(包括哔哩哔哩客户端的缓存和连接的Android手机的缓存), 包括爬虫获取标题等元信息  
- **可视化BBDown封装**: 下载指定链接的哔哩哔哩视频  
- **Markdown导出**: 包括导出专栏和格式化导出用户元数据(如收藏等)  

项目依赖以下开源项目:  

- [biliffm4s](https://github.com/Water-Run/-m4s-Python-biliffm4s/blob/master/biliffm4s/biliffm4s.py): 对`ffmpeg`的封装  
- [BBDown](https://github.com/nilaoda/BBDown): 知名哔哩哔哩下载工具  
- [pywebview](https://pywebview.flowrl.com/): 内嵌 Web 窗口套壳  

> 项目仅可在 Windows x64 环境下运行  

---

## 使用 (绿色版)

1. 从 [GitHub Releases](https://github.com/Water-Run/MyBiOut/releases) 下载 `MyBiOut-*.rar`  
2. 解压到任意目录 (可放 U 盘; 删除文件夹即卸载)  
3. 双击 **`MyBiOut.exe`**  
4. 关闭窗口即退出  

内嵌窗口基于系统 **WebView2**. Windows 11 一般已自带; 若窗口无法打开, 请安装 [WebView2 Runtime](https://developer.microsoft.com/microsoft-edge/webview2/).  

| 路径 | 说明 |
|---|---|
| `config.ini` | 配置文件 |
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

本地服务绑定 `http://127.0.0.1:端口`. 更多说明见 [docs/绿色版.md](./docs/绿色版.md).  

---

## 打包发布版

在仓库根目录**双击**或运行:

```cmd
打包.bat
```

流程: 安装构建依赖 → PyInstaller → 组装绿色目录 → 生成 **`.rar` 发布包**.

| 产出 | 路径 |
|---|---|
| 绿色目录 | `dist\MyBiOut-green\` |
| 发布 RAR | `dist\release\MyBiOut-<版本>.rar` |

要求:

- Windows + **Python 3.14+** (仅打包机需要)  
- **WinRAR** (`Rar.exe`, 用于生成 `.rar`)  

---

## 开发与测试

源码仍以 Python 实现; 开发调试可在仓库根目录:

```cmd
pip install -e ".[dev]"
python -m mybiout
pytest
```

- Windows 11  
- 小米13(Hyper OS 3), 一加8(原生Android 15)  
