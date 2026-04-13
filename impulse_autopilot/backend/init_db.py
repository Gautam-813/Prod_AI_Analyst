"""
Database Initialization Script
Run this to create tables and seed initial data
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from database import init_db, SessionLocal
from models import AutopilotConfig, PromptTemplate
import os as os_module
from dotenv import load_dotenv

load_dotenv()

def seed_prompts():
    """Load prompts from test_prompt.txt if it exists"""
    db = SessionLocal()
    try:
        # Check if prompts already exist
        existing = db.query(PromptTemplate).first()
        if existing:
            print("⏭️ Prompts already exist, skipping seed")
            return

        # Try to load from test_prompt.txt in parent directory
        prompt_file = os.path.join(os.path.dirname(__file__), "..", "test_prompt.txt")
        
        if os_module.path.exists(prompt_file):
            with open(prompt_file, "r", encoding="utf-8") as f:
                lines = [line.strip() for line in f.readlines() if line.strip() and "." in line]
            
            print(f"📝 Found {len(lines)} prompts in test_prompt.txt")
            
            for line in lines:
                try:
                    prompt_num = int(line.split(".")[0].strip())
                    prompt_text = line.split(".", 1)[1].strip()
                    
                    prompt = PromptTemplate(
                        prompt_num=prompt_num,
                        prompt_text=prompt_text,
                        active=True
                    )
                    db.add(prompt)
                except Exception as e:
                    print(f"⚠️ Skipping invalid prompt: {line[:50]}... ({e})")
            
            db.commit()
            print(f"✅ Seeded {len(lines)} prompts")
        else:
            print("⚠️ test_prompt.txt not found, adding sample prompts")
            # Add some sample prompts
            sample_prompts = [
                PromptTemplate(prompt_num=1, prompt_text="Identify key support and resistance levels", active=True),
                PromptTemplate(prompt_num=2, prompt_text="Find breakout opportunities with volume confirmation", active=True),
                PromptTemplate(prompt_num=3, prompt_text="Detect trend reversal patterns", active=True),
            ]
            db.add_all(sample_prompts)
            db.commit()
            print("✅ Added 3 sample prompts")
    except Exception as e:
        print(f"❌ Error seeding prompts: {e}")
        db.rollback()
    finally:
        db.close()

def seed_config():
    """Create default configuration"""
    db = SessionLocal()
    try:
        # Check if config already exists
        existing = db.query(AutopilotConfig).first()
        if existing:
            print("⏭️ Configuration already exists, skipping seed")
            return

        config = AutopilotConfig(
            enabled=False,
            interval_seconds=int(os_module.getenv("AUTOPILOT_INTERVAL", "300")),
            lot_size=float(os_module.getenv("DEFAULT_LOT_SIZE", "0.10")),
            symbol=os_module.getenv("DEFAULT_SYMBOL", "XAUUSD"),
            timeframe=os_module.getenv("DEFAULT_TIMEFRAME", "1m"),
            candle_count=int(os_module.getenv("DEFAULT_CANDLE_COUNT", "1000")),
            ai_provider=os_module.getenv("AI_PROVIDER", "NVIDIA"),
            api_key=os_module.getenv("NVIDIA_API_KEY", ""),
            model_name=os_module.getenv("MODEL_NAME", "qwen/qwen3.5-122b-a10b"),
            base_url=os_module.getenv("BASE_URL", "https://integrate.api.nvidia.com/v1"),
            mt5_url=os_module.getenv("MT5_URL", "http://localhost:5000"),
            mt5_token=os_module.getenv("MT5_TOKEN", "impulse_secure_2026"),
            success_count=0,
            error_count=0
        )
        db.add(config)
        db.commit()
        print("✅ Created default configuration")
    except Exception as e:
        print(f"❌ Error seeding config: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    print("🚀 Initializing database...")
    
    # Create tables
    init_db()
    
    # Seed data
    seed_prompts()
    seed_config()
    
    print("\n✅ Database initialization complete!")
    print("📊 Database file: data/autopilot.db")
