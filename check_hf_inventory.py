
import toml
import data_sync
import pandas as pd

def check_inventory():
    print("\n" + "="*50)
    print(" ☁️  IMPULSE AI — HUGGING FACE INVENTORY")
    print("="*50 + "\n")

    # 1. Load Secrets
    try:
        secrets = toml.load('.streamlit/secrets.toml')
        hf_token = secrets['HuggingFace_API_KEY']
        hf_repo = secrets['HF_REPO_ID']
        print(f"✅ Credentials Loaded for Repo: {hf_repo}")
    except Exception as e:
        print(f"❌ Error loading secrets: {e}")
        return

    # 2. Check each target symbol
    target_symbols = ["XAUUSD", "EURUSD"]
    
    for sym in target_symbols:
        print(f"\n--- 📊 {sym} ---")
        try:
            # Load from HF Hub
            df = data_sync.load_from_hf(hf_repo, sym, hf_token)

            if df.empty:
                print("⚠️ Dataset is empty or not found.")
            else:
                # Calculate Range
                # Convert time to datetime if it's not already
                df['time'] = pd.to_datetime(df['time'])
                first = df['time'].min()
                last = df['time'].max()
                count = len(df)

                print(f"📅 First Candle: {first}")
                print(f"📅 Latest Candle: {last}")
                print(f"📊 Total History: {count:,} rows")
                
        except Exception as e:
            print(f"❌ Could not reach {sym}: {e}")

    print("\n" + "="*50)
    print(" 🏁 INVENTORY COMPLETED")
    print("="*50 + "\n")

if __name__ == "__main__":
    check_inventory()
