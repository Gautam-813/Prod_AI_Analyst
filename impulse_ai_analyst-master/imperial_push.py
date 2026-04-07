
import MetaTrader5 as mt5
import pandas as pd
import toml
from datetime import datetime, timedelta, timezone
import requests
import os
import tempfile
import time
from huggingface_hub import HfApi, create_repo, upload_file

# Clean character support for Windows
import sys
if sys.stdout.encoding != 'utf-8':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# ============================================================================
# Imperial Data Push (No Server Needed)
# ============================================================================
def imperial_push():
    print("\n" + "="*60)
    print(" [SYNC] IMPULSE AI - IMPERIAL DIRECT DATA PUSH (BYPASS SERVER)")
    print("="*60 + "\n")

    # 1. Load Secrets
    try:
        secrets = toml.load('.streamlit/secrets.toml')
        hf_token = secrets['HuggingFace_API_KEY']
        hf_repo = secrets['HF_REPO_ID']
        print(f"[OK] Credentials Loaded: {hf_repo}")
    except Exception as e:
        print(f"[ERROR] Error loading secrets: {e}")
        return

    # 2. Connect to MT5
    if not mt5.initialize():
        print("[ERROR] MT5 Initialization failed. Is terminal open?")
        return
    print("[OK] Connected to MT5 Terminal")

    api = HfApi()

    # 3. Process Symbols
    symbols = ["XAUUSD", "EURUSD"]
    for sym in symbols:
        print(f"\n>>> PROCESSING {sym} <<<")
        
        # Resolve real symbol name (m, pro, cent, etc.)
        all_syms = mt5.symbols_get()
        real_name = sym
        for s in all_syms:
            if sym.upper() in s.name.upper():
                real_name = s.name
                break
        
        print(f"SEARCH: Resolved '{sym}' -> '{real_name}'")
        
        # Step A: Download Old Data from Hub
        url = f"https://huggingface.co/datasets/{hf_repo}/resolve/main/{sym}_M1_Data.parquet"
        try:
            print(f"FETCH: Downloading current {sym} history from Hub...")
            old_df = pd.read_parquet(url, storage_options={"headers": {"Authorization": f"Bearer {hf_token}"}})
            last_timestamp = pd.to_datetime(old_df['time']).max()
            print(f"UPDATE: Last Record on Hub: {last_timestamp}")
        except:
            print("INFO: No existing data on Hub. Starting fresh.")
            old_df = pd.DataFrame()
            last_timestamp = datetime(2025, 1, 1)

        # Step B: Fetch Delta from MT5
        now = datetime.now()
        print(f"DELTA: Fetching missing: {last_timestamp} -> {now}")
        
        mt5.symbol_select(real_name, True)
        rates = mt5.copy_rates_range(real_name, mt5.TIMEFRAME_M1, last_timestamp, now)
        
        if rates is None or len(rates) == 0:
            print(f"NOTICE: {sym} remains up to date.")
            continue
            
        new_df = pd.DataFrame(rates)
        new_df['time'] = pd.to_datetime(new_df['time'], unit='s')
        
        # Step C: Merge and Deduplicate
        full_df = pd.concat([old_df, new_df]).drop_duplicates(subset=['time'], keep='last').sort_values('time')
        print(f"RESULT: Dataset now has {len(full_df):,} candles total (+{len(new_df)} new)")

        # Step D: Save and Push back to Hub
        with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as tmp:
            full_df.to_parquet(tmp.name)
            print(f"PUSH: Uploading {sym} to Hub...")
            api.upload_file(
                path_or_fileobj=tmp.name,
                path_in_repo=f"{sym}_M1_Data.parquet",
                repo_id=hf_repo,
                repo_type="dataset",
                token=hf_token
            )
            print(f"DONE: {sym} INTEGRATED INTO HUB!")
            time.sleep(2)
            try:
                os.unlink(tmp.name)
            except:
                pass

    mt5.shutdown()
    print("\n" + "="*60)
    print(" [FINISH] IMPERIAL PUSH COMPLETED")
    print("="*60 + "\n")

if __name__ == "__main__":
    imperial_push()
