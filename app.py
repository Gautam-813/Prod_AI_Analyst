
import streamlit as st
import os
import pandas as pd
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import requests
import json
import io
import sys
import time
import traceback
import contextlib
import plotly.express as px
import plotly.graph_objects as go
import matplotlib.pyplot as plt
import seaborn as sns
import re
import math
import scipy
import altair as alt
import sklearn
from openai import OpenAI
import pandas_ta_classic as ta
import statsmodels.api as sm
import quantstats as qs
import duckdb
import polars as pl
import xgboost as xgb
from datetime import datetime, timezone, timedelta
import contextlib
import io
from streamlit_autorefresh import st_autorefresh
from data_sync import pull_mt5_latest, ping_mt5_server
from memory_system import load_all_memory, save_conversation_summary, save_insight, save_preference, update_stats, build_memory_context, save_feedback, load_feedback, get_feedback_stats
from login_page import check_auth

# ============================================================================
# News Detection & Fetching
# ============================================================================
NEWS_KEYWORDS = ["today", "news", "market", "performance", "sentiment", "fomc", "events", "latest", "current", "outlook", "update", "breaking", "economic", "currency", "forex"]

COMMON_SYMBOLS = {
    "gold": "XAUUSD", "xauusd": "XAUUSD", "xau": "XAUUSD",
    "silver": "XAGUSD", "xagusd": "XAGUSD", "xag": "XAGUSD",
    "eurusd": "EURUSD", "eur/usd": "EURUSD",
    "gbpusd": "GBPUSD", "gbp/usd": "GBPUSD",
    "usdjpy": "USDJPY", "usd/jpy": "USDJPY",
    "audusd": "AUDUSD", "aud/usd": "AUDUSD",
    "usdchf": "USDCHF", "usd/chf": "USDCHF",
    "nzdusd": "NZDUSD", "nzd/usd": "NZDUSD",
    "btc": "BTCUSD", "bitcoin": "BTCUSD",
    "oil": "USOIL", "crude": "USOIL",
    "sp500": "SPX", "spy": "SPX",
    "nasdaq": "NDX", "nvda": "NVDA", "tesla": "TSLA", "apple": "AAPL"
}

def contains_news_keywords(text: str) -> bool:
    """Check if the prompt contains news-related keywords."""
    text_lower = text.lower()
    return any(keyword in text_lower for keyword in NEWS_KEYWORDS)

def extract_symbol_from_prompt(prompt: str) -> str:
    """Extract trading symbol from the user's prompt using dynamic broker symbols."""
    prompt_upper = prompt.upper()
    
    # First: Check against broker's available symbols
    available_syms = st.session_state.get("available_symbols", [])
    if available_syms:
        for sym in available_syms:
            if sym in prompt_upper:
                return sym
    
    # Fallback: Check common aliases
    COMMON_ALIASES = {
        "gold": "XAUUSD", "silver": "XAGUSD",
        "eurusd": "EURUSD", "gbpusd": "GBPUSD",
        "usdjpy": "USDJPY", "audusd": "AUDUSD",
        "btc": "BTCUSD", "bitcoin": "BTCUSD",
    }
    prompt_lower = prompt.lower()
    for name, symbol in COMMON_ALIASES.items():
        if name in prompt_lower:
            return symbol
    
    # Fallback: Regex for common symbols
    import re
    pattern = r'\b([A-Z]{2,6})\b'
    matches = re.findall(pattern, prompt_upper)
    for match in matches:
        if match in ["XAU", "EUR", "GBP", "USD", "JPY", "AUD", "CHF", "NZD", "BTC", "SPX", "NDX"]:
            symbol_map = {"XAU": "XAUUSD", "EUR": "EURUSD", "GBP": "GBPUSD", "USD": "USDJPY", "BTC": "BTCUSD", "SPX": "SPX", "NDX": "NDX"}
            if match in symbol_map:
                return symbol_map[match]
    
    return None

def fetch_news_for_symbol(symbol: str) -> str:
    """Fetch latest news for a symbol using Yahoo Finance."""
    import yfinance as yf
    
    try:
        ticker = yf.Ticker(symbol)
        news = ticker.news
        
        if not news:
            return None
        
        news_items = []
        for item in news[:5]:
            title = item.get("title", "")
            publisher = item.get("publisher", "")
            if title:
                news_items.append(f"• {title} ({publisher})")
        
        if news_items:
            return "\n".join(news_items)
        return None
    except Exception as e:
        print(f"[News] Could not fetch news for {symbol}: {e}")
        return None

def build_news_context(prompt: str) -> str:
    """Build news context for the AI prompt if user asks about news."""
    if not contains_news_keywords(prompt):
        return ""
    
    symbol = extract_symbol_from_prompt(prompt)
    if not symbol:
        return ""
    
    news = fetch_news_for_symbol(symbol)
    if not news:
        return ""
    
    return f"""
📰 TODAY'S MARKET NEWS FOR {symbol}:
{news}
"""

# ============================================================================
# Trade Execution & Management Helpers
# ============================================================================
# --- PERSISTENT CONNECTION POOL (ASAP Speed) ---
if 'api_session' not in st.session_state:
    st.session_state.api_session = requests.Session()

def get_session():
    return st.session_state.api_session

# --- SAFE SECRET RESOLVER (Works on Render and Local) ---
def get_secret(key, default=""):
    """Safely retrieves a secret from Environment Variables (Render) or st.secrets (Local)."""
    # 1. Try Environment Variables (Primary for Render)
    try:
        val = os.environ.get(key)
        if val:
            return val
    except:
        pass

    # 2. Try Streamlit Secrets (Secondary for Local)
    try:
        # Wrap everything in a try-except because st.secrets can throw 
        # StreamlitSecretNotFoundError just by being accessed/checked.
        if key in st.secrets:
            return st.secrets.get(key, default)
    except Exception:
        # If secrets.toml is missing and no secrets are set, Streamlit raises an error
        pass

    return default

# --- CALLBACK STATES ---
if 'executing' not in st.session_state:
    st.session_state.executing = False
if 'last_exec_msg' not in st.session_state:
    st.session_state.last_exec_msg = ""
if 'autopilot_enabled' not in st.session_state:
    st.session_state.autopilot_enabled = False
if 'autopilot_lot' not in st.session_state:
    st.session_state.autopilot_lot = 0.10
if 'autopilot_logs' not in st.session_state:
    st.session_state.autopilot_logs = []
if 'last_auto_run' not in st.session_state:
    st.session_state.last_auto_run = None
if 'next_auto_run_time' not in st.session_state:
    st.session_state.next_auto_run_time = None
if 'autopilot_thread' not in st.session_state:
    st.session_state.autopilot_thread = None
if 'autopilot_interval' not in st.session_state:
    st.session_state.autopilot_interval = 300  # 5 minutes in seconds
if 'autopilot_error_count' not in st.session_state:
    st.session_state.autopilot_error_count = 0
if 'autopilot_success_count' not in st.session_state:
    st.session_state.autopilot_success_count = 0

# ============================================================================
# 🛡️ MEMORY-SAFE CACHED DATA LOADER (Fixes Render OOM Crashes)
# ============================================================================
@st.cache_data(ttl=1800, show_spinner=False)
def cached_load_from_hf(repo_id: str, symbol: str, hf_token: str):
    """
    Cached wrapper for load_from_hf.
    - Shared across ALL user sessions on the Render server.
    - Data is downloaded ONCE and reused for 30 minutes (ttl=1800).
    - Prevents the same parquet file being loaded into RAM multiple times,
      which was causing the Render OOM (Out of Memory) crashes.
    """
    from data_sync import load_from_hf
    return load_from_hf(repo_id, symbol, hf_token)

# --- HIGH-SPEED CACHING ---
@st.cache_data(ttl=3600)
def get_cached_symbol_info(m_url, m_tok, symbol):
    """Cache static symbol specs to avoid redundant API calls."""
    try:
        headers = {"X-MT5-Token": m_tok}
        resp = get_session().get(f"{m_url.rstrip('/')}/symbol/info/{symbol}", headers=headers, timeout=5)
        resp.raise_for_status()
        return resp.json()
    except: return None

@st.cache_data(ttl=600)
def get_cached_account_info(m_url, m_tok):
    """Cache account settings like leverage and currency."""
    try:
        headers = {"X-MT5-Token": m_tok}
        resp = get_session().get(f"{m_url.rstrip('/')}/account/info", headers=headers, timeout=5)
        resp.raise_for_status()
        return resp.json()
    except: return None

def place_mt5_order(mt5_url, mt5_token, symbol, action, volume, sl=None, tp=None, price=None, magic=123456, comment="[IMPULSE_V2]"):
    headers = {"X-MT5-Token": mt5_token}
    payload = {
        "symbol": symbol, "action": action.upper(), "volume": volume,
        "sl": sl, "tp": tp, "price": price, "magic": magic, "comment": comment
    }
    resp = get_session().post(f"{mt5_url.rstrip('/')}/order/place", json=payload, headers=headers, timeout=10)
    resp.raise_for_status()
    return resp.json()

def close_mt5_position(mt5_url, mt5_token, ticket, volume=None, comment="[IMPULSE_V2]"):
    headers = {"X-MT5-Token": mt5_token}
    payload = {"ticket": ticket, "volume": volume, "comment": comment}
    resp = get_session().post(f"{mt5_url.rstrip('/')}/order/close", json=payload, headers=headers, timeout=10)
    resp.raise_for_status()
    return resp.json()

def modify_mt5_position(mt5_url, mt5_token, ticket, sl=None, tp=None):
    headers = {"X-MT5-Token": mt5_token}
    payload = {"ticket": ticket, "sl": sl, "tp": tp}
    resp = get_session().post(f"{mt5_url.rstrip('/')}/order/modify", json=payload, headers=headers, timeout=10)
    resp.raise_for_status()
    return resp.json()

def fetch_open_positions(mt5_url, mt5_token):
    headers = {"X-MT5-Token": mt5_token}
    resp = get_session().get(f"{mt5_url.rstrip('/')}/positions/summary", headers=headers, timeout=5)
    resp.raise_for_status()
    return resp.json()

def fetch_trade_history(mt5_url, mt5_token, hours=24):
    headers = {"X-MT5-Token": mt5_token}
    resp = get_session().get(f"{mt5_url.rstrip('/')}/trades/history", params={"hours": hours}, headers=headers, timeout=5)
    resp.raise_for_status()
    return resp.json()

def calculate_lot_size_risk(account_balance, risk_percent, entry_price, sl_price, tick_value, point):
    """Calculate lot size based on risk % and SL distance."""
    if entry_price is None or sl_price is None or tick_value is None or point is None or point == 0:
        return None
    risk_amount = account_balance * (risk_percent / 100.0)
    sl_distance_points = abs(entry_price - sl_price) / point
    if sl_distance_points == 0:
        return None
    lot = risk_amount / (sl_distance_points * tick_value)
    return round(max(lot, 0.01), 2)

# ============================================================================
# 📊 GOOGLE SHEETS MASTER AUDIT LOG SYSTEM
# ============================================================================
def master_audit_log(action_type, details):
    """Unified logger to record actions to Google Sheets via Apps Script Webhook."""
    try:
        # Use provided Apps Script URL
        url = "https://script.google.com/macros/s/AKfycbxtd5reNGnPATB7oCWRtwYYO_BKMb55HwdemU5nw5MwkguSIlL8uV1maT8BkcK0TElz6A/exec"
        
        # Priority: Check if URL is in secrets (for production), otherwise use hardcoded
        webhook_url = get_secret("GSHEETS_LOG_URL", url)

        # Capture source info
        try:
            source_info = str(st.context.headers.get("User-Agent", "Unknown Device"))
        except:
            source_info = "Unknown"

        data = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "username": st.session_state.get("username", "System"),
            "name": st.session_state.get("user_name", "N/A"),
            "action": action_type,
            "details": details,
            "source": source_info
        }

        # Send to Google Sheets (Async-like feel with short timeout)
        requests.post(webhook_url, json=data, timeout=5)
    except Exception:
        pass

def _repair_json(text):
    """Fix common AI JSON mistakes: missing commas, trailing commas, unquoted values."""
    # Fix missing commas between key-value pairs: "key":value\n"key2"
    text = re.sub(r'("[\w_]+")\s*:\s*("[^"]*"|-?\d+\.?\d*|true|false|null)\s*\n\s*(")', r'\1: \2,\n  \3', text)
    # Fix trailing commas before closing brace
    text = re.sub(r',\s*}', '}', text)
    text = re.sub(r',\s*]', ']', text)
    return text

def detect_trade_setup(text):
    """Detect and parse a TRADE_SETUP JSON block from AI response."""
    json_pattern = r"```json\s*(.*?)\s*```"
    blocks = re.findall(json_pattern, text, re.S | re.I)
    for block in blocks:
        try:
            data = json.loads(block)
            if isinstance(data, dict) and data.get("action") == "TRADE_SETUP":
                return data
        except json.JSONDecodeError:
            # Attempt repair
            try:
                repaired = _repair_json(block)
                data = json.loads(repaired)
                if isinstance(data, dict) and data.get("action") == "TRADE_SETUP":
                    return data
            except json.JSONDecodeError:
                continue
    try:
        data = json.loads(text)
        if isinstance(data, dict) and data.get("action") == "TRADE_SETUP":
            return data
    except json.JSONDecodeError:
        try:
            repaired = _repair_json(text)
            data = json.loads(repaired)
            if isinstance(data, dict) and data.get("action") == "TRADE_SETUP":
                return data
        except json.JSONDecodeError:
            pass
    return None

def detect_trade_action(text):
    """Detect and parse a TRADE_ACTION JSON block (CLOSE, MODIFY_SL, MODIFY_TP, etc.)."""
    json_pattern = r"```json\s*(.*?)\s*```"
    blocks = re.findall(json_pattern, text, re.S | re.I)
    for block in blocks:
        try:
            data = json.loads(block)
            if isinstance(data, dict) and data.get("action") in ("CLOSE_POSITION", "MODIFY_SL", "MODIFY_TP", "MODIFY_SLTP", "ADD_TO_POSITION"):
                return data
        except json.JSONDecodeError:
            try:
                repaired = _repair_json(block)
                data = json.loads(repaired)
                if isinstance(data, dict) and data.get("action") in ("CLOSE_POSITION", "MODIFY_SL", "MODIFY_TP", "MODIFY_SLTP", "ADD_TO_POSITION"):
                    return data
            except json.JSONDecodeError:
                continue
    return None

def build_trade_context(mt5_url, mt5_token):
    """Build [ACTIVE TRADE CONTEXT] block for AI prompt injection."""
    lines = []
    try:
        summary = fetch_open_positions(mt5_url, mt5_token)
        if summary.get("positions"):
            lines.append("[ACTIVE TRADE CONTEXT]")
            for pos in summary["positions"]:
                lines.append(
                    f"Ticket: {pos['ticket']} | {pos['symbol']} {pos['direction']} | "
                    f"Entry: {pos['entry_price']} | Current: {pos['current_price']} | "
                    f"P&L: ${pos['profit']:.2f} | SL: {pos['sl']} | TP: {pos['tp']}"
                )
            lines.append(f"Account: Balance ${summary['balance']:.2f} | Equity ${summary['equity']:.2f} | Margin Level: {summary['margin_level']:.1f}%")
    except Exception:
        pass

    # REMOVED: Recent closed trades removed per user request
    # try:
    #     history = fetch_trade_history(mt5_url, mt5_token, hours=24)
    #     if history.get("deals"):
    #         lines.append("[RECENT CLOSED TRADES (Last 24h)]")
    #         for deal in history["deals"]:
    #             if deal.get("entry") == "CLOSE":
    #                 lines.append(
    #                     f"Ticket: {deal['ticket']} | {deal['symbol']} {deal['direction']} | "
    #                     f"Exit: {deal['price']} | P&L: ${deal['profit']:.2f} | Comment: {deal.get('comment', '')}"
    #                 )
    # except Exception:
    #     pass

    return "\n".join(lines)

# ============================================================================
# ⚡ HIGH-SPEED CALLBACK SYSTEM (V2.7)
# ============================================================================
def on_execute_market_cb(m_url, m_tok, symbol, action, lot, sl, tp):
    """Callback for instant market execution."""
    st.session_state.executing = True
    try:
        sl_val = sl if sl > 0 else None
        tp_val = tp if tp > 0 else None
        result = place_mt5_order(m_url, m_tok, symbol, action, lot, sl=sl_val, tp=tp_val)
        msg = f"✅ Market {action} #{result.get('ticket')} Successful!"
        st.session_state.last_exec_msg = msg
        st.toast(msg)
        
        # LOG TO AUDIT
        master_audit_log("TRADE_EXECUTION", f"Market {action} {lot} {symbol} SL:{sl} TP:{tp} Ticket:{result.get('ticket')}")
    except Exception as e:
        st.session_state.last_exec_msg = f"❌ Market Order Failed: {e}"
        st.toast(st.session_state.last_exec_msg)
    st.session_state.executing = False

def on_execute_pending_cb(m_url, m_tok, symbol, direction, entry, lot, sl, tp):
    """Callback for smart pending execution."""
    st.session_state.executing = True
    try:
        # Resolve current prices ASAP
        live_tick = get_session().get(f"{m_url.rstrip('/')}/symbol/info/{symbol}", 
                                   headers={"X-MT5-Token": m_tok}).json()
        ask, bid = live_tick.get("ask"), live_tick.get("bid")
        
        if not (entry and ask and bid):
            st.session_state.last_exec_msg = "❌ Pending Error: Price data unavailable."
        else:
            smart_action = ""
            if direction.upper() == "BUY":
                smart_action = "BUY_LIMIT" if entry < ask else "BUY_STOP"
            else:
                smart_action = "SELL_LIMIT" if entry > bid else "SELL_STOP"
            
            sl_val = sl if sl > 0 else None
            tp_val = tp if tp > 0 else None
            result = place_mt5_order(m_url, m_tok, symbol, smart_action, lot, sl=sl_val, tp=tp_val, price=entry)
            st.session_state.last_exec_msg = f"✅ {smart_action} #{result.get('ticket')} Placed!"
            st.toast(st.session_state.last_exec_msg)
    except Exception as e:
        st.session_state.last_exec_msg = f"❌ Pending Order Failed: {e}"
        st.toast(st.session_state.last_exec_msg)
    st.session_state.executing = False

def on_close_position_cb(m_url, m_tok, ticket):
    """Callback for instant position closure."""
    try:
        result = close_mt5_position(m_url, m_tok, ticket)
        st.toast(f"✅ Position #{ticket} Closed!")
    except Exception as e:
        st.toast(f"❌ Close failed: {e}")

def on_modify_position_cb(m_url, m_tok, ticket, sl, tp):
    """Callback for instant SL/TP modification."""
    try:
        # Use simple numeric inputs as floats
        sl_val = float(sl) if sl and float(sl) > 0 else None
        tp_val = float(tp) if tp and float(tp) > 0 else None
        result = modify_mt5_position(m_url, m_tok, ticket, sl=sl_val, tp=tp_val)
        st.toast(f"✅ Position #{ticket} Modified!")
    except Exception as e:
        st.toast(f"❌ Modify failed: {e}")

def render_trade_card(setup, mt5_url, mt5_token, card_id="default"):
    """Render an interactive Trade Execution Card from AI setup JSON with unique keys."""
    symbol = setup.get("symbol", "XAUUSD")
    direction = setup.get("direction", "BUY")
    order_type_raw = setup.get("order_type", "market")
    entry = setup.get("entry_price")
    sl = setup.get("stop_loss")
    tp = setup.get("take_profit")
    lot = setup.get("lot_size", 0.10)
    rr = setup.get("risk_reward", 0)
    reasoning = setup.get("reasoning", "")

    badge = "🟢 BUY" if direction.upper() == "BUY" else "🔴 SELL"
    st.markdown(f"---")
    st.markdown(f"#### {badge} Trade Setup — {symbol}")
    if reasoning:
        st.caption(f"📝 {reasoning}")

    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        use_ai_sltp = st.session_state.get("trade_ai_sltp", True)
        card_entry = st.number_input("Entry", value=float(entry) if entry else 0.0, step=0.01, key=f"card_entry_{symbol}_{card_id}")
    with c2:
        card_sl = st.number_input("SL", value=float(sl) if sl else 0.0, step=0.01, disabled=use_ai_sltp, key=f"card_sl_{symbol}_{card_id}")
    with c3:
        card_tp = st.number_input("TP", value=float(tp) if tp else 0.0, step=0.01, disabled=use_ai_sltp, key=f"card_tp_{symbol}_{card_id}")
    with c4:
        lot_mode = st.session_state.get("trade_lot_mode", False)
        if lot_mode:
            risk_pct = st.session_state.get("trade_risk_pct", 1.0)
            st.number_input("Risk %", value=risk_pct, step=0.1, disabled=True, key=f"card_risk_{symbol}_{card_id}")
            card_lot = lot
        else:
            card_lot = st.number_input("Lot Size", value=float(lot), min_value=0.01, step=0.01, key=f"card_lot_{symbol}_{card_id}")
    with c5:
        st.metric("R:R Ratio", f"{rr:.2f}" if rr else "N/A")

    # --- SMART ACTION SELECTION (CALLBACK-BASED) ---
    col_a, col_b, col_c = st.columns([1, 1, 0.5])
    
    with col_a:
        st.button(f"🚀 Market Execute", type="primary", use_container_width=True, 
                  key=f"mkt_exec_{symbol}_{direction}_{card_id}",
                  on_click=on_execute_market_cb,
                  args=(mt5_url, mt5_token, symbol, direction.upper(), card_lot, card_sl, card_tp))

    with col_b:
        st.button(f"🕒 Smart Pending", type="secondary", use_container_width=True, 
                  key=f"pnd_exec_{symbol}_{direction}_{card_id}",
                  on_click=on_execute_pending_cb,
                  args=(mt5_url, mt5_token, symbol, direction.upper(), card_entry, card_lot, card_sl, card_tp))

    with col_c:
        if st.button("❌", use_container_width=True, key=f"dismiss_{symbol}_{direction}_{card_id}"):
            pass

def render_action_card(action, mt5_url, mt5_token):
    """Render an Action Card for AI-suggested trade management."""
    action_type = action.get("action", "")
    ticket = action.get("ticket")
    reasoning = action.get("reasoning", "")

    if action_type == "CLOSE_POSITION":
        st.markdown(f"---")
        st.markdown(f"#### 🛡️ AI Suggestion: Close Position #{ticket}")
        st.caption(f"📝 {reasoning}")
        st.button(f"✅ Close Position #{ticket}", type="primary", key=f"ai_close_{ticket}",
                  on_click=on_close_position_cb, args=(mt5_url, mt5_token, ticket))
        if st.button("❌ Ignore", key=f"ignore_close_{ticket}"):
            pass

    elif action_type in ("MODIFY_SL", "MODIFY_TP", "MODIFY_SLTP"):
        new_sl = action.get("new_sl") or action.get("sl")
        new_tp = action.get("new_tp") or action.get("tp")
        st.markdown(f"---")
        st.markdown(f"#### 🛡️ AI Suggestion: Modify Position #{ticket}")
        changes = []
        if new_sl: changes.append(f"SL → {new_sl}")
        if new_tp: changes.append(f"TP → {new_tp}")
        st.caption(f"📝 {reasoning} ({', '.join(changes)})")
        st.button(f"✅ Apply Changes", type="primary", key=f"ai_modify_{ticket}",
                  on_click=on_modify_position_cb, args=(mt5_url, mt5_token, ticket, new_sl, new_tp))
        if st.button("❌ Ignore", key=f"ignore_modify_{ticket}"):
            pass

def filter_code_from_message(content):
    """Remove Python code blocks and JSON from AI response for clean display."""
    import re
    if not content:
        return content
    # Remove markdown code blocks (```python ... ``` or ``` ... ```)
    content = re.sub(r'```python[\s\S]*?```', '', content)
    content = re.sub(r'```[\s\S]*?```', '', content)
    # Remove import statements and code lines that start with import or have = in technical way
    lines = content.split('\n')
    filtered_lines = []
    skip_code_lines = False
    for line in lines:
        # Skip lines that look like code (starting with import, df., np., st., etc.)
        if any(line.strip().startswith(kw) for kw in ['import ', 'def ', 'class ', 'if __', 'for ', 'while ']):
            continue
        # Skip lines with multiple dots or brackets that indicate code
        if re.search(r'df\.|np\.|st\.|go\.|pd\.\w+\(', line) and not line.startswith('#'):
            continue
        filtered_lines.append(line)
    return '\n'.join(filtered_lines).strip()

def process_ai_query(prompt, df, model_choice, api_key, model_provider, history_key="messages", base_url=None, snapshot=None):
    """Handles professional quantitative analysis queries using multi-modal AI reasoning."""
    if "messages_live" not in st.session_state: st.session_state.messages_live = []
    if "messages" not in st.session_state: st.session_state.messages = []
    
    # Load persistent memory on first query
    if "memory_loaded" not in st.session_state:
        st.session_state.memory = load_all_memory()
        st.session_state.memory_loaded = True
    
    history = st.session_state[history_key]
    history.append({"role": "user", "content": prompt})
    
    master_audit_log("AI_QUERY", f"Prompt: {prompt}")
    
    with st.chat_message("user"): st.markdown(prompt)
    
    with st.chat_message("assistant"):
        with st.spinner("🧠 AI is analyzing your data..."):
            df_info = io.StringIO()
            df.info(buf=df_info)
            metadata = df_info.getvalue()
            
            # Build memory context
            memory_context = build_memory_context(st.session_state.memory)
            
            # Build news context if user asks about today's news
            news_context = build_news_context(prompt)
            
            system_prompt = f"""
            You are a Lead Quant in 2026. Use the provided DataFrame 'df' for your analysis.
            
            {memory_context}
            {news_context}
            
            SCHEMA: {metadata}
            LATEST_CANDLE_RECORDED: {df['time'].iloc[-1] if not df.empty and 'time' in df.columns else 'N/A'}
            SAMPLES (Last 5 Rows): {df.tail(5).to_string()}
            
            RULES (STRICT):
            1. Analyze only based on the provided data available in 'df'. Ignore local system time.
            2. Provide the analysis directly without code.
            3. If you identify a trade opportunity, output the explanation and a JSON block in ```json format:
               ```json
               {{"action": "TRADE_SETUP", "symbol": "XAUUSD", "direction": "BUY", "order_type": "market", "entry_price": 2345.50, "stop_loss": 2338.00, "take_profit": 2360.00, "lot_size": 0.10, "risk_reward": 1.93, "reasoning": "Brief explanation"}}
               ```
               IMPORTANT: JSON must be valid — every key-value pair must have a comma after it except the last one.
             5. If analyzing an open position, suggest management via JSON:
               ```json
               {{"action": "MODIFY_SLTP", "ticket": 123456, "new_sl": 2345.50, "new_tp": 2370.00, "reasoning": "Trail SL to lock profit"}}
               ```
               Actions: CLOSE_POSITION, MODIFY_SL, MODIFY_TP, MODIFY_SLTP, ADD_TO_POSITION
            """
            
            final_key = api_key
            if model_provider == "NVIDIA" and not final_key.startswith("nvapi-"):
                final_key = f"nvapi-{final_key}"
            
            client = OpenAI(base_url=base_url, api_key=final_key)
            full_txt = ""
            
            clean_history = []
            for m in history:
                clean_history.append({"role": m["role"], "content": m["content"]})

            messages = [{"role": "system", "content": system_prompt}] + clean_history
            
            try:
                stream = client.chat.completions.create(
                    model=model_choice, messages=messages, temperature=0.2, stream=True
                )
                for chunk in stream:
                    if chunk.choices[0].delta.content:
                        full_txt += chunk.choices[0].delta.content
                
                code_pattern = r"```python(.*?)```"
                blocks = re.findall(code_pattern, full_txt, re.S | re.I)
                final_code = "\n\n".join([b.strip() for b in blocks]) if blocks else None
                final_stdout = ""
                
                if final_code:
                    final_stdout, error = execute_generated_code(final_code, df)
                    if error:
                        st.error(f"Execution Error: {error}")
                
                if final_stdout:
                    st.markdown("**📊 Analysis Complete:**")
                else:
                    st.markdown(full_txt)
                
                msg_to_store = {"role": "assistant", "content": full_txt}
                if final_code: msg_to_store["code"] = final_code
                if final_stdout: msg_to_store["exec_result"] = final_stdout
                
                setup = detect_trade_setup(full_txt)
                if setup:
                    msg_to_store["detected_setup"] = setup
                
                action = detect_trade_action(full_txt)
                if action:
                    msg_to_store["detected_action"] = action
                
                if snapshot is not None:
                    if "data_vault" not in st.session_state: st.session_state.data_vault = {}
                    import time
                    snap_id = f"snap_{int(time.time())}"
                    st.session_state.data_vault[snap_id] = snapshot
                    msg_to_store["snapshot_id"] = snap_id
                    if len(st.session_state.data_vault) > 5:
                        oldest_key = next(iter(st.session_state.data_vault))
                        del st.session_state.data_vault[oldest_key]
                
                history.append(msg_to_store)
                if len(history) > 20:
                    history.pop(0)
                
                # Save conversation to persistent memory
                import time as time_module
                conv_id = f"conv_{int(time_module.time())}"
                detected_setup = msg_to_store.get("detected_setup")
                detected_action = msg_to_store.get("detected_action")
                
                save_conversation_summary(conv_id, prompt, full_txt, detected_setup, detected_action)
                
                # Update memory stats
                if detected_setup:
                    st.session_state.memory = load_all_memory()
                
                # Feedback UI
                st.markdown("---")
                col_fb1, col_fb2 = st.columns([1, 2])
                with col_fb1:
                    st.caption("Was this response helpful?")
                with col_fb2:
                    fb_key = f"fb_{len(history)}"
                    c1, c2, c3 = st.columns([1, 1, 2])
                    with c1:
                        if st.button("👍 Helpful", key=f"thumb_up_{fb_key}"):
                            save_feedback(1, "", full_txt[:500], st.session_state.get("user_name", "user"))
                            st.toast("Thanks for your feedback!")
                            st.rerun()
                    with c2:
                        if st.button("👎 Not Helpful", key=f"thumb_down_{fb_key}"):
                            save_feedback(0, "", full_txt[:500], st.session_state.get("user_name", "user"))
                            st.toast("Thanks! We'll improve.")
                            st.rerun()
                    with c3:
                        rating = st.selectbox("Rate", ["⭐", "⭐⭐", "⭐⭐⭐", "⭐⭐⭐⭐", "⭐⭐⭐⭐⭐"], key=f"star_{fb_key}", label_visibility="collapsed")
                        if st.button("Submit Rating", key=f"rate_{fb_key}"):
                            stars = len(rating)
                            save_feedback(stars, "", full_txt[:500], st.session_state.get("user_name", "user"))
                            st.toast(f"Rated {stars} stars!")
                            st.rerun()

            except Exception as e:
                st.error(f"API Error: {e}")

def handle_autopilot_execution(mt5_url, mt5_token, hf_repo, hf_token, model_choice, api_key, model_provider, base_url, is_background=False):
    """Orchestrates one cycle of the random prompt autopilot with DETAILED logging."""
    import random
    import time
    import traceback

    timestamp = time.strftime('%H:%M:%S')

    try:
        # 1. Load Prompts
        try:
            with open("test_prompt.txt", "r", encoding="utf-8") as f:
                prompts = [line.strip() for line in f.readlines() if line.strip() and "." in line]
        except Exception as e:
            error_msg = f"🔴 [{timestamp}] File Error: {e}"
            st.session_state.autopilot_logs.insert(0, error_msg)
            st.session_state.autopilot_error_count += 1
            return

        if not prompts:
            error_msg = f"🔴 [{timestamp}] No prompts found in test_prompt.txt"
            st.session_state.autopilot_logs.insert(0, error_msg)
            st.session_state.autopilot_error_count += 1
            return

        selected_line = random.choice(prompts)
        prompt_num = selected_line.split(".")[0].strip()
        prompt_text = selected_line.split(".", 1)[1].strip()

        # 2. Get Data Snapshot (FORCE FRESH DATA)
        current_sym = st.session_state.get("current_symbol_view", "XAUUSD")

        # We pull the absolute latest 1000 candles directly from MT5 memory
        try:
            from data_sync import pull_mt5_latest
            df = pull_mt5_latest(mt5_url, current_sym, "1m", count=1000, mt5_token=mt5_token)
        except Exception as e:
            error_msg = f"🔴 [{timestamp}] P:{prompt_num} Data Fetch Error: {e}"
            st.session_state.autopilot_logs.insert(0, error_msg)
            st.session_state.autopilot_error_count += 1
            return

        if df.empty:
            st.session_state.autopilot_logs.insert(0, f"🔴 [{timestamp}] P:{prompt_num} Failed: Could not fetch fresh market data.")
            st.session_state.autopilot_error_count += 1
            return

        # 3. Request AI Setup (DETAILED LOGGING)
        st.session_state.autopilot_logs.insert(0, f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        st.session_state.autopilot_logs.insert(0, f"📝 [{timestamp}] Prompt #{prompt_num}: {prompt_text}")
        st.session_state.autopilot_logs.insert(0, f"📊 Analyzing {current_sym} | {len(df)} candles | TF: 1m")

        df_info = io.StringIO()
        df.info(buf=df_info)
        metadata = df_info.getvalue()

        system_prompt = f"""
        You are a Lead Quant in 2026. USE JSON ONLY FOR TRADES.
        SCHEMA: {metadata}
        SAMPLES (Last 5 Rows): {df.tail(5).to_string()}
        RULES: 1. Output a JSON TRADE_SETUP block.
        2. Suggest an ENTRY_PRICE based on your analysis of 'df'.
        """

        # --- 🛡️ ENGINE SAFETY: Resolve API Key ---
        final_key = api_key
        if model_provider == "NVIDIA" and not str(final_key).startswith("nvapi-"):
            final_key = f"nvapi-{final_key}"

        client = OpenAI(base_url=base_url, api_key=final_key)

        try:
            # Non-streaming for automation
            ai_start_time = time.time()
            resp = client.chat.completions.create(
                model=model_choice,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Analyze current data and {prompt_text}"}
                ],
                temperature=0.2,
                timeout=30  # Add timeout
            )
            ai_response_time = time.time() - ai_start_time
            ai_txt = resp.choices[0].message.content
            
            # Log AI response summary (first 200 chars)
            ai_summary = ai_txt[:200].replace('\n', ' ')
            st.session_state.autopilot_logs.insert(0, f"🤖 AI Response ({ai_response_time:.1f}s): {ai_summary}...")
            
            setup = detect_trade_setup(ai_txt)

            if not setup:
                st.session_state.autopilot_logs.insert(0, f"🟡 [{timestamp}] P:{prompt_num} Result: No trade setup identified by AI")
                st.session_state.autopilot_logs.insert(0, f"💡 Market conditions didn't match prompt criteria")
                return

            # 4. Trade Setup Found - Log Details
            symbol = setup.get("symbol", current_sym)
            direction = setup.get("direction", "BUY").upper()
            entry = setup.get("entry_price", 0)
            sl = setup.get("stop_loss", 0)
            tp = setup.get("take_profit", 0)
            reasoning = setup.get("reasoning", "No reasoning provided")

            st.session_state.autopilot_logs.insert(0, f"🎯 [{timestamp}] P:{prompt_num} TRADE SETUP IDENTIFIED!")
            st.session_state.autopilot_logs.insert(0, f"   Direction: {'🟢 BUY' if direction == 'BUY' else '🔴 SELL'}")
            st.session_state.autopilot_logs.insert(0, f"   Symbol: {symbol}")
            st.session_state.autopilot_logs.insert(0, f"   Entry: {entry} | SL: {sl} | TP: {tp}")
            st.session_state.autopilot_logs.insert(0, f"   Reasoning: {reasoning}")

            # --- 🛡️ ENGINE SAFETY: Numeric Validation ---
            try:
                entry = float(setup.get("entry_price", 0))
                sl = float(setup.get("stop_loss", 0)) if setup.get("stop_loss") else None
                tp = float(setup.get("take_profit", 0)) if setup.get("take_profit") else None
            except (ValueError, TypeError):
                 st.session_state.autopilot_logs.insert(0, f"🔴 [{timestamp}] P:{prompt_num} Error: AI provided invalid price numbers.")
                 st.session_state.autopilot_error_count += 1
                 return

            lot = st.session_state.autopilot_lot

            # Get Live Tick for classification
            try:
                headers = {"X-MT5-Token": mt5_token}
                tick_resp = requests.get(f"{mt5_url.rstrip('/')}/symbol/info/{symbol}", headers=headers, timeout=5)
                tick_resp.raise_for_status()
                tick = tick_resp.json()
                ask, bid = tick.get("ask"), tick.get("bid")
            except Exception as e:
                st.session_state.autopilot_logs.insert(0, f"🔴 [{timestamp}] P:{prompt_num} Tick Data Error: {e}")
                st.session_state.autopilot_error_count += 1
                return

            if not (entry and ask and bid):
                st.session_state.autopilot_logs.insert(0, f"🔴 [{timestamp}] P:{prompt_num} Sync Error: Prices missing.")
                st.session_state.autopilot_error_count += 1
                return

            # Classification
            smart_action = ""
            if direction == "BUY":
                smart_action = "BUY_LIMIT" if entry < ask else "BUY_STOP"
            else:
                smart_action = "SELL_LIMIT" if entry > bid else "SELL_STOP"

            st.session_state.autopilot_logs.insert(0, f"📋 Order Type: {smart_action} (Entry {('below' if 'LIMIT' in smart_action else 'above')} current market)")

            # Place Order
            try:
                comment = f"[AUTO][P:{prompt_num}]"
                order_start_time = time.time()
                res = place_mt5_order(mt5_url, mt5_token, symbol, smart_action, lot,
                                      sl=sl, tp=tp, price=entry, comment=comment)
                order_time = time.time() - order_start_time

                ticket = res.get('ticket', 'N/A')
                st.session_state.autopilot_logs.insert(0, f"✅✅✅ [{timestamp}] TRADE EXECUTED SUCCESSFULLY! ✅✅✅")
                st.session_state.autopilot_logs.insert(0, f"   Ticket: #{ticket}")
                st.session_state.autopilot_logs.insert(0, f"   Type: {smart_action}")
                st.session_state.autopilot_logs.insert(0, f"   Entry: {entry} | SL: {sl} | TP: {tp}")
                st.session_state.autopilot_logs.insert(0, f"   Lot: {lot} | Symbol: {symbol}")
                st.session_state.autopilot_logs.insert(0, f"   Execution Time: {order_time:.2f}s")
                st.session_state.autopilot_success_count += 1
                st.session_state.autopilot_logs.insert(0, f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
            except Exception as e:
                st.session_state.autopilot_logs.insert(0, f"🔴 [{timestamp}] P:{prompt_num} Trade Execution Error: {e}")
                st.session_state.autopilot_logs.insert(0, f"📝 Order was NOT placed - check MT5 connection")
                st.session_state.autopilot_error_count += 1
                st.session_state.autopilot_logs.insert(0, f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

        except Exception as e:
            st.session_state.autopilot_logs.insert(0, f"🔴 [{timestamp}] P:{prompt_num} AI API Error: {e}")
            st.session_state.autopilot_logs.insert(0, f"📝 AI response was NOT received")
            st.session_state.autopilot_error_count += 1
            st.session_state.autopilot_logs.insert(0, f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
            
    except Exception as e:
        timestamp = time.strftime('%H:%M:%S')
        st.session_state.autopilot_logs.insert(0, f"🔴 [{timestamp}] Critical Autopilot Error: {e}")
        st.session_state.autopilot_logs.insert(0, f"📝 Traceback: {traceback.format_exc()}")
        st.session_state.autopilot_error_count += 1
        st.session_state.autopilot_logs.insert(0, f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")


# Lazy/Optional Heavy Imports
try:
    import pygwalker as pyg
    PYG_AVAILABLE = True
except (ImportError, MemoryError):
    PYG_AVAILABLE = False

try:
    from st_aggrid import AgGrid
    AGGRID_AVAILABLE = True
except (ImportError, MemoryError):
    AGGRID_AVAILABLE = False

# ============================================================================
# 🧵 BACKGROUND THREAD AUTOPILOT SYSTEM
# ============================================================================
import threading
import time as time_module

def _autopilot_thread_loop(mt5_url, mt5_token, hf_repo, hf_token, model_choice, api_key, model_provider, base_url):
    """Background thread that runs the autopilot independently of browser refresh."""
    while st.session_state.get('autopilot_enabled', False):
        try:
            # Calculate next run time
            next_run = time_module.time() + st.session_state.get('autopilot_interval', 300)
            st.session_state.next_auto_run_time = next_run
            
            # Sleep until next execution
            while st.session_state.get('autopilot_enabled', False) and time_module.time() < next_run:
                time_module.sleep(1)
            
            # Check if still enabled after sleep
            if not st.session_state.get('autopilot_enabled', False):
                break
            
            # Execute autopilot cycle
            handle_autopilot_execution(
                mt5_url, mt5_token, hf_repo, hf_token,
                model_choice, api_key, model_provider, base_url,
                is_background=True
            )
            
            # Update last run time
            st.session_state.last_auto_run = time_module.localtime()
            
        except Exception as e:
            timestamp = time_module.strftime('%H:%M:%S')
            st.session_state.autopilot_logs.insert(0, f"🔴 [{timestamp}] Thread Error: {e}")
            time_module.sleep(5)  # Brief pause on error
    
    st.session_state.autopilot_thread = None

def start_autopilot_thread(mt5_url, mt5_token, hf_repo, hf_token, model_choice, api_key, model_provider, base_url):
    """Start the background autopilot thread."""
    if st.session_state.get('autopilot_thread') is not None:
        st.session_state.autopilot_logs.insert(0, f"🟡 [{time_module.strftime('%H:%M:%S')}] Autopilot already running")
        return
    
    st.session_state.autopilot_enabled = True
    st.session_state.next_auto_run_time = time_module.time() + st.session_state.get('autopilot_interval', 300)
    
    thread = threading.Thread(
        target=_autopilot_thread_loop,
        args=(mt5_url, mt5_token, hf_repo, hf_token, model_choice, api_key, model_provider, base_url),
        daemon=True
    )
    thread.start()
    st.session_state.autopilot_thread = thread
    
    st.session_state.autopilot_logs.insert(0, f"🟢 [{time_module.strftime('%H:%M:%S')}] 🚀 Autopilot background thread started")

def stop_autopilot_thread():
    """Stop the background autopilot thread."""
    st.session_state.autopilot_enabled = False
    st.session_state.next_auto_run_time = None
    
    if st.session_state.get('autopilot_thread') is not None:
        st.session_state.autopilot_logs.insert(0, f"🔴 [{time_module.strftime('%H:%M:%S')}] ⏹️ Autopilot background thread stopped")
        st.session_state.autopilot_thread = None

# Symbol Mapping (MT5 -> Yahoo Finance)
YAHOO_MAPPING = {
    "XAUUSD": "GC=F",      # Gold Futures
    "EURUSD": "EURUSD=X",  # Euro/USD FX
    "DXY": "DX-Y.NYB",    # US Dollar Index
    "^NSEI": "^NSEI",     # Nifty 50 (Identity)
    "^NSEBANK": "^NSEBANK" # Bank Nifty (Identity)
}

# Page configuration
# ── PRO APP BRANDING ──
st.set_page_config(
    page_title="The Finance Engine",
    page_icon="📈",
    layout="wide",
)

# --- 🚀 CLOUD DETECTION ---
import os
IS_CLOUD = os.environ.get("STREAMLIT_SERVER_PORT") is not None or "HOSTNAME" in os.environ

# --- 🚀 CLOUD DETECTION ---
import os
IS_CLOUD = os.environ.get("STREAMLIT_SERVER_PORT") is not None or "HOSTNAME" in os.environ

# App theme and styling - Finance Engine Theme
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Syne:wght@600;700;800&family=DM+Sans:opsz,wght@9..40,300;9..40,400;9..40,500&display=swap');

:root {
    --bg:       #0d1117;
    --card:     #161b22;
    --border:   #30363d;
    --gold:     #f0b429;
    --text:     #f0f6fc;
    --muted:    #8b949e;
    --muted2:   #6e7681;
    --ibg:      #0d1117;
}

/* ── FORCE ALL EXPANDERS TO DARK ── */
[data-testid="stExpander"],
streamlit-expander,
div[aria-label="🔒 MT5 Broker Gate (Local Connection Settings)"],
div:has(> div > div > div > div:contains("MT5 Broker Gate")) {
    background: #161b22 !important;
}

div[data-testid="stExpander"] > div {
    background: #161b22 !important;
}

div[data-testid="stExpanderContent"] {
    background: #161b22 !important;
    color: #f0f6fc !important;
}

/* ── Full page reset ── */
html, body, .stApp { 
    background: var(--bg) !important; 
    font-family: 'DM Sans', sans-serif;
    color: var(--text) !important;
}

/* Main content background */
div[data-testid="stMain"] {
    background: var(--bg) !important;
}

/* Block container */
div[data-testid="stMain"] > .block-container {
    background: var(--bg) !important;
}

/* Hide default Streamlit elements */
header[data-testid="stHeader"],
.stToolbar, footer, #MainMenu, 
[data-testid="stDecoration"],
[data-testid="stStatusWidget"] { display: none !important; }

/* ── Text colors - enforce everywhere ── */
p, span, label, div, li, td, th {
    color: var(--text) !important;
}

/* Secondary text */
.muted, .stCaption, [data-testid="stCaption"] {
    color: var(--muted) !important;
}

/* ── Block container styles ── */
.block-container {
    padding-top: 24px !important;
    padding-bottom: 24px !important;
    background: transparent !important;
}

/* ── Headers ── */
h1, h2, h3, h4, h5, h6 {
    font-family: 'Syne', sans-serif !important;
    color: var(--text) !important;
    font-weight: 700 !important;
}

/* Streamlit markdown headers */
.stMarkdown h1, .stMarkdown h2, .stMarkdown h3 {
    color: var(--text) !important;
}

/* ── Buttons ── */
div[data-testid="stButton"] > button {
    width: 100%;
    background: linear-gradient(135deg,#f0b429 0%,#d99a0f 100%) !important;
    border: none !important;
    border-radius: 8px !important;
    padding: 12px 20px !important;
    font-family: 'Syne', sans-serif !important;
    font-size: 14px !important;
    font-weight: 600 !important;
    color: #0d1117 !important;
}

div[data-testid="stButton"] > button:hover {
    background: linear-gradient(135deg,#f0b429 0%,#f5c029 100%) !important;
}

/* ── Text inputs ── */
div[data-testid="stTextInput"] input,
input[class*="stTextInput"],
.stTextInput input {
    background: #0d1117 !important;
    border: 1px solid #30363d !important;
    border-radius: 8px !important;
    padding: 12px 14px !important;
    font-family: 'DM Sans', sans-serif !important;
    font-size: 14px !important;
    color: #f0f6fc !important;
}

div[data-testid="stTextInput"] input::placeholder,
input[class*="stTextInput"]::placeholder {
    color: #6e7681 !important;
}

/* ── Select boxes ── */
div[data-testid="stSelectbox"] > div > div,
div[class*="stSelectbox"] > div > div,
.stSelectbox div[class*="Select"] {
    background: #0d1117 !important;
    border: 1px solid #30363d !important;
    border-radius: 8px !important;
    color: #f0f6fc !important;
}

div[data-testid="stSelectbox"] div[class*="Select"],
.stSelectbox div[class*="Select"] {
    color: #f0f6fc !important;
}

/* ── Number inputs ── */
div[data-testid="stNumberInput"] input,
input[class*="stNumberInput"],
.stNumberInput input {
    background: #0d1117 !important;
    border: 1px solid #30363d !important;
    color: #f0f6fc !important;
}

/* ── Input container (the wrapper around input) ── */
div[data-testid="stTextInput"] > div > div,
div[data-testid="stNumberInput"] > div,
div[data-testid="stSelectbox"] > div,
div[class*="TextInput"] > div,
div[class*="NumberInput"] > div,
div[class*="Selectbox"] > div {
    background: #0d1117 !important;
}

/* ── Toggle/Checkbox ── */
div[data-testid="stToggle"] label {
    color: var(--text) !important;
}

/* ── All container text enforcement ── */
.stApp *,
div[class*="stMarkdown"] p,
div[class*="stText"],
div[class*="stLabel"] {
    color: var(--text) !important;
}

/* ── Sidebar styling ── */
section[data-testid="stSidebar"] {
    background: var(--card) !important;
    border-right: 1px solid var(--border) !important;
}

section[data-testid="stSidebar"] * {
    color: var(--text) !important;
}

section[data-testid="stSidebar"] .stMarkdown,
section[data-testid="stSidebar"] p,
section[data-testid="stSidebar"] label {
    color: var(--text) !important;
}

/* ── Metrics ── */
[data-testid="stMetric"] {
    background: var(--card) !important;
    border: 1px solid var(--border) !important;
    border-radius: 8px !important;
    padding: 16px !important;
}

[data-testid="stMetric"] * {
    color: var(--text) !important;
}

/* ── Chat messages ── */
.stChatMessage {
    background: var(--card) !important;
    border-radius: 8px !important;
}

.stChatMessage * {
    color: var(--text) !important;
}

/* ── Expanders ── */
streamlit-expander {
    background: var(--card) !important;
    border: 1px solid var(--border) !important;
    border-radius: 8px !important;
}

streamlit-expander > div {
    background: var(--card) !important;
}

div[data-testid="stExpanderContent"] {
    background: var(--card) !important;
    border-top: 1px solid var(--border) !important;
}

/* Fix for expander content - more aggressive */
div[aria-expanded="true"] + div,
div[data-testid="stExpanderContent"] > div,
div[data-testid="stExpanderContent"] > section {
    background: var(--card) !important;
}

/* Expander inner container */
section[data-testid="stExpander"] > div:first-child,
section[data-testid="stExpander"] > div:last-child {
    background: var(--card) !important;
}

/* ALL elements inside expander get dark background */
div[data-testid="stExpanderContent"] * {
    background: #161b22 !important;
    color: #f0f6fc !important;
}

/* Columns inside expander */
div[data-testid="stExpanderContent"] > div > div[class*="stColumn"],
div[data-testid="stExpanderContent"] div[data-testid="stHorizontalBlock"] {
    background: var(--card) !important;
}

/* ── Data frames / tables ── */
[data-testid="stDataFrame"],
[data-testid="stAgGrid"] {
    border: 1px solid var(--border) !important;
}

[data-testid="stDataFrame"] *,
[data-testid="stAgGrid"] * {
    color: var(--text) !important;
}

/* ── Tabs ── */
div[data-testid="stTabs"] button {
    font-family: 'Syne', sans-serif !important;
    font-weight: 600 !important;
    color: var(--text) !important;
}

div[data-testid="stTabs"] button[aria-selected="true"] {
    color: var(--gold) !important;
}

/* ── Radio buttons ── */
div[data-testid="stRadio"] label {
    color: var(--text) !important;
}

/* ── Checkboxes ── */
div[data-testid="stCheckbox"] label {
    color: var(--text) !important;
}

/* ── Sliders ── */
div[data-testid="stSlider"] label {
    color: var(--text) !important;
}

/* ── Form containers ── */
div[data-testid="stForm"] {
    background: transparent !important;
    border: none !important;
}

/* ── Tooltips ── */
div[data-testid="stTooltipIcon"] {
    color: var(--muted) !important;
}

/* ── Error/Warning/Success messages ── */
.stAlert {
    background: var(--card) !important;
    border-radius: 8px !important;
    color: var(--text) !important;
}

/* ── Scrollbars ── */
::-webkit-scrollbar {
    width: 8px;
    height: 8px;
}
::-webkit-scrollbar-track {
    background: var(--bg);
}
::-webkit-scrollbar-thumb {
    background: var(--border);
    border-radius: 4px;
}
</style>
""", unsafe_allow_html=True)

# Authentication is now handled by login_page module
check_auth()

# ── Main App Header Banner ──
st.markdown("""
<style>
.tfe-logo-row {
    display: flex; align-items: center; gap: 10px;
    margin-bottom: 20px; padding-bottom: 20px;
    border-bottom: 1px solid rgba(255,255,255,0.07);
}
.tfe-logo-icon {
    width: 40px; height: 40px; border-radius: 10px; flex-shrink: 0;
    background: linear-gradient(135deg,rgba(245,171,53,0.14),rgba(245,171,53,0.03));
    border: 1px solid rgba(245,171,53,0.2);
    display: flex; align-items: center; justify-content: center; font-size: 19px;
}
.tfe-logo-name {
    font-family: 'Syne',sans-serif; font-size: 20px; font-weight: 700;
    color: #edf0f6; letter-spacing: -0.2px;
}
.tfe-logo-name span { color: #f0b429; }
</style>

<div class="tfe-logo-row">
    <div class="tfe-logo-icon">📈</div>
    <div class="tfe-logo-name">The Finance <span>Engine</span></div>
</div>
""", unsafe_allow_html=True)

# Sidebar configuration
with st.sidebar:
    st.header("⚙️ Configuration")
    provider_choice = st.selectbox("Select AI Provider", [
        "NVIDIA", "Groq", "OpenRouter", "OpenRouter (Free)", "Gemini", "GitHub Models", "Cerebras", "Bytez"
    ])
    
    # Leave value empty to prevent dots being shown in the DOM (security measure)
    input_api_key = st.text_input(f"{provider_choice} API Key", value="", type="password", help=f"Enter your {provider_choice} API Key.")
    
    # Resolve the key: User input takes priority, secret is used as a silent fallback
    secret_key_name = f"{provider_choice.upper().replace(' ', '_').replace('(', '').replace(')', '')}_API_KEY"
    if provider_choice == "OpenRouter" or provider_choice == "OpenRouter (Free)":
        secret_key_name = "OPEN_ROUTER_API_KEY"
    elif provider_choice == "GitHub Models":
        secret_key_name = "GITHUB_API_KEY"
    
    api_key_to_use = input_api_key if input_api_key else get_secret(secret_key_name, "")
    
    if provider_choice == "NVIDIA":
        model_choice = st.selectbox("Select Model", [
            "qwen/qwen3.5-122b-a10b",
            "qwen/qwen2.5-coder-32b-instruct",
            "deepseek-ai/deepseek-v3.1",
            "deepseek-ai/deepseek-r1-distill-qwen-32b",
            "nvidia/llama-3.1-405b-instruct"
        ])
        base_url = "https://integrate.api.nvidia.com/v1"
    elif provider_choice == "Groq":
        model_choice = st.selectbox("Select Model", [
            "llama3-70b-8192",
            "llama3-8b-8192",
            "mixtral-8x7b-32768",
            "gemma2-9b-it",
            "deepseek-r1-distill-llama-70b"
        ])
        base_url = "https://api.groq.com/openai/v1"
    elif provider_choice == "OpenRouter":
        model_choice = st.selectbox("Select Model", [
            "anthropic/claude-3.5-sonnet",
            "anthropic/claude-3-5-haiku",
            "openrouter/hunter-alpha",
            "meta-llama/llama-3.1-70b-instruct",
            "google/gemini-pro-1.5",
            "mistralai/mixtral-8x22b-instruct"
        ])
        base_url = "https://openrouter.ai/api/v1"
    elif provider_choice == "OpenRouter (Free)":
        model_choice = st.selectbox("Select Free Model", [
            "deepseek/deepseek-r1:free",
            "openrouter/hunter-alpha",
            "google/gemini-pro-1.5:free",
            "meta-llama/llama-3.1-8b-instruct:free",
            "mistralai/mistral-nemo:free"
        ])
        base_url = "https://openrouter.ai/api/v1"
    elif provider_choice == "GitHub Models":
        model_choice = st.selectbox("Select Free Model", [
            "gpt-4o",
            "gpt-4o-mini",
            "meta-llama-3.1-70b-instruct",
            "AI21-Jamba-1.5-Large"
        ])
        base_url = "https://models.inference.ai.azure.com"
    elif provider_choice == "Cerebras":
        model_choice = st.selectbox("Select Free Model", [
            "llama3.1-70b",
            "llama3.1-8b"
        ])
        base_url = "https://api.cerebras.ai/v1"
    elif provider_choice == "Gemini":
        model_choice = st.selectbox("Select Model", [
            "gemini-2.5-flash",
            "gemini-2.5-pro",
            "gemini-1.5-flash",
            "gemini-1.5-pro"
        ])
        base_url = "https://generativelanguage.googleapis.com/v1beta/openai/"
    elif provider_choice == "Bytez":
        model_choice = st.selectbox("Select Model", [
            "meta-llama/Meta-Llama-3-8B-Instruct",
            "mistralai/Mistral-7B-Instruct-v0.2",
            "Qwen/Qwen1.5-72B-Chat"
        ])
        base_url = "https://api.bytez.com/models/v2/openai/"

    enable_thinking = st.checkbox("Enable Thinking Mode", value=True)
    show_debug = st.checkbox("Show AI Trace (Debug)", value=False)
    
    st.markdown("---")
    st.subheader("🕵️ AI Connection Diagnostic")
    if st.button("Run Connection Test"):
        if not api_key_to_use:
            st.error("No API Key found! Please enter one.")
        else:
            try:
                test_key = api_key_to_use
                if provider_choice == "NVIDIA" and not test_key.startswith("nvapi-"):
                    test_key = f"nvapi-{test_key}"
                
                test_client = OpenAI(base_url=base_url, api_key=test_key)
                test_client.models.list()
                st.success("✅ Connection Successful!")
            except Exception as e:
                st.error(f"❌ Connection Failed: {e}")
    
    st.markdown("---")
    st.caption("🔒 **Security Note**: Your Entered API Key is processed in volatile memory only and is never saved to disk or logs.")
    st.markdown("---")
    st.subheader("🛠️ Pro Stack Status")
    if PYG_AVAILABLE: st.success("✅ Visual Explorer Ready")
    else: st.warning("⚠️ Visual Explorer Disabled (Memory)")
    
    if AGGRID_AVAILABLE: st.success("✅ Data Grid Ready")
    else: st.warning("⚠️ Data Grid Disabled (Memory)")
    
    st.markdown("---")
    st.subheader("🧠 Memory & Context")
    if st.button("🗑️ Clear AI Memory Context", width="stretch"):
        st.session_state.messages = []
        st.rerun()

    # ── Cloud Data Management ──
    st.markdown("---")
    st.subheader("🌐 Data Strategy")
    data_source_priority = st.radio(
        "Default Data Source",
        ["☁️ Cloud Hub (Hugging Face)", "💾 Local Disk (.parquet)"],
        index=0,
        help="Choose where the 'Load' button looks first."
    )
    st.session_state.data_source_priority = data_source_priority

    # --- ⚡ AUTO-SYNC & CREDENTIALS ---
    # These MUST be defined before autopilot control center
    hf_repo  = get_secret("HF_REPO_ID", "")
    hf_token = get_secret("HuggingFace_API_KEY", "")
    mt5_url = st.session_state.get("mt5_url", "http://localhost:5000")
    mt5_token = get_secret("MT5_API_TOKEN", "impulse_secure_2026")

    # --- AUTOPILOT & AUTO-SYNC (HIDDEN) ---
    # The autopilot and auto-sync features are hidden for now but code is kept for future use
    """
    """
    # A
    """
    """
    
    # --- 🌍 GLOBAL MARKET VAULT (HIDDEN) ---
    # st.markdown("---")
    # st.subheader("🌍 Global Market Vault")
    # st.caption("Pull stocks/crypto from Yahoo Finance and archive to Cloud Hub.")

    # yf_symbol = st.text_input("Ticker Symbol", placeholder="e.g. NVDA, BTC-USD, TSLA")
    
    # col_per, col_int = st.columns(2)
    # with col_per:
    #     yf_period = st.selectbox("History", ["1mo", "3mo", "1y", "5y", "max"], index=4)
    # with col_int:
    #     yf_interval = st.selectbox("Interval", ["1h", "1d", "1wk"], index=1)

    # if st.button("📥 Fetch & Archive to Cloud", width="stretch"):
    #     if not yf_symbol:
    #         st.warning("Please enter a ticker symbol.")
    #     elif not hf_repo or not hf_token:
    #         st.error("Missing Hugging Face credentials in secrets.toml")
    #     else:
    #         from data_sync import sync_yahoo_symbol
    #         with st.spinner(f"Fetching {yf_symbol} from Global Markets..."):
    #             try:
    #                 df_yf, stats_yf = sync_yahoo_symbol(hf_repo, yf_symbol, hf_token, yf_period, yf_interval)
    #                 st.success(f"✅ {yf_symbol} Vaulted: {stats_yf['total_rows']:,} rows in Cloud")
    #                 st.session_state.df = df_yf
    #                 st.session_state.file_name = stats_yf["filename"]
    #                 st.toast(f"🏆 {yf_symbol} added to your Cloud Warehouse!")
    #                 st.rerun()
    #             except Exception as e:
    #                 st.error(f"❌ Global Fetch Failed: {e}")

    # --- 🌐 GLOBAL WEB INTEL SEARCH ---
    # st.markdown("---")
    # st.subheader("🌐 Global Web Intel")
    # st.caption("AI-powered research for macro news, sentiment, and geopolitics.")

    # search_query = st.text_input("Research Topic", placeholder="e.g. FOMC meeting interest rates, XAUUSD sentiment")
    
    # col_s1, col_s2 = st.columns(2)
    # with col_s1:
    #     max_res = st.slider("Max Results", 3, 10, 5)
    # with col_s2:
    #     search_type = st.radio("Focus", ["Market News", "General Search"], index=0, horizontal=True)

    # if st.button("🔍 Deep Intel Search", width="stretch"):
    #     if not search_query:
    #         st.warning("Please enter a research topic.")
    #     else:
    #         from web_search import run_web_search, get_market_news, analyze_sentiment
    #         with st.spinner(f"🔍 AI is researching the web for '{search_query}'..."):
    #             try:
    #                 if search_type == "Market News":
    #                     res = get_market_news(search_query, max_results=max_res)
    #                 else:
    #                     res = run_web_search(search_query, max_results=max_res)
                    
    #                 if not res:
    #                     st.warning("No results found. Try a different query.")
    #                 else:
    #                     sentiment = analyze_sentiment(res)
    #                     st.info(f"🧠 **AI Sentiment Estimate:** {sentiment}")
                        
    #                     st.markdown("### 📰 Latest Findings:")
    #                     for r in res:
    #                         with st.expander(f"📌 {r['title']}"):
    #                             st.write(f"**Source:** {r['href']}")
    #                             st.write(f"{r['body']}")
    #                             st.markdown(f"[Read full article]({r['href']})")
    #                     st.toast("✅ Web Research Completed!")
    #             except Exception as e:
    #                 st.error(f"❌ Search Error: {e}")

    # Arrow-safe display helper (fixes PyArrow serialization errors)
def make_arrow_safe(df):
    """Convert DataFrame to Arrow-compatible types for Streamlit display."""
    if not isinstance(df, pd.DataFrame):
        return df
    out = df.copy()
    for col in out.columns:
        if out[col].dtype == object:
            # Only convert strict object types to string; leave datetimes alone!
            out[col] = out[col].astype(str)
        elif 'mixed' in str(out[col].dtype).lower() or 'period' in str(out[col].dtype).lower():
            out[col] = out[col].astype(str)
    return out

# Data Processing logic
def process_data(uploaded_file):
    try:
        if uploaded_file.name.endswith('.parquet'):
            # Parquet files are strongly typed and natively supported
            df = pd.read_parquet(uploaded_file)
        else:
            # Load EVERYTHING as string first to prevent 'object' type confusion
            df = pd.read_csv(uploaded_file, dtype=str, low_memory=False)
        
        # Manually convert known numeric columns (support both Segmented and MA Impulse formats)
        numeric_cols = [
            'cross_price', 'segment_index', 'segment_price', 
            'segment_size_price', 'segment_move_points', 
            'segment_move_percent', 'sequence_extreme_price', 'is_final',
            'DifferencePoints', 'DifferencePercent', 'MovingAveragePeriod',
            'CrossoverStartPrice', 'CrossoverEndPrice', 'AbsolutePeakPrice',
            'ImpulsePeakPrice', 'ReversalPrice', 'MA_At_AbsolutePeak',
            'MA_At_ImpulsePeak', 'MA_At_Reversal', 'DeepestRetracePrice',
            'MA_At_DeepestRetrace'
        ]
        
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
        
        # Ensure 'symbol' and 'session' are clean strings
        for col in ['symbol', 'session', 'cross_type', 'segment_direction']:
            if col in df.columns:
                df[col] = df[col].fillna("UNKNOWN").astype(str)
        
        # Convert timestamps (naive datetime64[ns] for Arrow compatibility)
        time_cols = [
            'cross_time', 'cross_end_time', 'segment_time', 'sequence_extreme_time',
            'CrossoverStartTime', 'CrossoverEndTime', 'AbsolutePeakTime',
            'ImpulsePeakTime', 'ReversalTime', 'DeepestRetraceTime'
        ]
        for col in time_cols:
            if col in df.columns:
                dt = pd.to_datetime(df[col], errors='coerce', utc=False)
                df[col] = dt
                if df[col].dtype == object:
                    df[col] = df[col].astype(str)

        # FINAL ARROW COMPATIBILITY CHECK: 
        # Convert any remaining 'object' columns to string
        for col in df.columns:
            if df[col].dtype == object:
                df[col] = df[col].astype(str)
        
        return df.copy()
    except Exception as e:
        st.error(f"☢️ Nuclear Data Clean Error: {e}")
        return None

# ============================================================================
# Streamlit wrapper that auto-sanitizes DataFrames for Arrow compatibility
# ============================================================================
class _SafeStreamlit:
    def __getattr__(self, name):
        return getattr(st, name)
    def write(self, *args, **kwargs):
        sanitized = [make_arrow_safe(a) if isinstance(a, pd.DataFrame) else a for a in args]
        return st.write(*sanitized, **kwargs)
    def dataframe(self, data, **kwargs):
        data = make_arrow_safe(data) if isinstance(data, pd.DataFrame) else data
        return st.dataframe(data, **kwargs)
    def table(self, data, **kwargs):
        data = make_arrow_safe(data) if isinstance(data, pd.DataFrame) else data
        return st.table(data, **kwargs)

# Code Execution Engine
def execute_generated_code(code, df):
    safe_st = _SafeStreamlit()
    env = {
        'pd': pd,
        'np': np,
        'px': px,
        'go': go,
        'plt': plt,
        'sns': sns,
        'st': safe_st,
        'df': df,
        'math': math,
        'scipy': scipy,
        'sklearn': sklearn,
        'pyg': pyg if PYG_AVAILABLE else None,
        'ta': ta,
        'sm': sm,
        'qs': qs,
        'duck': duckdb,
        'pl': pl,
        'alt': alt,
        'xgb': xgb
    }
    output = io.StringIO()
    plt.close('all')
    with contextlib.redirect_stdout(output):
        try:
            exec(code, env)
            return output.getvalue(), None
        except Exception as e:
            return output.getvalue(), str(e)

def calculate_session_performance(history_data):
    """Analyze trade history to generate session performance metrics."""
    deals = history_data.get("deals", [])
    if not deals:
        return None
    
    # Filter for closing deals only
    closed_deals = [d for d in deals if d.get("entry") == "CLOSE"]
    if not closed_deals:
        return None
    
    total_pnl = sum(d.get("profit", 0) for d in closed_deals)
    winning_deals = [d for d in closed_deals if d.get("profit", 0) > 0]
    losing_deals = [d for d in closed_deals if d.get("profit", 0) <= 0]
    
    win_rate = (len(winning_deals) / len(closed_deals) * 100) if closed_deals else 0
    
    avg_win = sum(d.get("profit", 0) for d in winning_deals) / len(winning_deals) if winning_deals else 0
    avg_loss = sum(d.get("profit", 0) for d in losing_deals) / len(losing_deals) if losing_deals else 0
    
    return {
        "total_pnl": float(total_pnl),
        "count": len(closed_deals),
        "wins": len(winning_deals),
        "losses": len(losing_deals),
        "win_rate": float(win_rate),
        "avg_win": float(avg_win),
        "avg_loss": float(avg_loss),
        "history": closed_deals
    }

def render_performance_tab(m_url, m_tok):
    """Renders the dynamic filtering session performance dashboard."""
    colA, colB = st.columns([4, 1])
    with colA:
        st.subheader("📊 Session Performance Vault")
    with colB:
        if st.button("🔄 Refresh History", width="stretch"):
            pass # Button click will trigger fragment re-run naturally
    
    try:
        history = fetch_trade_history(m_url, m_tok, hours=0) # 0 = Fetch all records 
        deals = history.get("deals", [])
        
        if not deals:
            st.info("No closed trades in the history. Start trading to see analytics!")
            return

        # Load into DataFrame for rapid filtering
        df_hist = pd.DataFrame(deals)
        df_hist['time'] = pd.to_datetime(df_hist['time'], errors='coerce')
        df_hist['comment'] = df_hist['comment'].fillna("")

        # --- DYNAMIC FILTERS UI ---
        with st.expander("🔍 Filter History Vault", expanded=True):
            f1, f2, f3, f4 = st.columns(4)
            
            # 1. Date Range Filters (Replaces Comment Filter)
            today = datetime.now().date()
            start_date = f1.date_input("Start Date", today - timedelta(days=7))
            end_date = f2.date_input("End Date", today)
            
            # 2. Symbol Filter
            all_symbols = ["All Symbols"] + sorted(list(df_hist['symbol'].unique()))
            selected_symbol = f3.selectbox("Symbol", all_symbols, index=0)
            
            # 3. Direction Filter
            selected_dir = f4.selectbox("Direction", ["All", "BUY", "SELL"], index=0)
            
        # Apply Logic
        df_filtered = df_hist.copy()
        
        # Apply Date Logic
        if start_date and end_date:
            start_dt = pd.to_datetime(start_date)
            end_dt = pd.to_datetime(end_date) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
            df_filtered = df_filtered[(df_filtered['time'] >= start_dt) & (df_filtered['time'] <= end_dt)]
            
        if selected_symbol != "All Symbols":
            df_filtered = df_filtered[df_filtered['symbol'] == selected_symbol]
        if selected_dir != "All":
            df_filtered = df_filtered[df_filtered['direction'] == selected_dir]
            
        if df_filtered.empty:
            st.warning("No trades match the selected filters.")
            return

        # --- DYNAMIC METRICS CALCULATION ---
        total_pnl = df_filtered['profit'].sum()
        winning_deals = df_filtered[df_filtered['profit'] > 0]
        losing_deals = df_filtered[df_filtered['profit'] <= 0]
        
        count_all = len(df_filtered)
        count_wins = len(winning_deals)
        count_losses = len(losing_deals)
        
        win_rate = (count_wins / count_all * 100) if count_all > 0 else 0
        avg_win = winning_deals['profit'].mean() if not winning_deals.empty else 0
        avg_loss = losing_deals['profit'].mean() if not losing_deals.empty else 0

        # Top Level Metrics
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Net Profit", f"${total_pnl:,.2f}", delta=f"{total_pnl:.2f}")
        m2.metric("Win Rate", f"{win_rate:.1f}%")
        m3.metric("Total Trades", count_all)
        m4.metric("Avg Win/Loss", f"${avg_win:.2f} / ${avg_loss:.2f}")

        # Visualization
        st.markdown("---")
        col1, col2 = st.columns([2, 1])
        
        with col1:
            st.caption("📈 Session Equity Growth (Filtered Trades)")
            df_curve = df_filtered.sort_values('time').copy()
            df_curve['cumulative_pnl'] = df_curve['profit'].cumsum()
            
            fig = px.line(df_curve, x='time', y='cumulative_pnl', 
                          title="Realized P&L Curve",
                          template="plotly_dark",
                          labels={'cumulative_pnl': 'Profit ($)', 'time': 'Time'})
            fig.update_traces(line_color='#00ff41', fill='tozeroy')
            st.plotly_chart(fig, use_container_width=True)
            
        with col2:
            st.caption("🎯 Win/Loss Distribution")
            dist_fig = px.pie(values=[count_wins, count_losses], 
                              names=['Wins', 'Losses'],
                              color_discrete_sequence=['#00ff41', '#ff4b4b'],
                              hole=0.4)
            dist_fig.update_layout(template="plotly_dark", showlegend=False)
            st.plotly_chart(dist_fig, use_container_width=True)

        # Detailed History Table
        st.markdown("---")
        st.subheader("📜 Detailed Trade History")
        
        df_display = df_filtered[['ticket', 'symbol', 'direction', 'volume', 'price', 'profit', 'time', 'comment']].copy()
        df_display = df_display.sort_values('time', ascending=False)
        st.dataframe(make_arrow_safe(df_display), width="stretch")

    except Exception as e:
        st.error(f"Failed to load performance data: {e}")

# ============================================================================
# Main Application
st.title("🏛️ NVIDIA NIM Professional Quant Station")

# --- MASTER MODE SWITCHER ---
st.markdown("---")
view_mode = st.radio(
    "Choose Analysis Data Source",
    ["🗄️ Historical Vault (Hugging Face)", "📡 Live MT5 Feed (Direct Broker)"],
    horizontal=True,
    help="Switch between deep historical archives and real-time broker data."
)
st.markdown("---")

if "Historical" in view_mode:
    st.markdown("### 📥 Load Recent Market Data (7-Day 1M)")
    colA, colB, colC = st.columns([1.5, 2.5, 1])
    with colA:
        # Get symbols from broker if connected, else use default
        available_syms = st.session_state.get("available_symbols", ["XAUUSD", "EURUSD", "DXY", "GBPUSD", "BTCUSD", "US30", "NAS100"])
        
        # Show symbol count if available
        sym_count = st.session_state.get("broker_symbol_count", len(available_syms))
        st.caption(f"📊 {sym_count} symbols available")
        
        symbol_choice = st.selectbox(
            "Select Symbol", 
            available_syms,
            label_visibility="collapsed"
        )
    with colB:
        if st.button(f"🚀 Fetch Last 7 Days ({symbol_choice})", width="stretch"):
            st.session_state.current_symbol_view = symbol_choice
            
            # Priority: Use MT5 if connected, otherwise Yahoo Finance
            mt5_connected = st.session_state.get("mt5_connected", False)
            mt5_url = st.session_state.get("mt5_url", "http://localhost:5000")
            mt5_token = get_secret("MT5_API_TOKEN", "impulse_secure_2026")
            
            data_source = ""
            
            if mt5_connected:
                # Fetch from MT5 (supports ALL broker symbols!)
                from data_sync import pull_mt5_latest
                with st.spinner(f"📡 Fetching 7-day data for {symbol_choice} from your broker..."):
                    try:
                        new_df = pull_mt5_latest(mt5_url, symbol_choice, "M1", 10080, mt5_token)  # 7 days x 24h x 60min = 10080
                        if not new_df.empty:
                            st.session_state.df = new_df
                            st.session_state[f"df_{symbol_choice}"] = new_df
                            st.session_state.file_name = f"MT5_{symbol_choice}_7D"
                            data_source = "MT5 Broker"
                            st.success(f"✅ Loaded **{len(new_df):,}** rows from {symbol_choice} (Zero OOM risk!).")
                        else:
                            st.error(f"❌ MT5 returned empty data for {symbol_choice}.")
                    except Exception as e:
                        st.warning(f"⚠️ MT5 fetch failed: {e}. Trying Yahoo Finance...")
                        mt5_connected = False  # Fallback to Yahoo
            
            if not mt5_connected or data_source == "":
                # Fallback: Yahoo Finance (limited mapping)
                from data_sync import YAHOO_MAPPING
                target_yh = YAHOO_MAPPING.get(symbol_choice)
                
                if target_yh:
                    import yfinance as yf
                    with st.spinner(f"📡 Fetching 7-day data for {symbol_choice} from Yahoo Finance..."):
                        try:
                            ticker = yf.Ticker(target_yh)
                            new_df = ticker.history(period="7d", interval="1m")
                            
                            if not new_df.empty:
                                new_df = new_df.reset_index()
                                time_col = next(
                                    (c for c in new_df.columns if c.lower() in ("datetime", "date")),
                                    new_df.columns[0]
                                )
                                new_df = new_df.rename(columns={
                                    time_col:       'time',
                                    'Open':         'open',
                                    'High':         'high',
                                    'Low':          'low',
                                    'Close':        'close',
                                    'Volume':       'tick_volume',
                                })
                                new_df['time'] = pd.to_datetime(new_df['time'], utc=True)
                                new_df.columns = [c.lower() for c in new_df.columns]
                                
                                st.session_state.df = new_df
                                st.session_state[f"df_{symbol_choice}"] = new_df
                                st.session_state.file_name = f"YahooFinance_{symbol_choice}_7D"
                                data_source = "Yahoo Finance"
                                st.success(f"✅ Loaded **{len(new_df):,}** rows from Yahoo Finance (Zero OOM risk!).")
                            else:
                                st.error(f"❌ Yahoo Finance returned 0 rows for {symbol_choice}. Markets might be closed.")
                        except Exception as e:
                            st.error(f"⚠️ Failed to fetch data from Yahoo Finance: {e}")
                else:
                    st.error(f"⚠️ No data source available for {symbol_choice}. Connect to MT5 broker for full symbol support!")
            
            st.session_state.messages = []
            st.rerun()

    with colC:
        if st.button("🧹 Clear Workspace", width="stretch"):
            if 'df' in st.session_state: del st.session_state['df']
            if 'df_live' in st.session_state: del st.session_state['df_live']
            st.session_state.messages = []
            st.session_state.messages_live = []
            st.rerun()

    # --- HISTORICAL ANALYSIS TABS (Only if data loaded) ---
    if 'df' in st.session_state and st.session_state.df is not None:
        df = st.session_state.df
        h_tab1, h_tab2, h_tab3 = st.tabs(["💬 AI Analyst", "🔍 Visual Explorer", "📋 Data Grid"])
        
        with h_tab1:
            st.subheader("🤖 AI Data Analyst (Historical)")
            with st.expander("📊 Data Preview & Schema", expanded=True):
                st.dataframe(make_arrow_safe(df.head()), width="stretch")
            
            # Historical Chat history
            if "messages" not in st.session_state: st.session_state.messages = []
            for m in st.session_state.messages:
                with st.chat_message(m["role"]):
                    display_content = filter_code_from_message(m.get("content", ""))
                    st.markdown(display_content)
                    # Code display removed - no longer showing code in dashboard
            
            if prompt := st.chat_input("Analyze the archive...", key="hist_chat"):
                process_ai_query(prompt, df, model_choice, api_key_to_use, provider_choice, history_key="messages", base_url=base_url)

        with h_tab2:
            st.subheader("📊 Visual Explorer")
            if PYG_AVAILABLE:
                st.components.v1.html(pyg.to_html(make_arrow_safe(df.tail(100000))), height=800, scrolling=True)
            else: st.info("PyGWalker unavailable on this instance.")

        with h_tab3:
            st.subheader("📋 Data Grid")
            st.dataframe(make_arrow_safe(df.tail(1000)))
    else:
        st.info("👋 Master Source: **Historical Vault** selected. Please load a dataset above to start analysis.")

elif "Live" in view_mode:
    st.markdown("### 📡 Live MT5 Broker Terminal")
    
    # ── STEP 1: Broker Bridge Connection Gate ────────────────────────────
    is_connected = st.session_state.get("mt5_connected", False)
    with st.expander("🔒 MT5 Broker Gate (Local Connection Settings)", expanded=not is_connected):
        c1, c2 = st.columns(2)
        with c1:
            mt5_url_in = st.text_input("MT5 Server URL", 
                                     value=st.session_state.get("mt5_url", "http://localhost:5000"), 
                                     placeholder="http://localhost:5000",
                                     key="live_mt5_url")
        with c2:
            mt5_tok_in = st.text_input("Security Token", 
                                     value=get_secret("MT5_API_TOKEN", "impulse_secure_2026"), 
                                     type="password",
                                     key="live_mt5_token")
            
        if st.button("🔌 Establish Broker Bridge", width="stretch"):
            with st.spinner("Pinging local server..."):
                from data_sync import ping_mt5_server
                res = ping_mt5_server(mt5_url_in, mt5_tok_in)
                if res["reachable"] and res["mt5_initialized"]:
                    st.session_state.mt5_connected = True
                    st.session_state.mt5_url = mt5_url_in
                    
                    # Fetch all available symbols from broker
                    try:
                        import requests
                        symbols_url = f"{mt5_url_in}/symbols/all"
                        headers = {"X-MT5-Token": mt5_tok_in}
                        symbols_res = requests.get(symbols_url, headers=headers, timeout=10)
                        if symbols_res.status_code == 200:
                            data = symbols_res.json()
                            all_symbols = [s["name"] for s in data.get("symbols", []) if s.get("visible", False)]
                            st.session_state.available_symbols = sorted(all_symbols)
                            st.session_state.broker_symbol_count = len(all_symbols)
                            st.success(f"✅ Bridge Established! Terminal Unlocked. ({len(all_symbols)} symbols loaded)")
                        else:
                            st.success("✅ Bridge Established! Terminal Unlocked.")
                    except Exception as e:
                        print(f"[Symbols] Could not fetch symbols: {e}")
                        st.success("✅ Bridge Established! Terminal Unlocked.")
                    
                    st.rerun()
                else:
                    st.session_state.mt5_connected = False
                    st.error("❌ Connection Failed. Ensure 'mt5_data_server.py' is running locally.")

    # ── STEP 2: Main Terminal (Only if bridge is active) ──────────────────
    if st.session_state.get("mt5_connected"):
        m_url = st.session_state.get("mt5_url", "http://localhost:5000")
        m_tok = get_secret("MT5_API_TOKEN", "impulse_secure_2026")

        # ── MULTI-TAB ARCHITECTURE ────────────────────────────────────────
        t_live, t_perf, t_intel = st.tabs(["📺 Live Terminal", "📜 Trade History", "🌐 Market Intel"])

        with t_live:
            # ── TRADE CONFIGURATION PANEL ──────────────────────────────────────
            with st.expander("⚙️ Trade Configuration", expanded=False):
                tc1, tc2, tc3 = st.columns(3)
                with tc1:
                    order_type = st.selectbox("Order Type", [
                        "Market", "Buy Limit", "Sell Limit", "Buy Stop", "Sell Stop"
                    ], key="trade_order_type")
                with tc2:
                    lot_mode = st.toggle("Auto Lot (Risk %)", value=False, key="trade_lot_mode")
                    if lot_mode:
                        risk_pct = st.number_input("Risk %", min_value=0.1, max_value=100.0, value=1.0, step=0.1, key="trade_risk_pct")
                    else:
                        manual_lot = st.number_input("Lot Size", min_value=0.01, max_value=100.0, value=0.10, step=0.01, key="trade_manual_lot")
                with tc3:
                    sl_tp_mode = st.toggle("Use AI SL/TP", value=True, key="trade_ai_sltp")

            # ── CHART & FEED CONTROLS ──────────────────────────────────────────
            st_col1, st_col2, st_col3, st_col4 = st.columns([1.5, 1, 1.5, 1.5])
            with st_col1:
                available_syms_live = st.session_state.get("available_symbols", ["XAUUSD", "EURUSD", "DXY"])
                sym_count_live = st.session_state.get("broker_symbol_count", len(available_syms_live))
                st.caption(f"📊 {sym_count_live} symbols available")
                l_sym = st.selectbox("Symbol", available_syms_live, key="l_sym")
            with st_col2: l_tf = st.selectbox("TF", ["1m", "5m", "15m", "1h"], key="l_tf")
            with st_col3: l_count = st.number_input("Lookback Bars", value=500, min_value=100, max_value=5000, step=100, key="l_count")
            with st_col4: 
                st.write("")
                live_active = st.toggle("Enable Continuous Feed 📡", value=st.session_state.get("live_active_state", False), key="live_active_sync")
                st.session_state.live_active_state = live_active

            # 🎯 SURGICAL FRAGMENT: Re-runs only the Chart area
            @st.fragment(run_every=60 if live_active else None)
            def live_chart_fragment(symbol, timeframe, count, active):
                m_url_f = st.session_state.get("mt5_url", "http://localhost:5000")
                m_tok_f = get_secret("MT5_API_TOKEN", "impulse_secure_2026")
                from data_sync import pull_mt5_latest
                # Use directly outside to be safe
                df_l = pull_mt5_latest(m_url_f, symbol, timeframe, count, m_tok_f)
                if not df_l.empty:
                    st.session_state.df_live = df_l
                    st.subheader(f"📊 {symbol} — {timeframe} Real-Time Feed")
                    last_bar = df_l.iloc[-1]
                    t_str = last_bar['time'].strftime('%H:%M:%S') if hasattr(last_bar['time'], 'strftime') else str(last_bar['time'])
                    m1, m2, m3, m4, m5 = st.columns(5)
                    m1.metric("⏲️ Terminal Time", t_str)
                    m2.metric("🟢 OPEN", f"{last_bar['open']:.5f}")
                    m3.metric("📈 HIGH", f"{last_bar['high']:.5f}", delta=f"{(last_bar['high']-last_bar['open']):.5f}")
                    m4.metric("📉 LOW",  f"{last_bar['low']:.5f}",  delta=f"{(last_bar['low']-last_bar['open']):.5f}")
                    m5.metric("🎯 CURRENT", f"{last_bar['close']:.5f}", delta=f"{(last_bar['close']-last_bar['open']):.5f}")
                    fig = go.Figure(data=[go.Candlestick(x=df_l['time'], open=df_l['open'], high=df_l['high'], low=df_l['low'], close=df_l['close'])])
                    fig.update_layout(template="plotly_dark", height=500, margin=dict(l=10,r=10,t=10,b=10), showlegend=False)
                    st.plotly_chart(fig, use_container_width=True)

            live_chart_fragment(l_sym, l_tf, l_count, live_active)

            @st.fragment(run_every=1000)
            def position_manager_fragment():
                pm_url = st.session_state.get("mt5_url", "http://localhost:5000")
                pm_tok = get_secret("MT5_API_TOKEN", "impulse_secure_2026")
                try:
                    summary = fetch_open_positions(pm_url, pm_tok)
                except Exception: return
                if "last_open_count" in st.session_state and "last_positions" in st.session_state:
                    if summary.get("open_count", 0) < st.session_state.last_open_count:
                        # Find which tickets were closed
                        current_tickets = [p["ticket"] for p in summary.get("positions", [])]
                        last_tickets = [p["ticket"] for p in st.session_state.last_positions]
                        closed_tickets = [t for t in last_tickets if t not in current_tickets]
                        
                        try:
                            # Fetch recent history to find details of the closed trade
                            history = fetch_trade_history(pm_url, pm_tok, hours=1)
                            deals = history.get("deals", [])
                            for ticket in closed_tickets:
                                # Find deal matching this order/ticket
                                matching_deal = next((d for d in deals if d.get("ticket") == ticket and d.get("entry") == "CLOSE"), None)
                                if matching_deal:
                                    pnl = matching_deal.get("profit", 0)
                                    sym = matching_deal.get("symbol", "Trade")
                                    comm = matching_deal.get("comment", "").lower()
                                    
                                    # Detect if TP or SL hit
                                    reason = ""
                                    if "[tp]" in comm or "tp" in comm: reason = " (TP hit) 🎯"
                                    elif "[sl]" in comm or "sl" in comm: reason = " (SL hit) 🛡️"
                                    
                                    prefix = "✅" if pnl >= 0 else "❌"
                                    st.toast(f"{prefix} {sym} #{ticket} closed: ${pnl:+.2f}{reason}")
                                else:
                                    st.toast(f"🔔 Position #{ticket} closed! Check history for details.")
                        except Exception:
                            st.toast("🔔 A position has been closed! Check history for details.")
                
                st.session_state.last_open_count = summary.get("open_count", 0)
                st.session_state.last_positions = summary.get("positions", [])
                st.markdown("---")
                st.subheader("📋 Active Positions")
                bal = summary.get("balance", 0)
                eq = summary.get("equity", 0)
                ml = summary.get("margin_level", 0)
                tp_val = summary.get("total_profit", 0)
                oc = summary.get("open_count", 0)
                am1, am2, am3, am4 = st.columns(4)
                am1.metric("💰 Balance", f"${bal:,.2f}")
                am2.metric("📊 Equity", f"${eq:,.2f}", delta=f"${eq - bal:,.2f}")
                am3.metric("📈 Margin Level", f"{ml:.1f}%")
                am4.metric("📦 Open Count", f"{oc}", delta=f"${tp_val:,.2f}", delta_color="normal" if tp_val >= 0 else "inverse")
                positions = summary.get("positions", [])
                if positions:
                    for pos in positions:
                        p_color = "🟢" if pos["profit"] >= 0 else "🔴"
                        with st.container(border=True):
                            pc1, pc2, pc3, pc4, pc5, pc6, pc7, pc8 = st.columns([1, 1.5, 0.8, 1, 1, 1, 1, 1.5])
                            pc1.markdown(f"**{p_color} #{pos['ticket']}**")
                            pc2.markdown(f"**{pos['symbol']}** {pos['direction']}")
                            pc3.markdown(f"Vol: {pos['volume']}")
                            pc4.markdown(f"Entry: {pos['entry_price']}")
                            pc5.markdown(f"Current: {pos['current_price']}")
                            pc6.markdown(f"SL: {pos['sl'] or '-'}")
                            pc7.markdown(f"TP: {pos['tp'] or '-'}")
                            pc8.markdown(f"**P&L: ${pos['profit']:.2f}**")
                            act1, act2, act3 = st.columns(3)
                            with act1:
                                st.button(f"❌ Close", key=f"close_{pos['ticket']}", 
                                          on_click=on_close_position_cb, args=(pm_url, pm_tok, pos["ticket"]))
                            with act2: n_sl = st.number_input("SL", value=pos.get("sl") or 0.0, step=0.01, key=f"sl_{pos['ticket']}", label_visibility="collapsed")
                            with act3: n_tp = st.number_input("TP", value=pos.get("tp") or 0.0, step=0.01, key=f"tp_{pos['ticket']}", label_visibility="collapsed")
                            st.button(f"✏️ Update", key=f"mod_{pos['ticket']}", 
                                      on_click=on_modify_position_cb, args=(pm_url, pm_tok, pos["ticket"], n_sl, n_tp))
                else: st.info("No open positions. Use the AI Analyst to find setups.")
            
            position_manager_fragment()

            @st.fragment()
            def live_ai_analyst_fragment():
                st.markdown("---")
                st.subheader("🤖 Live AI Trade Analyst")
                if "messages_live" not in st.session_state: st.session_state.messages_live = []
                
                # --- TRANSACTION STATUS (V2.7) ---
                if st.session_state.last_exec_msg:
                    st.info(st.session_state.last_exec_msg)
                    if st.button("Clear Status"): 
                        st.session_state.last_exec_msg = ""
                        st.rerun()

                # Render messages with unique IDs based on index
                for i, m in enumerate(st.session_state.messages_live):
                    with st.chat_message(m["role"]):
                        display_content = filter_code_from_message(m.get("content", ""))
                        st.markdown(display_content)
                        if m.get("detected_setup"): 
                            render_trade_card(m["detected_setup"], m_url, m_tok, card_id=f"msg_{i}")
                        if m.get("detected_action"): 
                            render_action_card(m["detected_action"], m_url, m_tok)
                
                if chat_l := st.chat_input("Analyze live price action...", key="live_chat"):
                    snapshot_df = st.session_state.df_live.copy()
                    trade_context = build_trade_context(m_url, m_tok)
                    enhanced_prompt = f"{trade_context}\n\n{chat_l}" if trade_context else chat_l
                    process_ai_query(enhanced_prompt, snapshot_df, model_choice, api_key_to_use, provider_choice, history_key="messages_live", base_url=base_url, snapshot=snapshot_df)
            
            live_ai_analyst_fragment()

        with t_perf:
            @st.fragment(run_every=10) # 10 SECONDS
            def live_performance_fragment():
                p_url = st.session_state.get("mt5_url", "http://localhost:5000")
                p_tok = get_secret("MT5_API_TOKEN", "impulse_secure_2026")
                render_performance_tab(p_url, p_tok)
            
            live_performance_fragment()

        with t_intel:
            st.subheader("🌐 Global Web Intel")
            s_query = st.text_input("Topic", placeholder="e.g. Fed news", key="intel_search_tab")
            if st.button("🔍 Run Deep Intel", key="intel_btn"):
                if s_query:
                    from web_search import get_market_news, analyze_sentiment
                    with st.spinner("Searching..."):
                        news = get_market_news(s_query, max_results=5)
                        sent = analyze_sentiment(news) if news else "Unknown"
                        st.info(f"🧠 AI Sentiment: {sent}")
                        for n in news:
                            with st.expander(n['title']):
                                st.write(n['body'])
                                st.link_button("Read Source", n['href'])

    else:
        st.info("📡 Broker Terminal Locked. Please establish the bridge above to stream live market data.")
else:
    st.info("👋 Welcome! Please select a Mode above to begin.")
    st.image("https://developer.nvidia.com/sites/default/files/akamai/NVIDIA_NIM_Icon.png", width=100)
