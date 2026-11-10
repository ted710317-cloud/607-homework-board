@echo off
chcp 65001 > nul
echo 正在執行 Padlet 聯絡簿同步...
python "%~dp0sync.py"
