
import MetaTrader5 as mt5
import pandas as pd
import toml
from datetime import datetime
import os
import tempfile
import time
from huggingface_hub import HfApi

# 1. ENFORCE UTF-8 for Clean Console Output
import sys
if sys.stdout.encoding != 'utf-8':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

def run_master_sync():
    print("\n" + "="*60)
    print(" 👸 IMPERIAL MASTER SYNC - RESOLVING COLUMN CASE & PUSHING")
    print("="*60 + "\n")

    # A. Load Credentials
    try:
        secrets = toml.load('.streamlit/secrets.toml')
        hf_token = secrets['HuggingFace_API_KEY']
        hf_repo = secrets['HF_REPO_ID']
        print(f"[OK] Credentials Loaded: {hf_repo}")
    except Exception as e:
        print(f"[ERROR] Could not load secrets: {e}")
        return

    # B. Initialize MT5 (Direct Connection)
    if not mt5.initialize():
        print("[ERROR] MT5 Initialization failed. Is terminal open?")
        return
    print("[OK] Connected to MetaTrader 5")

    api = HfApi()
    symbols = ["XAUUSD", "EURUSD", "DXY"]

    # Mapping Column Names (Local Title Case -> Cloud Lowercase)
    # ['Time', 'Open', 'High', 'Low', 'Close', 'TickVolume', 'Spread', 'Volume']
    RENAME_MAP = {
        'Time': 'time',
        'Open': 'open',
        'High': 'high',
        'Low': 'low',
        'Close': 'close',
        'TickVolume': 'tick_volume',
        'Spread': 'spread',
        'Volume': 'real_volume'
    }

    for sym in symbols:
        print(f"\n>>> PROCESSING {sym} <<<")
        local_path = f"{sym}_M1_Data.parquet"
        
        if not os.path.exists(local_path):
            print(f"⚠️ Skip: Local file {local_path} not found.")
            continue

        # 1. Load Local Master (Title Case)
        try:
            print(f"📁 Loading local history from {local_path}...")
            df = pd.read_parquet(local_path)
            
            # Map column names if they are Title Case
            if 'Time' in df.columns:
                print(f"   📉 Renaming TitleCase columns to lowercase to match Webapp standards.")
                df = df.rename(columns=RENAME_MAP)
            
            # Ensure time is datetime
            df['time'] = pd.to_datetime(df['time'])
            start_date = df['time'].min()
            last_date = df['time'].max()
            print(f"   📅 Local Range: {start_date} -> {last_date}")
        except Exception as e:
            print(f"[ERROR] Failed to process local {sym}: {e}")
            continue

        # 2. Fetch missing gap from MT5
        now = datetime.now()
        print(f"📈 Fetching newest candles from {last_date} until {now}...")
        
        # Resolve real symbol name (suffix check)
        all_syms = mt5.symbols_get()
        real_symbol = sym
        for s in all_syms:
            if sym.upper() in s.name.upper():
                real_symbol = s.name
                break
        
        mt5.symbol_select(real_symbol, True)
        rates = mt5.copy_rates_range(real_symbol, mt5.TIMEFRAME_M1, last_date, now)

        if rates is not None and len(rates) > 0:
            new_df = pd.DataFrame(rates)
            new_df['time'] = pd.to_datetime(new_df['time'], unit='s')
            
            # Combine, Deduplicate, Sort
            df = pd.concat([df, new_df]).drop_duplicates(subset=['time'], keep='last').sort_values('time')
            print(f"   ✨ Merged! Total history is now {len(df):,} candles.")
        else:
            print("   ✅ No new candles items found in MT5 (already up-to-date).")

        # 3. Save to Temporary File & Push to Hub
        with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as tmp:
            df.to_parquet(tmp.name)
            tmp_path = tmp.name
        
        print(f"📤 Pushing Full Master to {hf_repo}...")
        try:
            api.upload_file(
                path_or_fileobj=tmp_path,
                path_in_repo=f"{sym}_M1_Data.parquet",
                repo_id=hf_repo,
                repo_type="dataset",
                token=hf_token
            )
            print(f"🏆 {sym} MASTER SYNC SUCCESS!")
        except Exception as e:
            print(f"[ERROR] Failed to upload {sym}: {e}")
        finally:
            # Cleanup temp file
            time.sleep(2)
            try: os.remove(tmp_path)
            except: pass

    mt5.shutdown()
    print("\n" + "="*60)
    print(" 📊 ALL MULTI-YEAR MASTERS ARE NOW ON CLOUD!")
    print("="*60 + "\n")

if __name__ == "__main__":
    run_master_sync()
