# `MyBiOut`

`MyBiOut`, 即`My-Bilibili-Output`, "导出我的哔哩哔哩", 一个综合性的, 一站式开箱即用哔哩哔哩导出工具集.  

![Logo](./mybiout/assets/logo.png)

支持的功能包括:  

- **本地缓存导出与恢复**：导出电脑或 Android 手机中的哔哩哔哩缓存，支持智能去重与元文件归档；恢复时可递归扫描改名后的目录，无需导出索引，并将同一 avid 的多个分集合并后批量导入新的 ADB 手机
- **可视化 BBDown 封装**：按单条或批量链接下载视频，可显式下载 AI 字幕；下载镜像不支持多线程时会自动切换单线程重试，并清理本次失败残片
- **Markdown 导出**：导出视频、用户与完整收藏夹元数据，也能逐篇批量导出 `rl` 专栏文集

项目依赖以下开源项目:  

- [biliffm4s](https://github.com/Water-Run/-m4s-Python-biliffm4s/blob/master/biliffm4s/biliffm4s.py): 对`ffmpeg`的封装  
- [BBDown](https://github.com/nilaoda/BBDown): 知名哔哩哔哩下载工具  
- [pywebview](https://pywebview.flowrl.com/): 内嵌 Web 窗口套壳  

> 发布形态：**Windows 11 x64** 绿色包（`.rar`）与 **Linux x64** 绿色包（`.tar.gz`）。Win10 x64 / 常见发行版也可跑，但不作保证。  

## 使用

### Windows

1. 从 [GitHub Releases](https://github.com/Water-Run/MyBiOut/releases) 下载 Windows x64 版 `MyBiOut.rar`（当前版本：二六〇八丙）
2. 解压到任意目录（包内含 `MyBiOut!/` 程序目录、`README.txt`、`LICENSE`）  
3. 进入 **`MyBiOut!`** 目录，双击 **`MyBiOut!.exe`**  
4. 关闭窗口即退出  

内嵌窗口基于系统 **WebView2**。Windows 11 一般已自带; 若窗口无法打开, 安装 [WebView2 Runtime](https://developer.microsoft.com/microsoft-edge/webview2/).  

绿色包 `bin/` **随程序分发** `BBDown.exe`、`ffmpeg.exe`、`adb.exe`（及 ADB 配套 dll）。  

可选参数：`MyBiOut!.exe --port 2026`；`--browser` 使用系统浏览器。端口被占用时会提示一键改用可用端口，不会结束占用端口的其他程序。

### Linux

1. 下载 Linux x64 版 `MyBiOut-linux-x64.tar.gz`，解压后进入 `MyBiOut!/`
2. 执行 `./MyBiOut!`（需可执行位；内嵌窗口依赖 GTK + WebKit，如 `webkit2gtk`）  
3. 若窗口起不来：`./MyBiOut! --browser`  

开发态：`pip install -r requirements.txt` 后 `python -m mybiout`（无 pywebview 时自动回退系统浏览器）。  

绿色包 `bin/` 随发 `BBDown`、`ffmpeg`、`adb`（无 `.exe` 后缀）。也可使用系统 PATH 中的同名工具。  

若缺工具或窗口运行时：启动时**弹提示即可**，程序仍尽量打开；对应功能可能不可用。

| 路径 | 说明 |
|---|---|
| `config.ini` | 配置文件 |
| `bin/` | 随包工具：BBDown / ffmpeg / adb |
| `auth_profile/` | 扫码登录可选资料目录 |
| `version.txt` | 版本号 (界面底部优先读此文件) |
| `使用说明.txt` | 简要说明 |

## 打包

维护者在本机执行 (Python 3.14+)。Windows 发布包为 **`.rar`**（脚本会探测 / 补齐 `rar a`）；Linux 发布包为 **`.tar.gz`**。  

```
python 打包.py
python 打包.py 重来
```

版本号为中文轨 **年月 + 月内序标** (如 `二六〇七甲` = 2026 年 7 月第 1 包; 序标 `甲乙丙丁戊己庚辛壬癸子丑`, 每月最多 12 个), 由打包脚本写入 `mybiout/version.txt`; 页面底部经 `/api/version` 读取 (优先绿色包根目录 `version.txt`).  
本月满 12 个会提示「受不了版本号溢出来了.... / 之后的版本下个月再来编译吧~」并退出; `python 打包.py 重来` 将计时归零, **下次**打包从本月「甲」起算.  
发布包内的 `config.ini` 为**脱敏默认配置**, 不会拷贝本机已有凭证.  
产出：Windows 为 `打包结果/MyBiOut! <版本>.rar`，Linux 为 `打包结果/MyBiOut! <版本>.tar.gz`。包内顶层为 `MyBiOut!/` + `README.txt` + `LICENSE`。

重复打包会复用 PyInstaller 缓存、不强制 `pip -U`, 通常比首次快很多.

开发依赖见 `requirements.txt` (可选: `pip install -r requirements.txt`).
