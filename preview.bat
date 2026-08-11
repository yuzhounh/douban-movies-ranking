@echo off
chcp 65001 >nul
title 豆瓣影视排行榜 - 本地预览
cd /d "%~dp0docs"
echo 正在启动本地预览服务器...
echo.
echo   预览地址: http://localhost:8321
echo.
echo 关闭本窗口即可停止服务器。
start "" "http://localhost:8321"
python -m http.server 8321
pause
