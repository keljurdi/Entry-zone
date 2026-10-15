import streamlit as st
import yfinance as yf
import pandas as pd
import json
import os
from datetime import datetime
import fear_greed

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
    delta = series.diff()
    gain = delta.where(delta > 0, 0).rolling(window=period).mean()
    loss = -delta.where(delta < 0, 0).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def get_stock_data(ticker):
    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period="1y")
        if hist.empty or len(hist) < 50:
            return None
        info = stock.info
        close = hist["Close"]
        rsi = calculate_rsi(close).iloc[-1]
        sma20 = close.rolling(20).mean().iloc[-1]
        sma50 = close.rolling(50).mean().iloc[-1]
        sma200 = close.rolling(200).mean().iloc[-1] if len(close) >= 200 else None
        price = close.iloc[-1]
        volume = hist["Volume"].iloc[-1]
        avg_volume = hist["Volume"].tail(20).mean()
        
        pct_from_sma20 = ((price - sma20) / sma20) * 100 if sma20 else 0
        pct_from_sma50 = ((price - sma50) / sma50) * 100 if sma50 else 0
        above_sma50 = price > sma50
        above_sma200 = price > sma200 if sma200 else False
        sma50_rising = sma50 > close.rolling(50).mean().iloc[-5] if len(close) > 55 else False
        
        # Trend-filtered pullback score (higher = better entry)
        score = 0
        reasons = []
        
        if above_sma50 and sma50_rising:
            score += 25
            reasons.append("Uptrend (above rising SMA50)")
        if above_sma200:
            score += 15
            reasons.append("Above SMA200")
        
        if -8 < pct_from_sma20 < 2:
            score += 30
            reasons.append(f"Near SMA20 ({pct_from_sma20:+.1f}%)")
        elif -5 < pct_from_sma50 < 3:
            score += 20
            reasons.append(f"Near SMA50 ({pct_from_sma50:+.1f}%)")
        
        if 30 < rsi < 55:
            score += 20
            reasons.append(f"RSI cooling ({rsi:.0f})")
        elif rsi < 30 and above_sma50:
            score += 15
            reasons.append(f"RSI oversold in trend ({rsi:.0f})")
        
        if volume < avg_volume * 0.85:
            score += 10
            reasons.append("Volume dry-up")
        
        return {
            "ticker": ticker,
            "name": info.get("shortName", ticker)[:25],
            "price": price,
            "rsi": rsi,
            "pct_sma20": pct_from_sma20,
            "pct_sma50": pct_from_sma50,
            "score": min(score, 100),
            "reasons": reasons,
            "change_pct": ((price - close.iloc[-2]) / close.iloc[-2]) * 100 if len(close) > 1 else 0,
            "above_trend": above_sma50
        }
    except Exception as e:
        return {"ticker": ticker, "error": str(e)}

# --- UI (mobile-friendly) ---
st.set_page_config(page_title="Entry Zone Tracker", layout="centered")
st.title("🎯 Entry Zones")
st.caption("Pullbacks in uptrends only. Kill FOMO.")

# Market sentiment
try:
    fg = fear_greed.get()
    score = fg["score"]
    rating = fg["rating"].title()
    st.metric("Fear & Greed", f"{score:.0f}", rating)
    if score < 40:
        st.success("Fear zone — better environment for entries.")
    elif score > 70:
        st.warning("Greed zone — higher FOMO risk. Be selective.")
    else:
        st.info("Neutral market.")
except:
    st.warning("Fear & Greed unavailable.")

st.divider()

# Watchlist
watchlist = load_watchlist()

with st.expander("Manage Watchlist", expanded=len(watchlist) == 0):
    new_ticker = st.text_input("Add ticker", placeholder="TSLA").upper().strip()
    col1, col2 = st.columns(2)
    if col1.button("Add", use_container_width=True) and new_ticker:
        if new_ticker not in watchlist:
            watchlist.append(new_ticker)
            save_watchlist(watchlist)
            st.rerun()
    if watchlist and col2.button("Clear All", use_container_width=True):
        save_watchlist([])
        st.rerun()
    
    if watchlist:
        remove = st.selectbox("Remove", [""] + watchlist)
        if st.button("Remove selected") and remove:
            watchlist.remove(remove)
            save_watchlist(watchlist)
            st.rerun()
    st.caption(f"{len(watchlist)} saved")

# Results
if not watchlist:
    st.info("Add tickers above to start.")
else:
    results = []
    with st.spinner("Loading..."):
        for t in watchlist:
            r = get_stock_data(t)
            if r and "error" not in r:
                results.append(r)
    
    if results:
        results = sorted(results, key=lambda x: x["score"], reverse=True)
        for r in results:
            with st.container(border=True):
                st.markdown(f"### {r['ticker']} — ${r['price']:.2f} ({r['change_pct']:+.1f}%)")
                c1, c2, c3 = st.columns(3)
                c1.metric("Score", r["score"])
                c2.metric("RSI", f"{r['rsi']:.0f}")
                c3.metric("vs SMA20", f"{r['pct_sma20']:+.1f}%")
                if r["reasons"]:
                    st.write(" • ".join(r["reasons"]))
                else:
                    st.write("No clear pullback zone.")
                if r["score"] >= 50 and r["above_trend"]:
                    st.success("Potential zone")
                elif not r["above_trend"]:
                    st.caption("Not in uptrend — skip")
    else:
        st.error("No data loaded.")

st.caption(f"Updated {datetime.now().strftime('%H:%M')} | Yahoo + CNN F&G | Not advice")
