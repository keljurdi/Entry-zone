# Entry Zone Tracker

Pullback entries in uptrends only (SMA + RSI + volume). Designed to reduce FOMO.

## Use on your phone (recommended)

1. Put the files in a public GitHub repo.
2. Go to [share.streamlit.io](https://share.streamlit.io) → Sign in with GitHub.
3. Create app → select repo + `stock_entry_tool.py`.
4. Deploy. You get a URL like `https://yourname.streamlit.app`.
5. Open on phone → Add to Home Screen.

Watchlist saves in the browser session / local file on the server (for personal use this is fine).

## Local run

```bash
pip install -r requirements.txt
streamlit run stock_entry_tool.py
```

## Scoring logic (trend-filtered)

- Must be above rising SMA50 (uptrend filter)
- Near SMA20 or SMA50
- RSI cooling (30–55) or oversold only if still in trend
- Volume dry-up on the pullback

Higher score = more conditions met. Not financial advice.
