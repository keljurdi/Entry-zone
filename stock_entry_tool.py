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
    if len(series) < period + 1:
        return None
    delta = series.diff()
    gain = delta.where(delta > 0, 0).rolling(window=period).mean()
    loss = -delta.where(delta < 0, 0).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi.iloc[-1] if not pd.isna(rsi.iloc[-1]) else None

def safe_pct(price, ma):
    if ma is None or pd.isna(ma) or ma == 0 or pd.isna(price):
        return None
    return ((price - ma) / ma) * 100

def get_stock_data(ticker):
    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period="1y")
        if hist.empty or len(hist) < 15:
            return {"ticker": ticker, "error": "Not enough price history"}
        
        info = stock.info or {}
        close = hist["Close"].dropna()
        if len(close) < 15:
            return {"ticker": ticker, "error": "Not enough clean price data"}
        
        price = close.iloc[-1]
        rsi = calculate_rsi(close)
        sma20 = close.rolling(20).mean().iloc[-1] if len(close) >= 20 else None
        sma50 = close.rolling(50).mean().iloc[-1] if len(close) >= 50 else None
        sma200 = close.rolling(200).mean().iloc[-1] if len(close) >= 200 else None
        
        pct_sma20 = safe_pct(price, sma20)
        pct_sma50 = safe_pct(price, sma50)
        
        volume = hist["Volume"].iloc[-1] if not hist["Volume"].empty else 0
        avg_volume = hist["Volume"].tail(20).mean() if len(hist) >= 20 else volume
        
        # --- Pullback / Swing score ---
        pullback_score = 0
        pullback_reasons = []
        
        above_sma50 = sma50 is not None and not pd.isna(sma50) and price > sma50
        if above_sma50:
            pullback_score += 20
            pullback_reasons.append("Above SMA50")
        
        if pct_sma20 is not None and -10 < pct_sma20 < 3:
            pullback_score += 30
            pullback_reasons.append(f"Near SMA20 ({pct_sma20:+.1f}%)")
        elif pct_sma50 is not None and -6 < pct_sma50 < 4:
            pullback_score += 20
            pullback_reasons.append(f"Near SMA50 ({pct_sma50:+.1f}%)")
        
        if rsi is not None and 30 < rsi < 55:
            pullback_score += 25
            pullback_reasons.append(f"RSI cooling ({rsi:.0f})")
        elif rsi is not None and rsi < 30 and above_sma50:
            pullback_score += 15
            pullback_reasons.append(f"RSI oversold in trend ({rsi:.0f})")
        
        if avg_volume and volume < avg_volume * 0.9:
            pullback_score += 15
            pullback_reasons.append("Volume dry-up")
        
        # --- Value / Long-term Hold score ---
        value_score = 0
        value_reasons = []
        
        pe = info.get("trailingPE") or info.get("forwardPE")
        if pe and 0 < pe < 25:
            value_score += 25
            value_reasons.append(f"Reasonable P/E ({pe:.1f})")
        elif pe and pe < 40:
            value_score += 10
            value_reasons.append(f"Moderate P/E ({pe:.1f})")
        
        rev_growth = info.get("revenueGrowth")
        if rev_growth and rev_growth > 0.10:
            value_score += 25
            value_reasons.append(f"Revenue growth {rev_growth*100:.0f}%")
        elif rev_growth and rev_growth > 0:
            value_score += 10
            value_reasons.append(f"Positive revenue growth")
        
        margins = info.get("profitMargins")
        if margins and margins > 0.10:
            value_score += 20
            value_reasons.append(f"Solid margins ({margins*100:.0f}%)")
        
        high_52 = info.get("fiftyTwoWeekHigh")
        if high_52 and price:
            dist_from_high = ((high_52 - price) / high_52) * 100
            if dist_from_high > 15:
                value_score += 20
                value_reasons.append(f"{dist_from_high:.0f}% off 52w high")
            elif dist_from_high > 5:
                value_score += 10
                value_reasons.append(f"{dist_from_high:.0f}% off highs")
        
        # Combined
        combined = max(pullback_score, value_score)
        style = "Pullback" if pullback_score >= value_score else "Value/Hold"
        
        return {
            "ticker": ticker,
            "name": (info.get("shortName") or ticker)[:28],
            "price": price,
            "rsi": rsi,
            "pct_sma20": pct_sma20,
            "pullback_score": min(pullback_score, 100),
            "value_score": min(value_score, 100),
            "combined": min(combined, 100),
            "style": style,
            "pullback_reasons": pullback_reasons,
            "value_reasons": value_reasons,
            "change_pct": ((price - close.iloc[-2]) / close.iloc[-2]) * 100 if len(close) > 1 else 0,
        }
    except Exception as e:
        return {"ticker": ticker, "error": str(e)[:80]}

# --- UI ---
st.set_page_config(page_title="Entry Zone Tracker", layout="centered")
st.title("🎯 Entry Zones")
st.caption("Pullbacks + long-term value. Reduce FOMO.")

# Market sentiment
try:
    fg = fear_greed.get()
    st.metric("Fear & Greed", f"{fg['score']:.0f}", fg["rating"].title())
    if fg["score"] < 40:
        st.success("Fear zone — better environment for entries.")
    elif fg["score"] > 70:
        st.warning("Greed zone — higher FOMO risk. Be selective.")
    else:
        st.info("Neutral market.")
except:
    st.warning("Fear & Greed unavailable.")

st.divider()

# Watchlist
watchlist = load_watchlist()

with st.expander("Manage Watchlist", expanded=len(watchlist) == 0):
    new_ticker = st.text_input("Add ticker", placeholder="TSLA, MU, NBIS").upper().strip()
    c1, c2 = st.columns(2)
    if c1.button("Add", use_container_width=True) and new_ticker:
        if new_ticker not in watchlist:
            watchlist.append(new_ticker)
            save_watchlist(watchlist)
            st.rerun()
    if watchlist and c2.button("Clear All", use_container_width=True):
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
            if r:
                results.append(r)
    
    if results:
        results = sorted(results, key=lambda x: x.get("combined", 0), reverse=True)
        for r in results:
            with st.container(border=True):
                if "error" in r:
                    st.markdown(f"### {r['ticker']}")
                    st.error(r["error"])
                    continue
                
                st.markdown(f"### {r['ticker']} — ${r['price']:.2f} ({r['change_pct']:+.1f}%)")
                c1, c2, c3 = st.columns(3)
                c1.metric("Combined", r["combined"])
                c2.metric("Pullback", r["pullback_score"])
                c3.metric("Value/Hold", r["value_score"])
                
                st.caption(f"Best fit: **{r['style']}**")
                
                if r["pullback_reasons"]:
                    st.write("**Pullback:** " + " • ".join(r["pullback_reasons"]))
                if r["value_reasons"]:
                    st.write("**Value:** " + " • ".join(r["value_reasons"]))
                
                if r["combined"] >= 40:
                    st.success("Worth a look")
                elif r["combined"] < 20:
                    st.caption("Weak signals right now")
    else:
        st.error("No data loaded.")

st.caption(f"Updated {datetime.now().strftime('%H:%M')} | Yahoo + CNN F&G | Not advice")
