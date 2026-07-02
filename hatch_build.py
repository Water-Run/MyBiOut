import sys as 系统

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


class 平台检查钩子(BuildHookInterface):
    def initialize(self, 版本, 构建数据):
        super().initialize(版本, 构建数据)

        # 限制只能在 Windows x64 系统上构建/安装
        if 系统.platform != "win32":
            raise RuntimeError(
                "\n"
                "===========================================================\n"
                "ERROR: MyBiOut! 仅支持 Windows 平台。\n"
                "==========================================================="
            )

        if 系统.maxsize <= 2**32:
            raise RuntimeError(
                "\n"
                "===========================================================\n"
                "ERROR: MyBiOut! 仅支持 64 位 Windows 系统。\n"
                "==========================================================="
            )

        # 强制将 Wheel 标记为平台特定（非 pure python），并指定为 Windows 64位平台标签（win_amd64）
        if self.target_name == "wheel":
            构建数据["pure_python"] = False
            构建数据["tag"] = "py3-none-win_amd64"


PlatformCheckHook = 平台检查钩子
