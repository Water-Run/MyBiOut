# MyBiOut! 绿色包一键构建 (Windows PowerShell)
# 在仓库根目录执行: powershell -ExecutionPolicy Bypass -File scripts/build_green.ps1

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

Write-Host "==> 安装打包依赖..."
python -m pip install -e ".[green]" pywebview pyinstaller

Write-Host "==> PyInstaller onedir..."
python -m PyInstaller --noconfirm --clean packaging/MyBiOut.spec

Write-Host "==> 组装绿色目录..."
python scripts/assemble_green.py

Write-Host "==> 完成: dist/MyBiOut-green/"
Write-Host "可将 dist/MyBiOut-green 压缩为 zip 作为 Release 资产。"
