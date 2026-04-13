"""
Data Sync Module
Handles: HuggingFace sync, Yahoo Finance, MT5 data sync, web search
Ported from app.py data_sync.py and web_search.py
"""

import os
import io
import json
import requests
import pandas as pd
from typing import Dict, Optional, Tuple, List
from datetime import datetime, timezone
from dotenv import load_dotenv

# Optional: yfinance (graceful fallback)
try:
    import yfinance as yf
    YFINANCE_AVAILABLE = True
except Exception as e:
    YFINANCE_AVAILABLE = False
    print(f"[WARNING] yfinance not available: {e}")

load_dotenv()

# ===== Yahoo Finance Mapping =====
YAHOO_MAPPING = {
    "XAUUSD": "GC=F",
    "EURUSD": "EURUSD=X",
    "DXY": "DX-Y.NYB",
    "^NSEI": "^NSEI",
    "^NSEBANK": "^NSEBANK"
}

# ===== MT5 Data Sync =====

def ping_mt5_server(mt5_url: str, mt5_token: str) -> Dict:
    """Ping MT5 server to check connection"""
    try:
        headers = {"X-MT5-Token": mt5_token}
        resp = requests.get(f"{mt5_url.rstrip('/')}/health", headers=headers, timeout=5)
        resp.raise_for_status()
        data = resp.json()
        return {
            "reachable": True,
            "mt5_initialized": data.get("mt5_initialized", False),
            "data": data
        }
    except Exception as e:
        return {
            "reachable": False,
            "mt5_initialized": False,
            "error": str(e)
        }


def pull_mt5_latest(mt5_url: str, symbol: str, timeframe: str, count: int = 1000, mt5_token: str = "impulse_secure_2026") -> pd.DataFrame:
    """Pull latest candles directly from MT5 server"""
    try:
        headers = {"X-MT5-Token": mt5_token}
        payload = {
            "symbol": symbol,
            "timeframe": timeframe,
            "count": count
        }
        resp = requests.post(
            f"{mt5_url.rstrip('/')}/data/fetch-latest",
            headers=headers,
            json=payload,
            timeout=15
        )
        resp.raise_for_status()
        data = resp.json()

        if not data or not data.get("data"):
            return pd.DataFrame()

        df = pd.DataFrame(data["data"])

        if "time" in df.columns:
            df["time"] = pd.to_datetime(df["time"])

        numeric_cols = ["open", "high", "low", "close", "volume", "tick_volume", "spread"]
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        return df

    except Exception as e:
        raise Exception(f"Failed to pull MT5 data: {e}")


# ===== HuggingFace Sync =====

def sync_hf_data(hf_repo: str, hf_token: str, symbol: str) -> Optional[pd.DataFrame]:
    """Pull latest data from HuggingFace Hub"""
    try:
        from huggingface_hub import hf_hub_download
        import tempfile

        # Download parquet file
        filename = f"{symbol}.parquet"
        file_path = hf_hub_download(
            repo_id=hf_repo,
            filename=filename,
            token=hf_token,
            repo_type="dataset"
        )

        df = pd.read_parquet(file_path)
        return df

    except Exception as e:
        print(f"⚠️ HuggingFace sync error for {symbol}: {e}")
        return None


def push_to_hf(hf_repo: str, hf_token: str, df: pd.DataFrame, symbol: str) -> bool:
    """Push DataFrame to HuggingFace Hub"""
    try:
        from huggingface_hub import HfApi
        import tempfile
        import os

        api = HfApi(token=hf_token)

        # Save to temp parquet
        with tempfile.NamedTemporaryFile(suffix='.parquet', delete=False) as tmp:
            df.to_parquet(tmp.name, index=False)
            tmp_path = tmp.name

        # Upload
        filename = f"{symbol}.parquet"
        api.upload_file(
            path_or_fileobj=tmp_path,
            path_in_repo=filename,
            repo_id=hf_repo,
            repo_type="dataset"
        )

        # Cleanup
        os.unlink(tmp_path)

        return True

    except Exception as e:
        print(f"⚠️ HuggingFace push error: {e}")
        return False


def sync_symbol(hf_repo: str, symbol: str, hf_token: str, mt5_url: str, mt5_token: str) -> Tuple[pd.DataFrame, Dict]:
    """
    Sync one symbol from MT5 → HuggingFace
    Returns: (updated_df, stats)
    """
    # 1. Pull from MT5
    mt5_df = pull_mt5_latest(mt5_url, symbol, "1m", count=1000, mt5_token=mt5_token)

    if mt5_df.empty:
        raise Exception(f"No data from MT5 for {symbol}")

    # 2. Pull from HuggingFace (if exists)
    hf_df = sync_hf_data(hf_repo, hf_token, symbol)

    if hf_df is not None and not hf_df.empty:
        # Merge: append new candles
        combined_df = pd.concat([hf_df, mt5_df], ignore_index=True)
        # Remove duplicates based on time
        combined_df = combined_df.drop_duplicates(subset=['time'], keep='last')
        combined_df = combined_df.sort_values('time').reset_index(drop=True)
    else:
        combined_df = mt5_df

    # 3. Push back to HuggingFace
    push_to_hf(hf_repo, hf_token, combined_df, symbol)

    stats = {
        "mt5_rows": len(mt5_df),
        "hf_rows": len(hf_df) if hf_df is not None else 0,
        "total_rows": len(combined_df),
        "new_rows": len(mt5_df)
    }

    return combined_df, stats


# ===== Yahoo Finance =====

def fetch_yahoo_data(symbol: str, period: str = "1y", interval: str = "1d") -> pd.DataFrame:
    """Fetch data from Yahoo Finance"""
    if not YFINANCE_AVAILABLE:
        raise Exception("yfinance not installed. Please run: pip install yfinance")

    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(period=period, interval=interval)

        if df.empty:
            raise Exception(f"No data for {symbol}")

        # Reset index and standardize columns
        df = df.reset_index()
        df.columns = [col.lower() if isinstance(col, str) else col for col in df.columns]

        # Rename to match our schema
        if 'date' in df.columns and 'time' not in df.columns:
            df = df.rename(columns={'date': 'time'})

        return df

    except Exception as e:
        raise Exception(f"Yahoo Finance fetch error: {e}")


def sync_yahoo_symbol(hf_repo: str, symbol: str, hf_token: str, period: str = "1y", interval: str = "1d") -> Tuple[pd.DataFrame, Dict]:
    """Fetch from Yahoo Finance and archive to HuggingFace"""
    # 1. Fetch from Yahoo
    df = fetch_yahoo_data(symbol, period, interval)

    # 2. Push to HuggingFace
    push_to_hf(hf_repo, hf_token, df, symbol)

    stats = {
        "total_rows": len(df),
        "filename": f"{symbol}.parquet"
    }

    return df, stats


# ===== Web Search (Market News & Sentiment) =====

def run_web_search(query: str, max_results: int = 5) -> List[Dict]:
    """
    Simple web search using DuckDuckGo (no API key needed)
    Returns list of {title, body, href}
    """
    try:
        from duckduckgo_search import DDGS

        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))

        return [
            {
                "title": r.get("title", ""),
                "body": r.get("body", ""),
                "href": r.get("href", "")
            }
            for r in results
        ]

    except ImportError:
        # Fallback: use a simple mock
        print("⚠️ duckduckgo_search not installed")
        return []
    except Exception as e:
        print(f"⚠️ Web search error: {e}")
        return []


def get_market_news(query: str, max_results: int = 5) -> List[Dict]:
    """Get market news related to query"""
    try:
        from duckduckgo_search import DDGS

        search_query = f"{query} market news trading"
        with DDGS() as ddgs:
            results = list(ddgs.news(keywords=search_query, max_results=max_results))

        return [
            {
                "title": r.get("title", ""),
                "body": r.get("body", ""),
                "href": r.get("url", ""),
                "date": r.get("date", "")
            }
            for r in results
        ]

    except ImportError:
        print("⚠️ duckduckgo_search not installed")
        return []
    except Exception as e:
        print(f"⚠️ News search error: {e}")
        return []


def analyze_sentiment(results: List[Dict]) -> str:
    """Analyze sentiment from search results"""
    if not results:
        return "Unable to determine - no results found"

    # Simple keyword-based sentiment analysis
    positive_words = [
        "bullish", "gain", "rise", "up", "growth", "positive", "rally",
        "surge", "boom", "strong", "higher", "optimistic", "recovery"
    ]
    negative_words = [
        "bearish", "drop", "fall", "down", "loss", "negative", "crash",
        "decline", "recession", "weak", "lower", "pessimistic", "risk"
    ]

    text = " ".join([r.get("body", "") + " " + r.get("title", "") for r in results]).lower()

    pos_count = sum(1 for word in positive_words if word in text)
    neg_count = sum(1 for word in negative_words if word in text)

    total = pos_count + neg_count
    if total == 0:
        return "Neutral"

    pos_ratio = pos_count / total

    if pos_ratio > 0.6:
        return "Bullish 🟢"
    elif pos_ratio < 0.4:
        return "Bearish 🔴"
    else:
        return "Neutral 🟡"


# ===== Auto-Sync Helper =====

def auto_sync_all(hf_repo: str, symbols: List[str], hf_token: str, mt5_url: str, mt5_token: str) -> Dict:
    """Auto-sync multiple symbols"""
    results = {}
    for symbol in symbols:
        try:
            df, stats = sync_symbol(hf_repo, symbol, hf_token, mt5_url, mt5_token)
            results[symbol] = {
                "success": True,
                "stats": stats
            }
        except Exception as e:
            results[symbol] = {
                "success": False,
                "error": str(e)
            }
    return results
