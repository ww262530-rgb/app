import streamlit as st
import yfinance as yf
import plotly.graph_objects as go
import numpy as np
import twstock  # 引入本地台股代碼庫，確保 100% 台股中文翻譯
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
st.title("📈 Python 自動化股市監控與 AI 決策系統")

# 2. 側邊欄設定
st.sidebar.header("⚙️ 參數設定")
ticker_input = st.sidebar.text_input("輸入股票代號 (例如: 2330.TW, AAPL, 0050.TW)", value="2330.TW")

period_mapping = {
    "近 1 個月": "1mo",
    "近 3 個月": "3mo",
    "近 6 個月": "6mo",
    "近 1 年": "1y",
    "近 5 年": "5y"
}
period_display = st.sidebar.selectbox("資料時間範圍", options=list(period_mapping.keys()), index=2)

st.sidebar.markdown("---")
current_time = datetime.now()
st.sidebar.write(f"🕒 系統最後更新時間:\n{current_time.strftime('%Y-%m-%d')} ({WEEK_DAYS_TW[current_time.weekday()]}) {current_time.strftime('%H:%M:%S')}")

# 3. 建立自訂 Requests Session 繞過限流 (核心修正)
@st.cache_resource
def get_headers_session():
    session = requests.Session()
    # 模擬一般瀏覽器發出請求，避免被 Yahoo 偵測為自動化腳本
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Referer': 'https://yahoo.com'
    })
    return session

# 4. 定義更安全的資料抓取函數 (加長快取時間至 5 分鐘，減少伺服器請求次數)
@st.cache_data(ttl=300)
def fetch_stock_data_safe(ticker, period_select):
    session = get_headers_session()
    
    # 決定要抓取的長度以計算 60MA
    required_period = "1y" if period_select in ["1mo", "3mo", "6mo", "1y"] else "5y"
    
    # 1. 抓取 K 線歷史數據（使用 download 搭配 session 通常比 history 穩定）
    df = yf.download(ticker, period=required_period, session=session, progress=False)
    
    # 2. 抓取基本面資料 (包覆在 try-except 內防止 info 接口報錯導致整個程式掛掉)
    info = {}
    try:
        stock_obj = yf.Ticker(ticker, session=session)
        info = stock_obj.info
    except Exception:
        pass # 如果 info 接口被限流，依然允許程式繼續執行 K 線分析
        
    return df, info

# 5. 執行抓取並呈現數據
try:
    ticker_upper = ticker_input.upper().strip()
    is_taiwan_stock = ticker_upper.endswith(".TW") or ticker_upper.endswith(".TWO")

    with st.spinner('🔄 正在從網路自動抓取最新股市數據並進行量化分析...'):
        df, info = fetch_stock_data_safe(ticker_upper, period_mapping[period_display])
    
    if df.empty:
        st.error("❌ 找不到該股票數據或被 Yahoo Finance 暫時限流，請稍後再試或檢查代號是否正確。")
    else:
        # 處理 yf.download 可能產生的 MultiIndex 欄位結構
        if isinstance(df.columns, go.layout.Template) or hasattr(df.columns, 'levels'):
            df.columns = df.columns.get_level_values(0)

        # --- 💥 超級智能中文名稱辨識邏輯 ---
        company_name = "未知公司"
        
        if not is_taiwan_stock and ticker_upper in US_COMPANY_NAMES_TW:
            company_name = US_COMPANY_NAMES_TW[ticker_upper]
        else:
            if is_taiwan_stock:
                pure_code = ticker_upper.replace(".TW", "").replace(".TWO", "")
                if pure_code in twstock.codes:
                    company_name = twstock.codes[pure_code].name
            
            if company_name == "未知公司" and info:
                company_name = info.get("longName", info.get("shortName", ticker_upper))

        # --- 5. 計算量化指標 ---
        df['MA5'] = df['Close'].rolling(window=5).mean()
        df['MA20'] = df['Close'].rolling(window=20).mean()
        df['MA60'] = df['Close'].rolling(window=60).mean()

        # 根據用戶選擇的時間範圍，截取前端要顯示的資料量
        if period_display == "近 1 個月":
            df_display = df.last("30D")
        elif period_display == "近 3 個月":
            df_display = df.last("90D")
        elif period_display == "近 6 個月":
            df_display = df.last("180D")
        elif period_display == "近 1 年":
            df_display = df.last("365D")
        else:
            df_display = df

        # 取得最新一筆與前一筆數據
        latest_data = df_display.iloc[-1]
        prev_data = df_display.iloc[-2]
        
        close_price = float(latest_data['Close'])
        prev_close = float(prev_data['Close'])
        price_change = close_price - prev_close
        price_change_pct = (price_change / prev_close) * 100
        volume = float(latest_data['Volume'])

        # --- 6. 頂部儀表板數據呈現 (KPI Metrics) ---
        st.subheader(f"📊 {company_name} ({ticker_upper}) 即時核心指標")
        
        col1, col2, col3, col4 = st.columns(4)
        col1.metric(
            label="最新收盤價", 
            value=f"${close_price:.2f}" if not is_taiwan_stock else f"{close_price:.2f} TWD",
            delta=f"{price_change:.2f} ({price_change_pct:.2f}%)"
        )
        col2.metric(label="當日最高價", value=f"{latest_data['High']:.2f}")
        col3.metric(label="當日最低價", value=f"{latest_data['Low']:.2f}")
        col4.metric(label="當日成交量", value=f"{volume:,.0f} 股")

        # --- 7. 繪製互動式 K 線圖與均線 ---
        st.subheader("📈 技術分析 K 線圖 (包含 5MA / 20MA / 60MA)")
        
        fig = go.Figure()
        
        fig.add_trace(go.Candlestick(
            x=df_display.index,
            open=df_display['Open'],
            high=df_display['High'],
            low=df_display['Low'],
            close=df_display['Close'],
            name="K線",
            increasing_line_color='red' if is_taiwan_stock else 'green',
            decreasing_line_color='green' if is_taiwan_stock else 'red'
        ))
        
        fig.add_trace(go.Scatter(x=df_display.index, y=df_display['MA5'], mode='lines', name='5MA (週線)', line=dict(color='orange', width=1.5)))
        fig.add_trace(go.Scatter(x=df_display.index, y=df_display['MA20'], mode='lines', name='20MA (月線)', line=dict(color='magenta', width=1.5)))
        fig.add_trace(go.Scatter(x=df_display.index, y=df_display['MA60'], mode='lines', name='60MA (季線)', line=dict(color='cyan', width=1.5)))
        
        fig.update_layout(
            xaxis_rangeslider_visible=False,
            template="plotly_dark",
            margin=dict(l=20, r=20, t=20, b=20),
            height=500
        )
        st.plotly_chart(fig, use_container_width=True)

        # --- 8. AI 模擬量化決策系統 ---
        st.subheader("🤖 智能 AI 量化決策面板")
        
        ma5_now = latest_data['MA5']
        ma20_now = latest_data['MA20']
        ma60_now = latest_data['MA60']
        
        signals = []
        score = 0
        
        if ma5_now > ma20_now:
            signals.append("🟢 短期趨勢偏多：5MA 位在 20MA 之上（黃金交叉）。")
            score += 1
        else:
            signals.append("🔴 短期趨勢偏空：5MA 位在 20MA 之下（死亡交叉）。")
            score -= 1
            
        if close_price > ma60_now:
            signals.append("🟢 長期支撐強勁：股價站穩 60MA (季線) 生命線之上。")
            score += 1
        else:
            signals.append("🔴 長期趨勢轉弱：股價跌破 60MA (季線) 生命線。")
            score -= 1

        volume_ma20 = df_display['Volume'].rolling(window=20).mean().iloc[-1]
        if volume > volume_ma20 * 1.2:
            signals.append("🟢 動能增溫：今日成交量高於 20 日平均量 20% 以上，屬於爆量結構。")
            score += 1
        elif volume < volume_ma20 * 0.8:
            signals.append("⚪ 動能停滯：今日成交量低於 20 日平均量 20% 以上，市場觀望氣氛濃。")

        ai_col1, ai_col2 = st.columns(2)
        
        with ai_col1:
            st.markdown("### 🚦 綜合決策建議")
            if score >= 2:
                st.success("🔥 強勢多頭 (強力買入)")
            elif score == 1:
                st.info("👍 偏多震盪 (逢低佈局)")
            elif score == 0:
                st.warning("⏳ 趨勢不明 (觀望現金為王)")
            else:
                st.error("🚨 弱勢空頭 (建議避開/反向思考)")
                
        with ai_col2:
            st.markdown("### 📝 量化數據診斷報告")
            for sig in signals:
                st.markdown(sig)

except Exception as e:
    st.error(f"⚠️ 系統執行發生錯誤: {e}")
    st.info("提示：由於 Streamlit 雲端共享 IP 容易觸發 Yahoo Finance 防爬蟲機制，若持續出現此錯誤，建議等幾分鐘後重新整理，或在本地端（Localhost）執行將完全正常。")
