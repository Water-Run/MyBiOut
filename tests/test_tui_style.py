r"""
TUI 样式结构自检: 直升机比例/对齐、双套标题、字符宽度、离线帧渲染。
不启动真实终端备用屏, 用字符网格模拟绘制结果。
"""

from __future__ import annotations


def _栅格绘机(打包模块, *, 朝右: bool, 帧: int = 2, 旋翼停: bool = False) -> list[str]:
    r"""在虚拟网格上按 绘直升机 同等规则叠字, 返回裁切后的行文本。"""
    宽, 高 = 48, 12
    格 = [[" "] * 宽 for _ in range(高)]
    列, 行 = 4, 2
    机身 = 打包模块._机身朝右 if 朝右 else 打包模块._机身朝左
    轮廓 = 机身[1]
    舱心 = 打包模块._座舱中心列(轮廓)
    旋翼字 = 打包模块._短旋翼帧[0 if 旋翼停 else (帧 % len(打包模块._短旋翼帧))]
    旋翼左 = 列 + 舱心 - len(旋翼字) // 2
    尾 = "x" if 旋翼停 else 打包模块._尾桨帧[帧 % len(打包模块._尾桨帧)]

    def 放(r: int, c: int, ch: str) -> None:
        if 0 <= r < 高 and 0 <= c < 宽 and ch != " ":
            格[r][c] = ch

    for i, ch in enumerate(旋翼字):
        放(行, 旋翼左 + i, ch)
    放(行 + 1, 列 + 舱心, "|")
    for bi, line in enumerate(机身):
        if bi == 0:
            continue
        for i, ch in enumerate(line):
            放(行 + 1 + bi, 列 + i, 尾 if ch == "?" else ch)
    return ["".join(r).rstrip() for r in 格[行 : 行 + 6]]


def test_双套标题互异且等宽纯ascii(打包模块) -> None:
    检, 结 = 打包模块._检查标题字形, 打包模块._结算标题字形
    assert 检 != 结
    assert all(len(r) == 打包模块._检查标题宽度 for r in 检)
    assert all(len(r) == 打包模块._结算标题宽度 for r in 结)
    assert all(ord(c) < 128 for r in 检 + 结 for c in r)
    # 检查页: 字母块特征
    assert any("BBBBB" in r or "M   M" in r for r in 检)
    # 结算页: 轮廓字特征
    assert any(r.strip().startswith("_") or r.strip().startswith("|") for r in 结)
    assert any("!" in r for r in 检) and any("!" in r for r in 结)
    # 宽度适配最小终端 52
    assert 打包模块._检查标题宽度 <= 50
    assert 打包模块._结算标题宽度 <= 50


def test_直升机传统比例与部件(打包模块) -> None:
    assert len(打包模块._短旋翼帧) >= 3
    assert all(len(f) == len(打包模块._短旋翼帧[0]) for f in 打包模块._短旋翼帧)
    for 名, 身 in (("右", 打包模块._机身朝右), ("左", 打包模块._机身朝左)):
        assert len(身) == 4
        assert all(len(r) == 打包模块._直升机宽度 for r in 身)
        轮廓 = 身[1]
        梁 = sum(1 for c in 轮廓 if c in "-_")
        舱 = sum(1 for c in 轮廓 if c in "[]oO#")
        assert 梁 >= 舱 * 2, f"{名} 尾梁过短: {轮廓!r}"
        assert "?" in 轮廓 and "T" in 轮廓
        assert "[" in 轮廓 and "]" in 轮廓
        assert (">" in 轮廓) ^ ("<" in 轮廓) or (">" in 轮廓 and 名 == "右")
        # 座舱短: 方括号跨度 <= 5
        a, b = 打包模块._座舱列范围(轮廓)
        assert 0 < b - a <= 5, f"{名} 座舱过长: {轮廓!r}"


def test_舱肚与起落撬对齐座舱(打包模块) -> None:
    for 名, 身 in (("右", 打包模块._机身朝右), ("左", 打包模块._机身朝左)):
        轮廓, 肚, 撬 = 身[1], 身[2], 身[3]
        a, b = 打包模块._座舱列范围(轮廓)
        舱心 = 打包模块._座舱中心列(轮廓)
        肚点 = [i for i, c in enumerate(肚) if c != " "]
        撬点 = [i for i, c in enumerate(撬) if c != " "]
        assert 肚点 and 撬点, 名
        # 舱肚/撬的质心应贴近座舱中心, 且点落在座舱邻域
        肚心 = sum(肚点) / len(肚点)
        撬心 = sum(撬点) / len(撬点)
        assert abs(肚心 - 舱心) <= 2.5, f"{名} 舱肚偏离: {肚!r} vs {轮廓!r}"
        assert abs(撬心 - 舱心) <= 3.0, f"{名} 撬偏离: {撬!r} vs {轮廓!r}"
        assert all(a - 2 <= i <= b + 1 for i in 肚点), f"{名} 舱肚超出座舱: {肚!r}"
        assert all(a - 3 <= i <= b + 2 for i in 撬点), f"{名} 撬超出座舱: {撬!r}"
        # 尾梁投影列上不应有撬
        梁列 = [i for i, c in enumerate(轮廓) if c in "-_"]
        assert 梁列
        梁区撬 = [i for i in 撬点 if i in 梁列]
        assert not 梁区撬, f"{名} 撬画到尾梁下: {撬!r}"


def test_旋翼对齐座舱中心_离线帧(打包模块) -> None:
    for 朝右 in (True, False):
        行们 = _栅格绘机(打包模块, 朝右=朝右, 帧=1)
        # 第 0 行应有主旋翼笔画, 第 1 行有桅杆
        assert any(c in "*+-" for c in 行们[0]), 行们
        assert "|" in 行们[1], 行们
        合体 = "\n".join(行们)
        assert "[oo]" in 合体 or "oo" in 合体
        # 尾桨动画字符或 x
        assert any(ch in 合体 for ch in "|/-\\x")


def test_单元宽一致性(打包模块) -> None:
    assert 打包模块._单元宽("A") == 1
    assert 打包模块._单元宽("#") == 1
    assert 打包模块._单元宽("|") == 1
    assert 打包模块._单元宽("中") == 2
    assert 打包模块._中日韩宽度("AB中") == 4
    # 标题行显示宽 == 字符数 (纯 ASCII)
    for 行 in 打包模块._检查标题字形:
        assert 打包模块._中日韩宽度(行) == len(行)
    for 行 in 打包模块._结算标题字形:
        assert 打包模块._中日韩宽度(行) == len(行)


def test_倒计时数字纯ascii等宽(打包模块) -> None:
    for 键, 形 in 打包模块._大数字字形.items():
        宽 = max(len(r) for r in 形)
        assert all(len(r) == 宽 for r in 形), 键
        assert all(ord(c) < 128 for r in 形 for c in r), 键
        assert 宽 <= 12


def test_快速代码检查当前树通过(打包模块) -> None:
    ok, msg = 打包模块.快速代码检查()
    assert ok is True, msg
