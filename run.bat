@echo off
chcp 65001 > nul
echo Kindle for PC AI朗読・自動ページめくりプレイヤーを起動しています...
uv run python main.py %*
pause
