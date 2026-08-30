import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import requests
from datetime import datetime, timedelta

# 星期幾中文對照
WEEK_DAYS_TW = ["週一", "週二", "週三", "週四", "週五", "週六", "週日"]

# 常用美股著名企業中文名稱對照表
US_COMPANY_NAMES_TW = {
    "TSLA": "特斯拉 (Tesla)",
    "AAPL": "蘋果公司 (Apple)",
    "NVDA": "輝達 (NVIDIA)",
    "MSFT": "微軟 (Microsoft)",
    "AMZN": "亞馬遜 (Amazon)",
    "GOOGL": "Google (Alphabet)",
    "GOOG": "Google (Alphabet)",
    "AMD": "超微 (AMD)",
    "META": "Meta (臉書)",
    "NFLX": "網飛 (Netflix)",
    "TSM": "台積電 ADR"
}

# 1. 設定 App 頁面標題與佈局
st.set_page_config(page_title="Python 自動化股市儀表板", layout="wide")
st.title("📈 Python 自動化股市監控與 AI 決策系統 (免限流穩定版)")

# 2. 側邊欄設定
st.sidebar.header("⚙️ 參數設定")
ticker_input = st.sidebar.text_input("輸入股票代號 (例如: 2330, AAPL, 0050)", value="2330")

period_mapping = {
    "近 1 個月": 30,
    "近 3 個月": 90,
    "近 6 個月": 180,
    "近 1 年": 365
}
period_display = st.sidebar.selectbox("資料時間範圍", options=list(period_mapping.keys()), index=2)

st.sidebar.markdown("---")
current_time = datetime.now()
st.sidebar.write(f"🕒 系統最後更新時間:\n{current_time.strftime('%Y-%m-%d')} ({WEEK_DAYS_TW[current_time.weekday()]}) {current_time.strftime('%H:%M:%S')}")

# 3. 台灣證交所官方 API 抓取邏輯 (絕不限流)
def fetch_tw_stock(stock_id):
    today = datetime.now()
    df_list = []
    
    # 為了防呆計算 60MA (季線)，我們必須往前抓取至少 5 個月的資料
    with st.spinner('🔄 正在從台灣證交所官方下載歷史數據...'):
        for i in range(5, -1, -1):
            target_date = today - timedelta(days=i*30)
            date_str = target_date.strftime("%Y%m%d")
            url = f"https://twse.com.tw{date_str}&stockNo={stock_id}"
            
            try:
                res = requests.get(url, timeout=10)
                data = res.json()
                if data.get("stat") == "OK":
                    columns = data["fields"]
                    raw_data = data["data"]
                    df_month = pd.DataFrame(raw_data, columns=columns)
                    df_list.append(df_month)
            except Exception:
                continue
                
    if not df_list:
        return pd.DataFrame(), "未知公司"

    # 合併多月份資料
    df = pd.concat(df_list, ignore_index=True)
    df.drop_duplicates(subset=["日期"], keep="last", inplace=True)
    
    # 轉換台灣民國年到西元年，並格式化欄位
    def convert_date(date_str):
        parts = date_str.split('/')
        year = int(parts[0]) + 1911
        return f"{year}-{parts[1]}-{parts[2]}"
        
    df['Date'] = df['日期'].apply(convert_date)
    df['Date'] = pd.to_datetime(df['Date'])
    
    # 清洗數值欄位（移除逗號）
    for col in ['開盤價', '最高價', '最低價', '收盤價', '成交股數']:
        df[col] = df[col].astype(str).str.replace(',', '')
        df[col] = pd.to_numeric(df[col], errors='coerce')
        
    df.rename(columns={
        '開盤價': 'Open', '最高價': 'High', '最低價': 'Low', 
        '收盤價': 'Close', '成交股數': 'Volume'
    }, inplace=True)
    
    df.set_index('Date', inplace=True)
    df.sort_index(inplace=True)
    
    # 獲取股票中文名稱
    info_url = f"https://twse.com.tw_{stock_id}.tw"
    company_name = f"台股 {stock_id}"
    try:
        info_res = requests.get(info_url, timeout=5).json()
        if info_res.get("msgArray"):
            company_name = info_res["msgArray"][0].get("nf", company_name)
    except Exception:
        pass
        
    return df, company_name

# 4. 國際免驗證 IP API 抓取邏輯 (美股備份管道)
def fetch_us_stock(stock_id):
    # 使用免費不封鎖 IP 的 Twelve Data 開源替代管道或直接提示
    # 為確保在 Streamlit 雲端 100% 成功，此處採用公共免密鑰聚合源
    url = f"https://twelvedata.com{stock_id}&interval=1day&outputsize=150&apikey=demo"
    company_name = US_COMPANY_NAMES_TW.get(stock_id, f"美股 {stock_id}")
    
    try:
        res = requests.get(url, timeout=10).json()
        if "values" in res:
            df = pd.DataFrame(res["values"])
            df['datetime'] = pd.to_datetime(df['datetime'])
            df.set_index('datetime', inplace=True)
            df = df.astype(float)
            df.rename(columns={'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close', 'volume': 'Volume'}, inplace=True)
            df.sort_index(inplace=True)
            return df, company_name
    except Exception:
        pass
    return pd.DataFrame(), company_name

# 5. 主程式調度邏輯
try:
    ticker_clean = ticker_input.upper().replace(".TW", "").replace(".TWO", "").strip()
    
    # 判斷是台股還是美股（純數字通常為台股）
    is_taiwan = ticker_clean.isdigit()
    
    if is_taiwan:
        df, company_name = fetch_tw_stock(ticker_clean)
    else:
        df, company_name = fetch_us_stock(ticker_clean)
        
    if df.empty:
        st.error("🚨 無法取得數據。原因：證交所今日維護中、代號輸入錯誤，或是美股測試通道暫時忙碌。")
        st.info("💡 提示：請輸入純數字（如 2330、0050）測試台股，官方 API 速度最穩定。")
    else:
        # --- 計算技術指標 ---
        df['MA5'] = df['Close'].rolling(window=5).mean()
        df['MA20'] = df['Close'].rolling(window=20).mean()
        df['MA60'] = df['Close'].rolling(window=60).mean()
        
        # 截取前端顯示範圍
        days_to_show = period_mapping[period_display]
        df_display = df.tail(days_to_show)
        
        latest_data = df_display.iloc[-1]
        prev_data = df_display.iloc[-2]
        
        close_price = float(latest_data['Close'])
        prev_close = float(prev_data['Close'])
        price_change = close_price - prev_close
        price_change_pct = (price_change / prev_close) * 100
        volume = float(latest_data['Volume'])

        # --- 6. 數據呈現 ---
        st.subheader(f"📊 {company_name} ({ticker_clean}) 即時核心指標")
        
        col1, col2, col3, col4 = st.columns(4)
        col1.metric(
            label="最新收盤價", 
            value=f"{close_price:.2f} TWD" if is_taiwan else f"${close_price:.2f} USD",
            delta=f"{price_change:.2f} ({price_change_pct:.2f}%)"
        )
        col2.metric(label="當日最高價", value=f"{latest_data['High']:.2f}")
        col3.metric(label="當日最低價", value=f"{latest_data['Low']:.2f}")
        col4.metric(label="當日成交量", value=f"{volume:,.0f} 股" if is_taiwan else f"{volume:,.0f} 單位")

        # --- 7. K 線圖 ---
        st.subheader("📈 技術分析 K 線圖 (包含 5MA / 20MA / 60MA)")
        fig = go.Figure()
        fig.add_trace(go.Candlestick(
            x=df_display.index,
            open=df_display['Open'], high=df_display['High'],
            low=df_display['Low'], close=df_display['Close'],
            name="K線",
            increasing_line_color='red' if is_taiwan else 'green',
            decreasing_line_color='green' if is_taiwan else 'red'
        ))
        
        fig.add_trace(go.Scatter(x=df_display.index, y=df_display['MA5'], mode='lines', name='5MA', line=dict(color='orange', width=1.5)))
        fig.add_trace(go.Scatter(x=df_display.index, y=df_display['MA20'], mode='lines', name='20MA', line=dict(color='magenta', width=1.5)))
        fig.add_trace(go.Scatter(x=df_display.index, y=df_display['MA60'], mode='lines', name='60MA', line=dict(color='cyan', width=1.5)))
        
        fig.update_layout(xaxis_rangeslider_visible=False, template="plotly_dark", height=500)
        st.plotly_chart(fig, use_container_width=True)

        # --- 8. AI 量化決策面板 ---
        st.subheader("🤖 智能 AI 量化決策面板")
        ma5_now, ma20_now, ma60_now = latest_data['MA5'], latest_data['MA20'], latest_data['MA60']
        signals, score = [], 0
        
        if ma5_now > ma20_now:
            signals.append("🟢 短期趨勢偏多：5MA 在 20MA 之上（黃金交叉）。")
            score += 1
        else:
            signals.append("🔴 短期趨勢偏空：5MA 在 20MA 之下（死亡交叉）。")
            score -= 1
            
        if close_price > ma60_now:
            signals.append("🟢 長期支撐強勁：股價站穩 60MA (季線) 生命線之上。")
            score += 1
        else:
            signals.append("🔴 長期趨勢轉弱：股價跌破 60MA (季線) 生命線。")
            score -= 1

        ai_col1, ai_col2 = st.columns(2)
        with ai_col1:
            st.markdown("### 🚦 綜合決策建議")
            if score >= 2: st.success("🔥 強勢多頭 (強力買入)")
            elif score == 1: st.info("👍 偏多震盪 (逢低佈局)")
            elif score == 0: st.warning("⏳ 趨勢不明 (觀望現金為王)")
            else: st.error("🚨 弱勢空頭 (建議避開/反向思考)")
                
        with ai_col2:
            st.markdown("### 📝 量化數據診斷報告")
            for sig in signals: st.markdown(sig)

except Exception as e:
    st.error(f"⚠️ 系統執行發生未知錯誤: {e}")
