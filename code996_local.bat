@echo off
chcp 65001 >nul
echo ====================================
echo Code996 本地分析工具
echo ====================================
echo.

python code996_local.py %*

if errorlevel 1 (
    echo.
    echo [错误] 脚本执行失败
    echo 请确保：
    echo 1. 已安装 Python 3.6+
    echo 2. 当前目录是一个 Git 仓库
    echo 3. Git 命令可用
    echo.
    pause
)

