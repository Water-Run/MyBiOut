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

> 发布形态面向 **Windows 11 x64** 绿色包（亦可能在 Win10 x64 上运行，但不作保证）  

## 使用

1. 从 [GitHub Releases](https://github.com/Water-Run/MyBiOut/releases) 下载 `MyBiOut! *.rar`（例 `MyBiOut! 二六〇七甲.rar`）  
2. 解压到任意目录（包内含 `MyBiOut!/` 程序目录、`README.md`、`LICENSE`）  
3. 进入 **`MyBiOut!`** 目录，双击 **`MyBiOut!.exe`**  
4. 关闭窗口即退出  

内嵌窗口基于系统 **WebView2**. Windows 11 一般已自带; 若窗口无法打开, 安装 [WebView2 Runtime](https://developer.microsoft.com/microsoft-edge/webview2/).  

绿色包 `bin/` **随程序分发** `BBDown.exe`、`ffmpeg.exe`、`adb.exe`（及 ADB 配套 dll），一般无需再装系统 PATH 工具。内嵌窗口依赖系统 **WebView2**（Win11 一般自带）。  

若缺工具或 WebView2 起不来：启动时**弹提示即可**，程序仍尽量打开（可回退浏览器）；对应功能可能不可用。  

可选参数: `MyBiOut!.exe --port 2026`；`--browser` 仅调试用（默认内嵌窗口，绿色包不自动开浏览器）。

| 路径 | 说明 |
|---|---|
| `config.ini` | 配置文件 |
| `bin/` | 随包工具：`BBDown.exe` / `ffmpeg.exe` / `adb.exe` |
| `auth_profile/` | 扫码登录可选资料目录 |
| `version.txt` | 版本号 (界面底部优先读此文件) |
| `使用说明.txt` | 简要说明 |

## 打包

维护者在本机执行 (Python 3.14+)。发布包固定为 **`.rar`**：脚本会探测 PATH / 常见目录 / `tools/rar`；若没有可用的 `rar a` 创建端，会尝试 winget 或下载安装到工程 `tools/rar`（本机缓存，不进 git）。  

```cmd
python 打包.py
python 打包.py 重来
```

版本号为中文轨 **年月 + 月内序标** (如 `二六〇七甲` = 2026 年 7 月第 1 包; 序标 `甲乙丙丁戊己庚辛壬癸子丑`, 每月最多 12 个), 由打包脚本写入 `mybiout/version.txt`; 页面底部经 `/api/version` 读取 (优先绿色包根目录 `version.txt`).  
本月满 12 个会提示「受不了版本号溢出来了.... / 之后的版本下个月再来编译吧~」并退出; `python 打包.py 重来` 将计时归零, **下次**打包从本月「甲」起算.  
发布包内的 `config.ini` 为**脱敏默认配置**, 不会拷贝本机已有凭证.  
产出: `打包结果/MyBiOut! <版本>.rar` (例 `MyBiOut! 二六〇七甲.rar`；空格与 `!` 均保留)。包内顶层为 `MyBiOut!/` + `README.md` + `LICENSE`。  

重复打包会复用 PyInstaller 缓存、不强制 `pip -U`, 通常比首次快很多.

开发依赖见 `requirements.txt` (可选: `pip install -r requirements.txt`).
