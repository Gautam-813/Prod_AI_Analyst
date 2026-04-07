
import toml
import data_sync
from datetime import datetime, timezone
import requests

def run_full_sync():
    print("\n" + "="*50)
    print(" 🚀 IMPULSE AI — FULL DATA SYNC TO HUB")
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

    # 2. Server Configuration (Targeting your running EXE)
    # We will try Port 5000, 5001, and 5002 automatically
    ports = [5000, 5001, 5002]
    server_url = None
    server_token = "impulse_secure_2026"

    for port in ports:
        url = f"http://localhost:{port}"
        print(f"🔍 Checking MT5 Server on Port {port}...")
        try:
            status = data_sync.ping_mt5_server(url, server_token)
            if status['reachable'] and status['mt5_initialized']:
                server_url = url
                print(f"✅ MT5 Server CONNECTED on {url}")
                break
        except:
            continue

    if not server_url:
        print("❌ Could not reach MT5 Server. Please ensure MT5_Impulse_Data_Server.exe is running!")
        return

    # 3. Perform Sync for Target Symbols
    target_symbols = ["XAUUSD", "EURUSD"]
    
    for sym in target_symbols:
        print(f"\n🔄 --- SYNCING {sym} ---")
        try:
            # Full Smart Delta Sync until Now
            updated_df, stats = data_sync.sync_symbol(
                hf_repo, 
                sym, 
                hf_token, 
                server_url, 
                server_token
            )
            
            if stats['status'] == 'already_fresh':
                print(f"✅ {sym} is already up to date ({stats['label']})")
            else:
                print(f"✅ SUCCESS: {sym} updated!")
                print(f"   📊 Received: {stats.get('new_rows', 0)} new candles")
                print(f"   📂 Final Shape: {updated_df.shape}")
                
        except Exception as e:
            print(f"❌ FAILED to sync {sym}: {e}")

    print("\n" + "="*50)
    print(" 🏁 SYNC COMPLETED")
    print("="*50 + "\n")

if __name__ == "__main__":
    run_full_sync()
