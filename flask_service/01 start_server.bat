@echo off
chcp 65001 >nul

echo ===================================================
echo     启动 Zotero Picker 开发环境
echo ===================================================
echo.

echo [1/3] 正在激活 Anaconda 基础环境...
:: 【！！！注意：请将下方路径替换为你自己电脑上 Anaconda或者python 的实际安装路径！！！】
:: 常见默认路径示例：C:\ProgramData\Anaconda3\Scripts\activate.bat
call D:\01_Programs\Anaconda3\Scripts\activate.bat base

echo [2/3] 正在启动后台 Flask 服务...
:: 此处已使用 %~dp0 相对路径，自动适配当前文件夹，【无需修改】
start "Zotero Picker Backend" /MIN python "%~dp0flask_script.py"

echo [3/3] 正在唤醒 Zotero...
:: 【！！！注意：请将下方路径替换为你自己电脑上 Zotero.exe 的实际安装路径！！！】
:: 常见默认路径示例："C:\Program Files\Zotero\zotero.exe"
start "" "C:\Program Files\Zotero\zotero.exe"

timeout /t 2 >nul
exit