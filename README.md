# `MyBiOut`

`MyBiOut`, 即`My-Bilibili-Output`, "导出我的哔哩哔哩", 一个综合性的, 一站式开箱即用哔哩哔哩导出工具集.  

![Logo](./mybiout/assets/logo.png)

支持的功能包括:  

- **本地缓存导出**: 导出本地的哔哩哔哩视频(包括哔哩哔哩客户端的缓存和连接的Android手机的缓存), 包括爬虫获取标题等元信息  
- **可视化BBDown封装**: 下载指定链接的哔哩哔哩视频  
- **Markdown导出**: 包括导出专栏和格式化导出用户元数据(如收藏等)  

项目依赖以下开源项目:  

- [biliffm4s](https://github.com/Water-Run/-m4s-Python-biliffm4s/blob/master/biliffm4s/biliffm4s.py): 对`ffmpeg`的封装  
- [BBDown](https://github.com/nilaoda/BBDown): 知名哔哩哔哩下载工具  
- [pywebview](https://pywebview.flowrl.com/): 内嵌 Web 窗口套壳  

> 项目仅可在 Windows x64 环境下运行  

## 使用

1. 从 [GitHub Releases](https://github.com/Water-Run/MyBiOut/releases) 下载 `MyBiOut!-*.rar`  
2. 解压到任意目录  
3. 双击 **`MyBiOut!.exe`**  
4. 关闭窗口即退出  

内嵌窗口基于系统 **WebView2**. Windows 11 一般已自带; 若窗口无法打开, 安装 [WebView2 Runtime](https://developer.microsoft.com/microsoft-edge/webview2/).  

可选参数: `MyBiOut!.exe --port 2026` / `--browser`  

| 路径 | 说明 |
|---|---|
| `config.ini` | 配置文件 |
| `bin/` | `BBDown.exe` / `ffmpeg` 等外部工具 |
| `auth_profile/` | 扫码登录可选资料目录 |
| `version.txt` | 版本号 (界面底部优先读此文件) |
| `使用说明.txt` | 简要说明 |

## 打包

维护者在本机执行 (Python 3.14+)。发布包固定为 **`.rar`**：脚本会探测 PATH / 常见目录 / `tools/rar`；若没有可用的 `rar a` 创建端，会尝试 winget 或下载安装到工程 `tools/rar`（本机缓存，不进 git）。  

```cmd
python 打包.py
```

版本号为中文轨 **年月 + 月内序标** (如 `二六〇七甲` = 2026 年 7 月第 1 包; 序标 `甲乙丙丁戊己庚辛壬癸子丑`, 每月最多 12 个), 由打包脚本写入 `mybiout/version.txt`; 页面底部经 `/api/version` 读取 (优先绿色包根目录 `version.txt`).  
发布包内的 `config.ini` 为**脱敏默认配置**, 不会拷贝本机已有凭证.  
产出: `dist/release/MyBiOut!-<版本>.rar` (例 `MyBiOut!-二六〇七甲.rar`)  

重复打包会复用 PyInstaller 缓存、不强制 `pip -U`, 通常比首次快很多.

开发依赖见 `requirements.txt` (可选: `pip install -r requirements.txt`).
