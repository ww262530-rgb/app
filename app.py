import streamlit as st
import yfinance as yf
import plotly.graph_objects as go
import numpy as np
import twstock  # 引入本地台股代碼庫，確保 100% 台股中文翻譯
from datetime import datetime

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

# 1. 修正後的快取函數：改回 cache_resource 並加入瀏覽器偽裝
@st.cache_resource(ttl=300)  # 快取 5 分鐘，改用 resource 儲存連線物件
def fetch_stock_data(ticker):
    import requests
    
    # 建立客製化 Session 偽裝成一般 Chrome 瀏覽器
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    })
    
    # 將偽裝好的 session 帶入 Ticker
    stock = yf.Ticker(ticker, session=session)
    return stock


# 2. 側邊欄設定
st.sidebar.header("⚙️ 參數設定")
ticker_input = st.sidebar.text_input("輸入股票代號 (例如: 2330.TW, AAPL, 0050.TW)", value="2330.TW")

# 時間範圍中文化（為了計算中長期均線，預設拉長資料庫抓取範圍，前端顯示維持原樣）
period_mapping = {
    "近 1 個月": "1mo",
    "近 3 個月": "3mo",
    "近 6 個月": "6mo",
    "近 1 年": "1y",
    "近 5 年": "5y"
}
period_display = st.sidebar.selectbox("資料時間範圍", options=list(period_mapping.keys()), index=2) # 預設改近6個月更利於趨勢分析

# 顯示最後更新時間
st.sidebar.markdown("---")
current_time = datetime.now()
st.sidebar.write(f"🕒 系統最後更新時間:\n{current_time.strftime('%Y-%m-%d')} ({WEEK_DAYS_TW[current_time.weekday()]}) {current_time.strftime('%H:%M:%S')}")

# 3. 定義資料抓取函數 (為了均線計算防呆，一律抓取更長線的資料後再截取)
@st.cache_data(ttl=300)  # 快取 5 分鐘，避免頻繁請求
def fetch_stock_data(ticker):
    import requests
    
    # 建立一個客製化的 Session 偽裝成一般 Chrome 瀏覽器外殼
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    })
    
    # 將偽裝好的 session 餵給 yfinance
    stock = yf.Ticker(ticker, session=session)
    
    # 移除會報錯的 proxy 和 user_agent 參數
    df_history = stock.history(
        period="1y", 
        auto_adjust=True
    )
    return stock, df_history


# 4. 執行抓取並呈現數據
try:
    ticker_upper = ticker_input.upper()
    is_taiwan_stock = ticker_upper.endswith(".TW") or ticker_upper.endswith(".TWO")

    with st.spinner('🔄 正在從網路自動抓取最新股市數據並進行量化分析...'):
        stock_obj = fetch_stock_data(ticker_input)
        # 根據畫面上選擇的範圍動態調整（若選短天期，背景一律多抓，確保能算出 60MA 季線）
        fetch_period = "1y" if period_mapping[period_display] in ["1mo", "3mo", "6mo", "1y"] else "5y"
        df = stock_obj.history(period=fetch_period, auto_adjust=True)
        info = stock_obj.info

    
    if df.empty:
        st.error("❌ 找不到該股票數據，請檢查代號是否正確。")
    else:
        # --- 💥 超級智能中文名稱辨識邏輯 ---
        company_name = ""
        if is_taiwan_stock:
            raw_code = ticker_upper.split('.')[0]
            if raw_code in twstock.codes:
                tw_info = twstock.codes[raw_code]
                company_name = f"{tw_info.name} ({raw_code})"
            else:
                company_name = info.get('shortName') or info.get('longName') or ticker_upper
        else:
            company_name = US_COMPANY_NAMES_TW.get(ticker_upper, info.get('shortName') or info.get('longName') or ticker_upper)

        # --- 🛡️ 安全排除 NaN (空數值) 防錯機制 ---
        df_clean = df.dropna(subset=['Close', 'Open', 'High', 'Low']).copy()
        
        # --- 📈 核心量化指標計算 (均線 & RSI) ---
        df_clean['MA5'] = df_clean['Close'].rolling(window=5).mean()    # 短期：週線
        df_clean['MA20'] = df_clean['Close'].rolling(window=20).mean()  # 中期：月線
        df_clean['MA60'] = df_clean['Close'].rolling(window=60).mean()  # 長期：季線
        
        # 計算 RSI (14)
        delta = df_clean['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df_clean['RSI'] = 100 - (100 / (1 + rs))

        # 根據使用者選擇的時間範圍過濾最終顯示的資料
        target_period = period_mapping[period_display]
        days_dict = {"1mo": 22, "3mo": 66, "6mo": 132, "1y": 252, "5y": 1260}
        display_days = days_dict.get(target_period, 132)
        
        df_display = df_clean.tail(display_days)

        if df_display.empty:
            st.warning("⚠️ 該區間內無有效的股票交易價格。")
        else:
            # 獲取最新狀態值
            current_price = df_display['Close'].iloc[-1]
            ma5_now = df_display['MA5'].iloc[-1]
            ma20_now = df_display['MA20'].iloc[-1]
            ma60_now = df_display['MA60'].iloc[-1]
            rsi_now = df_display['RSI'].iloc[-1]
            
            if len(df_display) > 1:
                price_change = df_display['Close'].iloc[-1] - df_display['Close'].iloc[-2]
                pct_change = (price_change / df_display['Close'].iloc[-2]) * 100
            else:
                price_change, pct_change = 0.0, 0.0

            # 頂部三大關鍵指標卡片
            col1, col2, col3 = st.columns(3)
            col1.metric("🏢 公司名稱", company_name)
            col2.metric("💵 最新收盤價", f"${current_price:.2f} 元")
            col3.metric("📈 今日漲跌幅", f"{price_change:+.2f} 元 ({pct_change:+.2f}%)")

            st.markdown("---")

            # 🔥 新增功能：短中長趨勢、買點、操作建議決策面板
            st.subheader("🤖 量化分析與策略操作建議")
            trend_col, signal_col, action_col = st.columns(3)

            with trend_col:
                st.markdown("#### 🔍 短中長趨勢診斷")
                # 短期趨勢 (MA5 vs MA20)
                if current_price >= ma5_now:
                    st.success("🟢 **短期趨勢**：多頭強勢 (股價站上5日線)")
                else:
                    st.error("🔴 **短期趨勢**：弱勢修正 (股價跌破5日線)")
                
                # 中期趨勢 (MA20 月線)
                if current_price >= ma20_now:
                    st.success("🟢 **中期趨勢**：月線支撐 (波段偏多走勢)")
                else:
                    st.error("🔴 **中期趨勢**：月線壓制 (波段面臨回檔)")
                
                # 長期趨勢 (MA60 季線)
                if np.isnan(ma60_now):
                    st.warning("⚪ **長期趨勢**：歷史資料不足以計算季線")
                elif current_price >= ma60_now:
                    st.success("🟢 **長期趨勢**：季線之上 (長線牛市格局)")
                else:
                    st.error("🔴 **長期趨勢**：季線之下 (長線熊市或大型調整)")

            with signal_col:
                st.markdown("#### 🎯 買賣點訊號提示")
                if np.isnan(rsi_now):
                    st.info("💡 RSI 指標計算中...")
                else:
                    st.write(f"📊 **目前 RSI (14) 指數**：`{rsi_now:.1f}`")
                    if rsi_now >= 70:
                        st.markdown("<span style='color:red; font-weight:bold;'>⚠️ 訊號：市場過熱 (過度買超)</span>", unsafe_allow_html=True)
                        st.caption("🚨 股價進入短期高檔技術超買區，請留意追高風險。")
                    elif rsi_now <= 30:
                        st.markdown("<span style='color:green; font-weight:bold;'>✅ 訊號：打底浮現 (過度賣超)</span>", unsafe_allow_html=True)
                        st.caption("💰 股價進入恐慌超賣區，通常是價值投資人分批尋找左側買點的時機。")
                    else:
                        st.markdown("<span>⚖️ 訊號：中性震盪</span>", unsafe_allow_html=True)
                        st.caption("🔄 目前市場買賣力道均衡，適合觀察均線扣高或突破方向。")

            with action_col:
                st.markdown("#### 💡 整合操作策略建議")
                # 簡單決策樹邏輯
                if current_price >= ma20_now and (rsi_now < 70 or np.isnan(rsi_now)):
                    st.info("📋 **建議**：**順勢續抱 / 逢回拉回買進**")
                    st.caption("基於中線多頭架構未破，且技術面尚未過熱，可沿著月線或雙週線逢低分批布局，或維持原有部位續抱。")
                elif current_price < ma20_now and rsi_now <= 35:
                    st.info("📋 **建議**：**尋求左側支撐 / 分批低接**")
                    st.caption("股價雖跌破月線，但已高度超賣。適合長線投資人依季線或前低支撐，實施分批金字塔式逢低配置。")
                elif rsi_now >= 70:
                    st.info("📋 **建議**：**落袋為安 / 分批停利**")
                    st.caption("短線情緒極度亢奮。建議不宜開槓桿追高，短線交易者可考慮調節部分獲利，靜待拉回均線再重新布局。")
                else:
                    st.info("📋 **建議**：**空手者觀望 / 持股者中性看待**")
                    st.caption("目前趨勢與動能不明顯，可靜待股價回檔至關鍵均線（如月線、季線）有守時，再進場建立基本部位。")

            st.markdown("---")

            # 5. 使用 Plotly 繪製中文化互動 K 線圖 (同步加入 MA 均線線條)
            fig = go.Figure()
            
            # K線主體
            fig.add_trace(go.Candlestick(
                x=df_display.index,
                open=df_display['Open'],
                high=df_display['High'],
                low=df_display['Low'],
                close=df_display['Close'],
                increasing_line_color='red',    # 台灣習慣：漲紅
                decreasing_line_color='green',  # 台灣習慣：跌綠
                name="K線走勢"
            ))
            
            # 疊加均線
            fig.add_trace(go.Scatter(x=df_display.index, y=df_display['MA5'], mode='lines', line=dict(color='orange', width=1.5), name='5日均線(週)'))
            fig.add_trace(go.Scatter(x=df_display.index, y=df_display['MA20'], mode='lines', line=dict(color='purple', width=1.5), name='20日均線(月)'))
            if not np.isnan(ma60_now):
                fig.add_trace(go.Scatter(x=df_display.index, y=df_display['MA60'], mode='lines', line=dict(color='blue', width=1.5), name='60日均線(季)'))
            
            fig.update_layout(
                title=f"📊 {company_name} 歷史 K 線技術指標圖 ({period_display})",
                xaxis_title="交易日期",
                yaxis_title="股價 (元)",
                xaxis_rangeslider_visible=False,
                template="plotly_white",
                hovermode="x unified"
            )
            
            st.plotly_chart(fig, width="stretch")

            # 顯示原始數據表格
            st.markdown("---")
            st.subheader("📋 近 10 筆歷史交易明細")
            
            df_chinese = df_display.copy()
            df_chinese['交易日期'] = [f"{d.strftime('%Y-%m-%d')} ({WEEK_DAYS_TW[d.weekday()]})" for d in df_chinese.index]
            
            if is_taiwan_stock:
                df_chinese['成交量(張)'] = (df_chinese['Volume'] / 1000).round(1)
                volume_col = '成交量(張)'
            else:
                df_chinese['成交量(萬股)'] = (df_chinese['Volume'] / 10000).round(1)
                volume_col = '成交量(萬股)'

            df_chinese = df_chinese.rename(columns={
                'Open': '開盤價',
                'High': '最高價',
                'Low': '最低價',
                'Close': '收盤價'
            })
            
            # 將均線加入顯示清單
            show_df = df_chinese[['交易日期', '開盤價', '最高價', '最低價', '收盤價', 'MA5', 'MA20', volume_col]].tail(10)
            show_df = show_df.set_index('交易日期').sort_index(ascending=False)
            
            st.dataframe(show_df, width="stretch")

except Exception as e:
    st.error(f"⚠️ 系統抓取時發生錯誤: {e}")
    st.info("💡 提示：如果查詢台股，請務必在代號後方加上後綴。例如：台積電請輸入 '2330.TW'、鴻海請輸入 '2317.TW'")
