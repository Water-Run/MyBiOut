from PyInstaller.utils.hooks.gi import GiModuleInfo


模块信息 = GiModuleInfo("JavaScriptCore", "4.1")
if 模块信息.available:
    binaries, datas, hiddenimports = 模块信息.collect_typelib_data()
