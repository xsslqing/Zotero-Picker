@echo off
:: Set console to UTF-8
chcp 65001 >nul
set PYTHONIOENCODING=utf-8

echo ===================================================
echo Zotero Picker Build Script (Standalone Env)
echo ===================================================
echo.

set TEMP_ENV=zotero_temp_build
set PY_VER=3.10

echo [1/7] Initializing Anaconda base environment...
call D:\01_Programs\Anaconda3\Scripts\activate.bat base

echo [2/7] Removing existing temp environment if any...
call conda env remove -n %TEMP_ENV% -y >nul 2>&1

echo [3/7] Creating new clean environment (with tk/sqlite)...
call conda create -n %TEMP_ENV% python=%PY_VER% tk sqlite -y

echo [4/7] Activating and installing dependencies...
call conda activate %TEMP_ENV%
:: Added 'pillow' to automatically fix/convert fake .ico files
pip install flask requests flask_cors pyinstaller pillow -i https://pypi.tuna.tsinghua.edu.cn/simple

echo [5/7] Cleaning previous build files...
if exist build rmdir /s /q build
if exist dist\zotero_picker.exe del /q dist\zotero_picker.exe

echo [6/7] Running PyInstaller...
pyinstaller flask_script.spec

echo [7/7] Tearing down temp environment...
call conda deactivate
call conda env remove -n %TEMP_ENV% -y

echo.
echo ===================================================
echo Build completed successfully!
echo Check the 'dist' folder for zotero_picker.exe.
echo ===================================================
pause