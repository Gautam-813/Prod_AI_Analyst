import os
import streamlit as st
from huggingface_hub import HfApi, create_repo, upload_file

# Load secrets manually from the file (Streamlit secrets might not be available if not running through streamlit run)
import toml
secrets = toml.load(".streamlit/secrets.toml")

HF_TOKEN = secrets.get("HuggingFace_API_KEY")
REPO_ID = secrets.get("HF_REPO_ID")

if not HF_TOKEN or not REPO_ID:
    print("❌ Error: HuggingFace_API_KEY or HF_REPO_ID missing in .streamlit/secrets.toml")
    exit(1)

api = HfApi()

def initialize_hf_repo():
    print(f"🔄 Checking repository: {REPO_ID}...")
    try:
        api.repo_info(repo_id=REPO_ID, repo_type="dataset", token=HF_TOKEN)
        print("✅ Repository already exists.")
    except Exception:
        print(f"🆕 Creating NEW private repository: {REPO_ID}...")
        try:
            create_repo(repo_id=REPO_ID, repo_type="dataset", token=HF_TOKEN, private=True)
            print("✅ Successfully created private repository.")
        except Exception as e:
            print(f"❌ Failed to create repo: {e}")
            return False
    return True

def upload_initial_files():
    files_to_upload = ["XAUUSD_M1_Data.parquet", "EURUSD_M1_Data.parquet"]
    
    for filename in files_to_upload:
        if os.path.exists(filename):
            print(f"⬆️ Uploading {filename} to HF Hub...")
            try:
                upload_file(
                    path_or_fileobj=filename,
                    path_in_repo=filename,
                    repo_id=REPO_ID,
                    repo_type="dataset",
                    token=HF_TOKEN,
                    commit_message=f"Initial upload of {filename}"
                )
                print(f"✅ {filename} uploaded successfully.")
            except Exception as e:
                print(f"❌ Failed to upload {filename}: {e}")
        else:
            print(f"⚠️ Skipping {filename} (not found locally in d:\\date-wise\\17-03-2026)")

if __name__ == "__main__":
    print("="*60)
    print("🚀 Hugging Face Hub One-Time Setup")
    print("="*60)
    
    if initialize_hf_repo():
        upload_initial_files()
        print("\n🎉 Setup Complete! Your data is now secured on Hugging Face Hub.")
        print("   You can now use the 'Live Data Sync' buttons in the Streamlit app sidebar.")
    print("="*60)
