import streamlit as st
import yfinance as yf
import pandas as pd
import json
import os
from datetime import datetime
import fear_greed
import plotly.graph_objects as go

WATCHLIST_FILE = "watchlist.json"

def load_watchlist():
    if os.path.exists(WATCHLIST_FILE):
        with open(WATCHLIST_FILE, "r") as f:
            return json.load(f)
    return []

def save_watchlist(tickers):
    with open(WATCHLIST_FILE, "w") as f:
        json.dump(sorted(list(set(tickers))), f)

def calculate_rsi(series, period=14):
    if len(series) < period + 1:
        return None
    delta = series.diff()
    gain = delta.where(delta > 0, 0).rolling(window=period).mean()
    loss = -delta.where(delta < 0, 0).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    val = rsi.iloc[-1]
    return round(val, 1) if not pd.isna(val) else None

def safe_pct(price, ma):
    if ma is None or pd.isna(ma) or ma == 0 or pd.isna(price):
        return None
    return round(((price - ma) / ma) * 100, 1)

def get_stock_data(ticker):
    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period="6mo", interval="1d")
        if hist.empty or len(hist) < 10:
            return {"ticker": ticker, "error": "No recent price data"}
        
        info = stock.info or {}
        close = hist["Close"].dropna()
        price = round(close.iloc[-1], 2)
        prev = close.iloc[-2] if len(close) > 1 else price
        change_pct = round(((price - prev) / prev) * 100, 2) if prev else 0
        
        rsi = calculate_rsi(close)
        sma20 = close.rolling(20).mean().iloc[-1] if len(close) >= 20 else None
        sma50 = close.rolling(50).mean().iloc[-1] if len(close) >= 50 else None
        
        pct_sma20 = safe_pct(price, sma20)
        
        # Simple scores with clear meaning
        pullback = 0
        pull_notes = []
        if pct_sma20 is not None and -12 <= pct_sma20 <= 2:
            pullback += 40
            pull_notes.append("Price near recent average")
        if rsi and 25 <= rsi <= 50:
            pullback += 35
            pull_notes.append(f"Momentum cooled (RSI {rsi})")
        if rsi and rsi < 30:
            pullback += 25
            pull_notes.append("Oversold")
        
        value = 0
        val_notes = []
        pe = info.get("trailingPE")
        if pe and 5 < pe < 30:
            value += 40
            val_notes.append(f"P/E {pe:.0f} (reasonable)")
        rev_g = info.get("revenueGrowth")
        if rev_g and rev_g > 0.05:
            value += 30
            val_notes.append(f"Growing revenue")
        high = info.get("fiftyTwoWeekHigh")
        if high and price < high * 0.85:
            value += 30
            val_notes.append("Off recent highs")
        
        combined = max(pullback, value)
        style = "Pullback" if pullback > value else "Value / Hold"
        
        # Mini chart data
        chart_df = close.tail(60).reset_index()
        
        return {
            "ticker": ticker,
            "name": (info.get("shortName") or ticker)[:30],
            "price": price,
            "change_pct": change_pct,
            "rsi": rsi,
            "pct_sma20": pct_sma20,
            "pullback": pullback,
            "value": value,
            "combined": combined,
            "style": style,
            "pull_notes": pull_notes,
            "val_notes": val_notes,
            "chart": chart_df,
            "summary": info.get("longBusinessSummary", "")[:180] + "..." if info.get("longBusinessSummary") else ""
        }
    except Exception as e:
        return {"ticker": ticker, "error": "Data unavailable"}

# UI
st.set_page_config(page_title="Entry Zones", layout="centered", page_icon="📈")
st.title("📈 Entry Zones")
st.caption("Simple signals for better entries. Not advice.")

# Sentiment
try:
    fg = fear_greed.get()
    s = fg["score"]
    st.metric("Market Mood", f"{s:.0f}", fg["rating"].title())
    if s < 40:
        st.success("Fearful market — often better for buying.")
    elif s > 70:
        st.warning("Greedy market — easier to overpay.")
    else:
        st.info("Neutral mood.")
except:
    st.info("Market mood unavailable.")

st.divider()

# Watchlist
watchlist = load_watchlist()
with st.expander("Add / Remove Stocks", expanded=not watchlist):
    new = st.text_input("Ticker", placeholder="TSLA").upper().strip()
    c1, c2 = st.columns(2)
    if c1.button("Add", use_container_width=True) and new:
        if new not in watchlist:
            watchlist.append(new)
            save_watchlist(watchlist)
            st.rerun()
    if watchlist and c2.button("Clear", use_container_width=True):
        save_watchlist([])
        st.rerun()
    if watchlist:
        rm = st.selectbox("Remove", [""] + watchlist)
        if st.button("Remove") and rm:
            watchlist.remove(rm)
            save_watchlist(watchlist)
            st.rerun()

if not watchlist:
    st.info("Add a ticker above to see signals.")
else:
    with st.spinner("Loading..."):
        data = [get_stock_data(t) for t in watchlist]
    
    data = sorted([d for d in data if d], key=lambda x: x.get("combined", 0), reverse=True)
    
    for d in data:
        with st.container(border=True):
            if "error" in d:
                st.subheader(d["ticker"])
                st.error(d["error"])
                continue
            
            # Header
            col1, col2 = st.columns([2, 1])
            with col1:
                st.subheader(f"{d['ticker']}  ${d['price']}")
                st.caption(d["name"])
            with col2:
                st.metric("Today", f"{d['change_pct']:+.1f}%")
            
            # Scores with plain meaning
            st.write(f"**Best signal right now: {d['style']}**  ({d['combined']}/100)")
            
            c1, c2 = st.columns(2)
            with c1:
                st.metric("Pullback score", d["pullback"], help="Higher = price pulled back toward its recent average with cooled momentum")
                if d["pull_notes"]:
                    st.caption(" • ".join(d["pull_notes"]))
                else:
                    st.caption("No clear pullback")
            with c2:
                st.metric("Value score", d["value"], help="Higher = cheaper relative to earnings/growth or off highs")
                if d["val_notes"]:
                    st.caption(" • ".join(d["val_notes"]))
                else:
                    st.caption("No strong value signal")
            
            # Mini chart
            if d.get("chart") is not None and not d["chart"].empty:
                fig = go.Figure(go.Scatter(x=d["chart"]["Date"], y=d["chart"]["Close"], mode="lines", line=dict(color="#1f77b4", width=2)))
                fig.update_layout(height=180, margin=dict(l=0, r=0, t=10, b=0), xaxis=dict(showticklabels=False), yaxis=dict(showticklabels=False), showlegend=False)
                st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
            
            if d.get("summary"):
                with st.expander("What this company does"):
                    st.write(d["summary"])
            
            if d["combined"] >= 50:
                st.success("Worth checking")
            elif d["combined"] >= 30:
                st.info("Moderate interest")
            else:
                st.caption("Weak signals")

st.caption(f"Updated {datetime.now().strftime('%H:%M')} • Data from Yahoo Finance • Not financial advice")
