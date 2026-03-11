# `MyBiOut`

`MyBiOut`, 即`My-Bilibili-Output`, "导出我的哔哩哔哩", 一个综合性的, 一站式开箱即用哔哩哔哩导出工具集.  

![Logo](./mybiout/assets/logo-fullres.png)

支持的功能包括:  

- **本地缓存导出**: 导出本地的哔哩哔哩视频(包括哔哩哔哩客户端的缓存和连接的Android手机的缓存), 包括爬虫获取标题等元信息  
- **可视化BBDown封装**: 下载指定链接的哔哩哔哩视频  
- **Markdown导出**: 包括导出专栏和格式化导出用户元数据(如收藏等)  

使用`FastAPI`, 网页前端部署在`localhost`. 显然的, 你需要有一个标准的`Python`环境.  
项目发布在[PyPi]()上:  

```cmd
pip install mybiout
```

完成安装后, 打开Windows终端, 输入以下命令获取使用帮助:  

```cmd
man!
```

`man`即`manuscript`(参阅Linux的`man`命令): 手册.  

使用以下命令(不区分大小写)启动系统:  

```cmd
MyBiOut!
```

这将在本机的的`23333`端口启动服务. 你需要保持这个终端不关闭以维持服务的运行.  
页面将在浏览器自动打开. 如果没有打开, 考虑手动访问:  

```url
http://localhost:23333
```

如果你不想用`23333`作为端口, 你可以使用以下启动方式切换端口:  

```cmd
MyBiOut! --port 端口号
```

例如, 以`2026`作为端口:  

```cmd
MyBiOut! --port 2026
```

项目依赖以下开源项目:  

- [biliffm4s](https://github.com/Water-Run/-m4s-Python-biliffm4s/blob/master/biliffm4s/biliffm4s.py): 对`ffmpeg`的封装  
- [BBDown](https://github.com/nilaoda/BBDown): 知名哔哩哔哩下载工具  

## 测试

- Windows 11
- 小米13(Hyper OS 3), 一加8(原生Android 15)
