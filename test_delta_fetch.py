"""
test_delta_fetch.py
Quick standalone test for the Yahoo Finance delta fetch.
Run with: python test_delta_fetch.py
"""
import yfinance as yf
import pandas as pd
from datetime import datetime, timezone

SYMBOL   = "GC=F"          # Gold Futures (XAUUSD equivalent)
INTERVAL = "1m"
YF_MAX_DAYS_1M = 6

now_utc = datetime.now(timezone.utc)

# Simulate the last known timestamp from HF Hub
# Change this to match your actual last candle
LAST_KNOWN = "2026-03-20 20:57:00"  # UTC
last_ts = pd.Timestamp(LAST_KNOWN, tz="UTC")

gap_hours = (now_utc - last_ts).total_seconds() / 3600
earliest_allowed = pd.Timestamp(now_utc - pd.Timedelta(days=YF_MAX_DAYS_1M))
fetch_start = pd.Timestamp(max(last_ts, earliest_allowed))

print("=" * 60)
print(f"  Symbol        : {SYMBOL}")
print(f"  Last candle   : {last_ts}")
print(f"  Now (UTC)     : {now_utc.strftime('%Y-%m-%d %H:%M:%S UTC')}")
print(f"  Gap           : {gap_hours:.1f} hours")
print(f"  Earliest 1m   : {earliest_allowed}")
print(f"  Fetch start   : {fetch_start}")
print(f"  Fetch end     : now")
print("=" * 60)

start_str = fetch_start.strftime("%Y-%m-%d")
end_str   = (pd.Timestamp(now_utc) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")  # +1d so today is included

print(f"\n📡 Calling: yf.Ticker('{SYMBOL}').history(start='{start_str}', end='{end_str}', interval='{INTERVAL}')")

try:
    ticker = yf.Ticker(SYMBOL)
    df = ticker.history(start=start_str, end=end_str, interval=INTERVAL)

    if df.empty:
        print("\n❌ RESULT: Empty DataFrame returned by Yahoo Finance.")
        print("   Possible reasons:")
        print("   1. Market was closed during the gap period (weekend/holiday)")
        print("   2. The gap start is too old (>7 days) for 1m interval")
        print("   3. Yahoo Finance rate-limited or symbol issue")

        # --- Fallback test: try period='7d' ---
        print("\n🔁 Fallback test: period='7d', interval='1m' ...")
        df2 = ticker.history(period="7d", interval="1m")
        if df2.empty:
            print("   ❌ Fallback also empty. Yahoo Finance may be rate-limiting or symbol invalid.")
        else:
            print(f"   ✅ Fallback succeeded! Got {len(df2):,} rows.")
            print(f"   First row: {df2.index[0]}")
            print(f"   Last row : {df2.index[-1]}")
    else:
        df = df.reset_index()
        time_col = next((c for c in df.columns if c.lower() in ("datetime", "date")), df.columns[0])
        df = df.rename(columns={time_col: 'time'})
        df['time'] = pd.to_datetime(df['time'], utc=True)
        print(f"\n✅ SUCCESS! Fetched {len(df):,} new candles.")
        print(f"   First : {df['time'].min()}")
        print(f"   Last  : {df['time'].max()}")
        print(f"\n   Columns: {list(df.columns)}")
        print(f"\n   Sample (first 3 rows):")
        print(df[['time','Open','High','Low','Close','Volume']].head(3).to_string(index=False))

except Exception as e:
    print(f"\n💥 EXCEPTION: {type(e).__name__}: {e}")
