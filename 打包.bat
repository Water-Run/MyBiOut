@echo off
chcp 65001 >nul
setlocal EnableExtensions
cd /d "%~dp0"

echo ========================================
echo   MyBiOut! 绿色版发布打包
echo ========================================
echo.

where python >nul 2>&1
if errorlevel 1 (
  echo [错误] 未找到 python, 请先安装 Python 3.14+ 并加入 PATH
  exit /b 1
)

echo [1/4] 安装/更新构建依赖...
python -m pip install -e ".[green]" "pywebview>=5.0" "pyinstaller>=6.0.0"
if errorlevel 1 (
  echo [错误] 依赖安装失败
  exit /b 1
)

echo.
echo [2/4] PyInstaller 构建 onedir...
python -m PyInstaller --noconfirm --clean packaging\MyBiOut.spec
if errorlevel 1 (
  echo [错误] PyInstaller 构建失败
  exit /b 1
)

echo.
echo [3/4] 组装绿色目录 dist\MyBiOut-green\ ...
python scripts\assemble_green.py
if errorlevel 1 (
  echo [错误] 绿色目录组装失败
  exit /b 1
)

echo.
echo [4/4] 生成发布版 .rar ...
python scripts\pack_rar.py
if errorlevel 1 (
  echo [错误] RAR 打包失败 ^(需要本机安装 WinRAR 的 Rar.exe^)
  exit /b 1
)

echo.
echo ========================================
echo   完成
echo   绿色目录: dist\MyBiOut-green\
echo   发布包:   dist\release\MyBiOut-版本.rar
echo ========================================
echo.
pause
exit /b 0
