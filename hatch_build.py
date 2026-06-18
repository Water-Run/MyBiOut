import sys

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


class PlatformCheckHook(BuildHookInterface):
    def initialize(self, version, build_data):
        super().initialize(version, build_data)

        # 限制只能在 Windows x64 系统上构建/安装
        if sys.platform != "win32":
            raise RuntimeError(
                "\n"
                "===========================================================\n"
                "ERROR: MyBiOut! 仅支持 Windows 平台。\n"
                "ERROR: MyBiOut! only supports the Windows platform.\n"
                "==========================================================="
            )

        if sys.maxsize <= 2**32:
            raise RuntimeError(
                "\n"
                "===========================================================\n"
                "ERROR: MyBiOut! 仅支持 64 位 Windows 系统。\n"
                "ERROR: MyBiOut! only supports 64-bit Windows systems.\n"
                "==========================================================="
            )

        # 强制将 Wheel 标记为平台特定（非 pure python），并指定为 Windows 64位平台标签（win_amd64）
        if self.target_name == 'wheel':
            build_data['pure_python'] = False
            build_data['tag'] = 'py3-none-win_amd64'
