@echo off
:: 1. 自動切換到你的股市 App 專案資料夾路徑
cd /d "C:\Users\b8903\OneDrive\Desktop\選股\APP"

:: 2. 使用 Python 模組方式直接啟動 Streamlit
python -m streamlit run app.py

:: 如果程式異常關閉，保持視窗開啟以利查看錯誤訊息
pause
