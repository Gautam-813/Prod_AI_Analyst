"""
MT5 Data Server - On-Demand OHLC Data Provider
Provides data directly as JSON (no file storage)
Powered by FastAPI + Uvicorn
"""
import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime, timedelta
import pytz
from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, Annotated
import re
import os
import signal
import sys
import io
import socket
import uvicorn

# Fix Windows console encoding for emoji support
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

# --- 🛡️ MT5 SAFE CONSTANTS ---
# Older or different versions of the MT5 library might miss some attributes. 
# We define them here as fallbacks to ensure the server NEVER crashes on order placement.
def safe_mt5_getattr(attr, fallback):
    return getattr(mt5, attr) if hasattr(mt5, attr) else fallback

# Filling Modes
ORDER_FILLING_FOK = safe_mt5_getattr('ORDER_FILLING_FOK', 1)
ORDER_FILLING_IOC = safe_mt5_getattr('ORDER_FILLING_IOC', 2)
ORDER_FILLING_RETURN = safe_mt5_getattr('ORDER_FILLING_RETURN', 3)

# Action Types
TRADE_ACTION_DEAL = safe_mt5_getattr('TRADE_ACTION_DEAL', 1)
TRADE_ACTION_PENDING = safe_mt5_getattr('TRADE_ACTION_PENDING', 5)
TRADE_ACTION_SLTP = safe_mt5_getattr('TRADE_ACTION_SLTP', 6)
TRADE_ACTION_MODIFY = safe_mt5_getattr('TRADE_ACTION_MODIFY', 7)

# Order Types
ORDER_TYPE_BUY = safe_mt5_getattr('ORDER_TYPE_BUY', 0)
ORDER_TYPE_SELL = safe_mt5_getattr('ORDER_TYPE_SELL', 1)
# -----------------------------
try:
    import mplfinance as mpf
except ImportError:
    pass

# ============================================================================
# Dynamic Server Metadata
# ============================================================================
def get_network_ip():
    """Detect the primary network IP of this machine."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # Doesn't need real connectivity, just triggers OS to resolve local interface
        s.connect(('8.8.8.8', 1))
        IP = s.getsockname()[0]
    except Exception:
        IP = '127.0.0.1'
    finally:
        s.close()
    return IP

SERVER_IP = get_network_ip()
def get_startup_config():
    # Priority 1: Environment Variables (Prevents blocking for EXEs/headless)
    port_env = os.getenv("MT5_SERVER_PORT")
    token_env = os.getenv("MT5_API_TOKEN")
    terminal_env = os.getenv("MT5_TERMINAL_PATH")

    if port_env and token_env:
        return int(port_env), token_env, terminal_env
    
    # Priority 2: Interactive CLI (Fallback if no environment is set)
    print("\n" + "=" * 60)
    print("      🚀 MT5 Data Server v2.6 — Configuration Startup")
    print("=" * 60 + "\n")

    default_port = os.getenv("MT5_SERVER_PORT", "5000")
    port_input = input(f"🔹 Enter Port [Default {default_port}]: ") or default_port
    port = int(port_input)

    default_token = os.getenv("MT5_API_TOKEN", "impulse_secure_2026")
    token_input = input(f"🔹 Enter Security Token [Default '{default_token}']: ") or default_token
    
    print("\n🔹 Multiple MT5 Instances Detected?")
    print("   (Leave empty to use your default/active MT5)")
    terminal_path = input("🔹 Enter MT5 Terminal Path (e.g. C:\\...\\terminal64.exe): ").strip() or None

    return port, token_input, terminal_path

PORT, MT5_API_TOKEN, STARTUP_PATH = get_startup_config()

async def verify_token(x_mt5_token: Annotated[str | None, Header()] = None):
    if x_mt5_token != MT5_API_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid or missing MT5 Security Token")
    return x_mt5_token

# ============================================================================
# FastAPI App
# ============================================================================
app = FastAPI(
    title="MT5 Data Server",
    description="On-Demand OHLC Data Provider for MetaTrader 5",
    version="2.0.0"
)

# Allow all origins so Streamlit (on any host) can call this server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================================
# Pydantic Request Models (replaces Flask request.json)
# ============================================================================
class InitializeRequest(BaseModel):
    terminal_path: Optional[str] = None

class SymbolSearchRequest(BaseModel):
    pattern: str

class FetchDataRequest(BaseModel):
    symbol: str
    timeframe: str   # 1m, 5m, 15m, 30m, 1h, 4h, 1d, 1w, 1M
    start_date: str  # ISO format: 2026-03-19T00:00:00Z
    end_date: str

class QuickFetchRequest(BaseModel):
    symbol: str
    preset: str = "yesterday_to_now"  # yesterday_to_now, last_24h, last_week, today, last_hour
    timeframe: str = "1m"

class FetchLatestRequest(BaseModel):
    symbol: str
    timeframe: str
    count: int = 500

# ============================================================================
# Order & Trade Pydantic Models
# ============================================================================
class PlaceOrderRequest(BaseModel):
    symbol: str
    action: str  # "BUY", "SELL", "BUY_LIMIT", "SELL_LIMIT", "BUY_STOP", "SELL_STOP"
    volume: float  # Lot size
    price: Optional[float] = None  # Required for pending orders
    sl: Optional[float] = None
    tp: Optional[float] = None
    comment: str = "[IMPULSE_V2]"
    magic: int = 0

class CloseOrderRequest(BaseModel):
    ticket: int
    volume: Optional[float] = None  # Partial close; None = full close

class ModifyOrderRequest(BaseModel):
    ticket: int
    sl: Optional[float] = None
    tp: Optional[float] = None

# ============================================================================
# MT5 Provider Class (unchanged from original)
# ============================================================================
class MT5DataProvider:
    def __init__(self):
        self.initialized = False
        self.terminal_path = None
        self._symbol_cache = {}  # ⚡ ASAP Symbol Resolution Cache (Key: User Input, Value: Broker Symbol)

    def initialize_mt5(self, terminal_path=None):
        """Initialize MT5 connection"""
        if self.initialized:
            return True
        try:
            if terminal_path:
                if not mt5.initialize(path=terminal_path):
                    return False
            else:
                if not mt5.initialize():
                    return False
            self.initialized = True
            self.terminal_path = terminal_path
            return True
        except Exception as e:
            print(f"MT5 initialization error: {e}")
            return False

    def shutdown(self):
        """Shutdown MT5 connection"""
        if self.initialized:
            mt5.shutdown()
            self.initialized = False

    def find_symbols(self, pattern):
        """Find symbols matching pattern (e.g., 'XAUUSD' finds XAUUSD, XAUUSDm, XAUUSD.sc)"""
        if not self.initialized:
            return []
        try:
            all_symbols = mt5.symbols_get()
            if all_symbols is None:
                return []
            regex_pattern = re.compile(pattern, re.IGNORECASE)
            matched = []
            for symbol in all_symbols:
                if regex_pattern.search(symbol.name):
                    matched.append({
                        'name': symbol.name,
                        'description': symbol.description,
                        'path': symbol.path,
                        'visible': symbol.visible
                    })
            return matched
        except Exception as e:
            print(f"Symbol search error: {e}")
            return []

    def get_symbol_info(self, symbol):
        """Get detailed symbol information"""
        if not self.initialized:
            return None
        try:
            info = mt5.symbol_info(symbol)
            if info is None:
                return None
            return {
                'name': info.name,
                'description': info.description,
                'point': info.point,
                'digits': info.digits,
                'trade_contract_size': info.trade_contract_size,
                'visible': info.visible
            }
        except Exception as e:
            print(f"Symbol info error: {e}")
            return None

    def resolve_symbol_name(self, target_name):
        """
        Smart resolution: XAUUSD -> XAUUSDm, XAUUSD.sc, etc.
        Uses ⚡ Cached resolution for sub-millisecond response.
        """
        if not target_name: return ""
        t_upper = target_name.upper()

        # 1. ⚡ Quick Cache Hit (Returns ASAP)
        if t_upper in self._symbol_cache:
            return self._symbol_cache[t_upper]

        # 2. Direct exact match in MT5
        if mt5.symbol_info(target_name):
            self._symbol_cache[t_upper] = target_name
            return target_name

        # 3. Case-insensitive Regex search (Heavy operation, done once per symbol)
        try:
            print(f"🔍 Searching broker symbols for '{target_name}' match...")
            all_symbols = mt5.symbols_get()
            if all_symbols:
                regex = re.compile(re.escape(target_name), re.IGNORECASE)
                for s in all_symbols:
                    if regex.search(s.name):
                        print(f"✅ Resolved '{target_name}' → '{s.name}' (Cached)")
                        self._symbol_cache[t_upper] = s.name
                        return s.name
                
                # Special case aliases
                aliases = {"GOLD": "XAUUSD", "SILVER": "XAGUSD", "USDX": "DXY"}
                if t_upper in aliases:
                    alias_target = aliases[t_upper]
                    regex_alias = re.compile(re.escape(alias_target), re.IGNORECASE)
                    for s in all_symbols:
                        if regex_alias.search(s.name):
                            self._symbol_cache[t_upper] = s.name
                            print(f"✅ Resolved '{target_name}' → '{s.name}' (Alias Cached)")
                            return s.name
        except Exception as e:
            print(f"Symbol lookup error: {e}")
        
        return target_name # fallback

    def fetch_ohlc_data(self, symbol, timeframe, start_date, end_date):
        """
        Fetch OHLC data for given parameters
        """
        if not self.initialized:
            return None, "MT5 not initialized"
        
        try:
            # Smart Resolve Symbol Name
            symbol = self.resolve_symbol_name(symbol)

            # Enable symbol if not visible
            if not mt5.symbol_select(symbol, True):
                return None, f"Failed to select symbol: {symbol}"

            timeframe_map = {
                '1m':  mt5.TIMEFRAME_M1,
                '5m':  mt5.TIMEFRAME_M5,
                '15m': mt5.TIMEFRAME_M15,
                '30m': mt5.TIMEFRAME_M30,
                '1h':  mt5.TIMEFRAME_H1,
                '4h':  mt5.TIMEFRAME_H4,
                '1d':  mt5.TIMEFRAME_D1,
                '1w':  mt5.TIMEFRAME_W1,
                '1M':  mt5.TIMEFRAME_MN1
            }
            tf = timeframe_map.get(timeframe, mt5.TIMEFRAME_M1)

            timezone = pytz.timezone("Etc/UTC")
            if isinstance(start_date, str):
                start_dt = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
            else:
                start_dt = start_date
            if isinstance(end_date, str):
                end_dt = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
            else:
                end_dt = end_date

            if start_dt.tzinfo is None:
                start_dt = timezone.localize(start_dt)
            if end_dt.tzinfo is None:
                end_dt = timezone.localize(end_dt)

            rates = mt5.copy_rates_range(symbol, tf, start_dt, end_dt)
            if rates is None or len(rates) == 0:
                return None, f"No data available for {symbol}"

            df = pd.DataFrame(rates)
            df['time'] = pd.to_datetime(df['time'], unit='s')
            return df, None
        except Exception as e:
            return None, f"Data fetch error: {str(e)}"

# Global provider instance
provider = MT5DataProvider()

# ============================================================================
# API ENDPOINTS
# ============================================================================

@app.get("/health")
def health_check(token: Annotated[str, Depends(verify_token)]):
    """Check if server is running and MT5 status"""
    return {
        "status": "running",
        "mt5_initialized": provider.initialized,
        "terminal_path": provider.terminal_path
    }

@app.post("/initialize")
def initialize(req: InitializeRequest, token: Annotated[str, Depends(verify_token)]):
    """Initialize MT5 connection"""
    success = provider.initialize_mt5(req.terminal_path)
    if success:
        account_info = mt5.account_info()
        return {
            "success": True,
            "message": "MT5 initialized successfully",
            "account": account_info.login if account_info else None,
            "server": account_info.server if account_info else None
        }
    raise HTTPException(status_code=500, detail={
        "success": False,
        "message": "Failed to initialize MT5",
        "error": str(mt5.last_error())
    })

@app.post("/symbols/search")
def search_symbols(req: SymbolSearchRequest, token: Annotated[str, Depends(verify_token)]):
    """Search for symbols matching a regex pattern"""
    if not provider.initialized:
        raise HTTPException(status_code=400, detail="MT5 not initialized")
    if not req.pattern:
        raise HTTPException(status_code=400, detail="Pattern required")
    symbols = provider.find_symbols(req.pattern)
    return {
        "pattern": req.pattern,
        "count": len(symbols),
        "symbols": symbols
    }

@app.get("/symbols/info/{symbol}")
def symbol_info(symbol: str, token: Annotated[str, Depends(verify_token)]):
    """Get detailed symbol information"""
    if not provider.initialized:
        raise HTTPException(status_code=400, detail="MT5 not initialized")
    info = provider.get_symbol_info(symbol)
    if info is None:
        raise HTTPException(status_code=404, detail=f"Symbol {symbol} not found")
    return info

@app.post("/data/fetch")
def fetch_data(req: FetchDataRequest, token: Annotated[str, Depends(verify_token)]):
    """
    Fetch OHLC data and return directly as JSON.

    Timeframes: 1m, 5m, 15m, 30m, 1h, 4h, 1d, 1w, 1M
    Dates: ISO format e.g. 2026-03-19T00:00:00Z
    """
    if not provider.initialized:
        raise HTTPException(status_code=400, detail="MT5 not initialized. Call /initialize first")

    df, error = provider.fetch_ohlc_data(
        symbol=req.symbol,
        timeframe=req.timeframe,
        start_date=req.start_date,
        end_date=req.end_date
    )
    if error:
        raise HTTPException(status_code=500, detail=error)

    df['time'] = df['time'].dt.strftime('%Y-%m-%d %H:%M:%S')
    data_records = df.to_dict('records')

    print("\n" + "="*70)
    print(f"✓ Fetched {len(data_records)} candles for {req.symbol}")
    print(f"  Timeframe: {req.timeframe}")
    print(f"  Range: {df['time'].iloc[0]} → {df['time'].iloc[-1]}")
    print("="*70 + "\n")

    return {
        "success": True,
        "symbol": req.symbol,
        "timeframe": req.timeframe,
        "rows": len(data_records),
        "columns": list(df.columns),
        "date_range": {
            "start": df['time'].iloc[0],
            "end": df['time'].iloc[-1]
        },
        "data": data_records
    }

@app.post("/data/quick-fetch")
def quick_fetch(req: QuickFetchRequest, token: Annotated[str, Depends(verify_token)]):
    """
    Quick fetch with common presets.

    Presets: yesterday_to_now, last_24h, last_week, today, last_hour
    """
    if not provider.initialized:
        raise HTTPException(status_code=400, detail="MT5 not initialized")

    # 📡 PULSE CHECK: Get Terminal/Broker "Now" (The only source of truth)
    sym_clean = provider.resolve_symbol_name(req.symbol)
    tick = mt5.symbol_info_tick(sym_clean)
    if tick:
        # Get terminal time from last tick
        now = datetime.fromtimestamp(tick.time, pytz.UTC)
    else:
        # Fallback to UTC only if market is closed or symbol unknown
        now = datetime.now(pytz.UTC)

    presets = {
        'yesterday_to_now': (now - timedelta(days=1), now),
        'last_24h':         (now - timedelta(hours=24), now),
        'last_week':        (now - timedelta(days=7), now),
        'today':            (now.replace(hour=0, minute=0, second=0, microsecond=0), now),
        'last_hour':        (now - timedelta(hours=1), now)
    }

    if req.preset not in presets:
        raise HTTPException(status_code=400, detail=f"Invalid preset. Choose from: {list(presets.keys())}")

    start_date, end_date = presets[req.preset]
    df, error = provider.fetch_ohlc_data(req.symbol, req.timeframe, start_date, end_date)
    if error:
        raise HTTPException(status_code=500, detail=error)

    df['time'] = df['time'].dt.strftime('%Y-%m-%d %H:%M:%S')
    data_records = df.to_dict('records')

    print("\n" + "="*70)
    print(f"✓ Quick Fetch: {req.preset}")
    print(f"  Symbol: {req.symbol} | TF: {req.timeframe} | Candles: {len(data_records)}")
    print(f"  Range: {df['time'].iloc[0]} → {df['time'].iloc[-1]}")
    print("="*70 + "\n")

    return {
        "success": True,
        "symbol": req.symbol,
        "timeframe": req.timeframe,
        "preset": req.preset,
        "rows": len(data_records),
        "columns": list(df.columns),
        "date_range": {
            "start": df['time'].iloc[0],
            "end": df['time'].iloc[-1]
        },
        "data": data_records
    }

@app.post("/data/fetch-latest")
def fetch_latest(req: FetchLatestRequest, token: Annotated[str, Depends(verify_token)]):
    """
    Fetch the LAST 'count' candles directly by position (0 = latest).
    This ignores system clock differences between broker and local server.
    """
    if not provider.initialized:
        raise HTTPException(status_code=400, detail="MT5 not initialized")
    
    symbol = provider.resolve_symbol_name(req.symbol)
    if not mt5.symbol_select(symbol, True):
        raise HTTPException(status_code=404, detail=f"Symbol {symbol} not found")
        
    timeframe_map = {
        '1m':  mt5.TIMEFRAME_M1,
        '5m':  mt5.TIMEFRAME_M5,
        '15m': mt5.TIMEFRAME_M15,
        '30m': mt5.TIMEFRAME_M30,
        '1h':  mt5.TIMEFRAME_H1,
        '4h':  mt5.TIMEFRAME_H4,
        '1d':  mt5.TIMEFRAME_D1,
        '1w':  mt5.TIMEFRAME_W1,
        '1M':  mt5.TIMEFRAME_MN1
    }
    tf = timeframe_map.get(req.timeframe, mt5.TIMEFRAME_M1)
    
    # Position-based fetch: start=0, count=req.count
    rates = mt5.copy_rates_from_pos(symbol, tf, 0, req.count)
    if rates is None or len(rates) == 0:
        raise HTTPException(status_code=500, detail="No data available from MT5 bridge")
        
    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    df['time'] = df['time'].dt.strftime('%Y-%m-%d %H:%M:%S')
    data_records = df.to_dict('records')
    
    print(f"🔥 Position Fetch: {req.symbol} | Start=0 | Count={req.count}")
    
    return {
        "success": True,
        "symbol": req.symbol,
        "timeframe": req.timeframe,
        "rows": len(data_records),
        "data": data_records
    }

@app.post("/order/place")
def place_order(req: PlaceOrderRequest, token: Annotated[str, Depends(verify_token)]):
    """Place a market or pending order directly in MT5."""
    if not provider.initialized:
        raise HTTPException(status_code=400, detail="MT5 not initialized")

    symbol = provider.resolve_symbol_name(req.symbol)
    if not mt5.symbol_select(symbol, True):
        raise HTTPException(status_code=404, detail=f"Symbol {symbol} not found")

    # Get detailed symbol info ASAP (combining info + tick)
    symbol_info = mt5.symbol_info(symbol)
    tick = mt5.symbol_info_tick(symbol)

    if symbol_info is None or tick is None:
        raise HTTPException(status_code=400, detail=f"Broker data unavailable for {symbol}")

    if req.volume < symbol_info.volume_min:
        raise HTTPException(status_code=400, detail=f"Volume {req.volume} below minimum {symbol_info.volume_min}")
    
    volume_step = symbol_info.volume_step
    volume = round(req.volume / volume_step) * volume_step
    volume = round(volume, 2)

    point = symbol_info.point
    digits = symbol_info.digits
    min_stop_points = symbol_info.trade_stops_level  # Minimum distance in points
    min_stop_price = (min_stop_points * point) if min_stop_points else (point * 10)
    # Add buffer
    min_stop_price = max(min_stop_price, point * 5)

    action_map = {
        "BUY": ORDER_TYPE_BUY,
        "SELL": ORDER_TYPE_SELL,
        "BUY_LIMIT": getattr(mt5, 'ORDER_TYPE_BUY_LIMIT', 2),
        "SELL_LIMIT": getattr(mt5, 'ORDER_TYPE_SELL_LIMIT', 3),
        "BUY_STOP": getattr(mt5, 'ORDER_TYPE_BUY_STOP', 4),
        "SELL_STOP": getattr(mt5, 'ORDER_TYPE_SELL_STOP', 5),
    }

    if req.action not in action_map:
        raise HTTPException(status_code=400, detail=f"Invalid action: {req.action}. Choose from {list(action_map.keys())}")

    order_type = action_map[req.action]
    is_pending = req.action in ("BUY_LIMIT", "SELL_LIMIT", "BUY_STOP", "SELL_STOP")

    if is_pending and req.price is None:
        raise HTTPException(status_code=400, detail="Price is required for pending orders")

    if is_pending:
        price = req.price
    elif req.action == "BUY":
        price = tick.ask
    else:
        price = tick.bid

    if price is None:
        raise HTTPException(status_code=500, detail="Cannot get current price for symbol")

    price = round(price, digits)

    # Validate SL/TP
    if not is_pending:
        if req.sl is not None:
            sl = round(req.sl, digits)
            if req.action == "BUY":
                if sl >= price:
                    sl = round(price - abs(price - sl) - min_stop_price, digits)
                if (price - sl) < min_stop_price:
                    sl = round(price - min_stop_price, digits)
            else:  # SELL
                if sl <= price:
                    sl = round(price + abs(price - sl) + min_stop_price, digits)
                if (sl - price) < min_stop_price:
                    sl = round(price + min_stop_price, digits)
        else:
            sl = None

        if req.tp is not None:
            tp = round(req.tp, digits)
            if req.action == "BUY":
                if tp <= price:
                    tp = round(price + abs(price - tp) + min_stop_price, digits)
                if (tp - price) < min_stop_price:
                    tp = round(price + min_stop_price, digits)
            else:  # SELL
                if tp >= price:
                    tp = round(price - abs(price - tp) - min_stop_price, digits)
                if (price - tp) < min_stop_price:
                    tp = round(price - min_stop_price, digits)
        else:
            tp = None
    else:
        sl = round(req.sl, digits) if req.sl is not None else None
        tp = round(req.tp, digits) if req.tp is not None else None

    deviation = 20

    request = {
        "action": TRADE_ACTION_DEAL if not is_pending else TRADE_ACTION_PENDING,
        "symbol": symbol,
        "volume": volume,
        "type": order_type,
        "price": price,
        "deviation": deviation,
        "magic": req.magic,
        "comment": req.comment,
        "type_time": getattr(mt5, 'ORDER_TIME_GTC', 0),
        "type_filling": ORDER_FILLING_IOC,
    }

    if sl:
        request["sl"] = sl
    if tp:
        request["tp"] = tp

    if not is_pending:
        filling_mode = symbol_info.filling_mode
        # Dynamic filling mode detection (bitmask: 1=FOK, 2=IOC)
        if filling_mode & 1:
            request["type_filling"] = ORDER_FILLING_FOK
        elif filling_mode & 2:
            request["type_filling"] = ORDER_FILLING_IOC
        else:
            request["type_filling"] = ORDER_FILLING_RETURN

    result = mt5.order_send(request)

    if result is None or result.retcode != getattr(mt5, 'TRADE_RETCODE_DONE', 10009):
        retcode = result.retcode if result else "None"
        comment = result.comment if result else "No response"
        error_msg = f"Order failed: retcode={retcode}, comment={comment}"
        print(f"❌ {error_msg}")
        raise HTTPException(status_code=400, detail=error_msg)

    print(f"✅ Order placed: {req.action} {volume} {symbol} @ {price} | Ticket: {result.order} | SL: {sl} | TP: {tp}")

    return {
        "success": True,
        "ticket": result.order,
        "symbol": symbol,
        "action": req.action,
        "volume": volume,
        "price": price,
        "sl": sl,
        "tp": tp,
        "comment": result.comment,
    }


@app.post("/order/close")
def close_order(req: CloseOrderRequest, token: Annotated[str, Depends(verify_token)]):
    """Close an open position by ticket (full or partial)."""
    if not provider.initialized:
        raise HTTPException(status_code=400, detail="MT5 not initialized")

    positions = mt5.positions_get(ticket=req.ticket)
    if positions is None or len(positions) == 0:
        raise HTTPException(status_code=404, detail=f"No open position found for ticket {req.ticket}")

    position = positions[0]
    close_volume = req.volume if req.volume else position.volume

    if close_volume > position.volume:
        raise HTTPException(status_code=400, detail=f"Close volume {close_volume} exceeds position volume {position.volume}")

    if position.type == mt5.POSITION_TYPE_BUY:
        price = mt5.symbol_info_tick(position.symbol).bid
        order_type = mt5.ORDER_TYPE_SELL
    else:
        price = mt5.symbol_info_tick(position.symbol).ask
        order_type = mt5.ORDER_TYPE_BUY

    symbol_info = mt5.symbol_info(position.symbol)
    filling_mode = symbol_info.filling_mode if symbol_info else 2  # 2 = IOC fallback
    # Dynamic filling mode detection (bitmask: 1=FOK, 2=IOC)
    if filling_mode & 1:
        type_filling = mt5.ORDER_FILLING_FOK
    elif filling_mode & 2:
        type_filling = mt5.ORDER_FILLING_IOC
    else:
        type_filling = mt5.ORDER_FILLING_RETURN

    request = {
        "action": TRADE_ACTION_DEAL,
        "symbol": position.symbol,
        "volume": close_volume,
        "type": order_type,
        "position": req.ticket,
        "price": price,
        "deviation": 20,
        "magic": 0,
        "comment": "[IMPULSE_V2]",
        "type_time": getattr(mt5, 'ORDER_TIME_GTC', 0),
        "type_filling": type_filling,
    }

    result = mt5.order_send(request)

    if result is None or result.retcode != getattr(mt5, 'TRADE_RETCODE_DONE', 10009):
        retcode = result.retcode if result else "None"
        comment = result.comment if result else "No response"
        raise HTTPException(status_code=400, detail=f"Close failed: retcode={retcode}, comment={comment}")

    print(f"✅ Position closed: Ticket {req.ticket} | {close_volume} {position.symbol} @ {price}")

    return {
        "success": True,
        "ticket": req.ticket,
        "closed_volume": close_volume,
        "close_price": price,
        "comment": result.comment,
    }


@app.post("/order/modify")
def modify_order(req: ModifyOrderRequest, token: Annotated[str, Depends(verify_token)]):
    """Modify SL and/or TP of an open position."""
    if not provider.initialized:
        raise HTTPException(status_code=400, detail="MT5 not initialized")

    positions = mt5.positions_get(ticket=req.ticket)
    if positions is None or len(positions) == 0:
        raise HTTPException(status_code=404, detail=f"No open position found for ticket {req.ticket}")

    position = positions[0]
    symbol_info = mt5.symbol_info(position.symbol)
    if symbol_info is None:
        raise HTTPException(status_code=400, detail=f"Cannot get symbol info for {position.symbol}")

    digits = symbol_info.digits
    new_sl = round(req.sl, digits) if req.sl is not None else position.sl
    new_tp = round(req.tp, digits) if req.tp is not None else position.tp

    request = {
        "action": TRADE_ACTION_SLTP,
        "symbol": position.symbol,
        "position": req.ticket,
        "sl": new_sl,
        "tp": new_tp,
    }

    result = mt5.order_send(request)

    if result is None or result.retcode != getattr(mt5, 'TRADE_RETCODE_DONE', 10009):
        retcode = result.retcode if result else "None"
        comment = result.comment if result else "No response"
        raise HTTPException(status_code=400, detail=f"Modify failed: retcode={retcode}, comment={comment}")

    print(f"✅ Position modified: Ticket {req.ticket} | SL: {new_sl} | TP: {new_tp}")

    return {
        "success": True,
        "ticket": req.ticket,
        "sl": new_sl,
        "tp": new_tp,
        "comment": result.comment,
    }


@app.get("/orders/open")
def get_open_orders(token: Annotated[str, Depends(verify_token)]):
    """List all open positions with real-time P&L."""
    if not provider.initialized:
        raise HTTPException(status_code=400, detail="MT5 not initialized")

    positions = mt5.positions_get()
    if positions is None:
        return {"success": True, "count": 0, "positions": []}

    position_list = []
    for pos in positions:
        position_list.append({
            "ticket": pos.ticket,
            "symbol": pos.symbol,
            "direction": "BUY" if pos.type == mt5.POSITION_TYPE_BUY else "SELL",
            "volume": pos.volume,
            "entry_price": pos.price_open,
            "current_price": pos.price_current,
            "sl": pos.sl,
            "tp": pos.tp,
            "profit": pos.profit,
            "swap": pos.swap,
            "commission": pos.commission,
            "magic": pos.magic,
            "comment": pos.comment,
            "time": pos.time.strftime("%Y-%m-%d %H:%M:%S") if hasattr(pos.time, 'strftime') else str(pos.time),
        })

    return {
        "success": True,
        "count": len(position_list),
        "positions": position_list,
    }


@app.get("/account/info")
def get_account_info(token: Annotated[str, Depends(verify_token)]):
    """Get full account details: balance, equity, margin, free margin, margin level."""
    if not provider.initialized:
        raise HTTPException(status_code=400, detail="MT5 not initialized")

    acc = mt5.account_info()
    if acc is None:
        raise HTTPException(status_code=500, detail="Cannot retrieve account info")

    margin_level = (acc.equity / acc.margin * 100) if acc.margin > 0 else 0

    return {
        "success": True,
        "login": acc.login,
        "server": acc.server,
        "name": acc.name,
        "balance": acc.balance,
        "equity": acc.equity,
        "margin": acc.margin,
        "free_margin": acc.margin_free,
        "margin_level": round(margin_level, 2),
        "profit": acc.profit,
        "currency": acc.currency,
        "leverage": acc.leverage,
        "trade_mode": acc.trade_mode,
    }


@app.get("/symbol/info/{symbol}")
def get_symbol_info_endpoint(symbol: str, token: Annotated[str, Depends(verify_token)]):
    """Get detailed symbol info for lot size calculation (point, digits, contract size, tick value)."""
    if not provider.initialized:
        raise HTTPException(status_code=400, detail="MT5 not initialized")

    resolved = provider.resolve_symbol_name(symbol)
    info = mt5.symbol_info(resolved)
    if info is None:
        raise HTTPException(status_code=404, detail=f"Symbol {symbol} not found")

    tick = mt5.symbol_info_tick(resolved)

    return {
        "success": True,
        "symbol": resolved,
        "point": info.point,
        "digits": info.digits,
        "trade_contract_size": info.trade_contract_size,
        "volume_min": info.volume_min,
        "volume_max": info.volume_max,
        "volume_step": info.volume_step,
        "tick_value": info.trade_tick_value,
        "tick_size": info.trade_tick_size,
        "spread": info.spread,
        "bid": tick.bid if tick else None,
        "ask": tick.ask if tick else None,
    }


@app.get("/positions/summary")
def get_positions_summary(token: Annotated[str, Depends(verify_token)]):
    """Lightweight endpoint for fast Trade Manager refresh (1s interval)."""
    if not provider.initialized:
        raise HTTPException(status_code=400, detail="MT5 not initialized")

    acc = mt5.account_info()
    if acc is None:
        raise HTTPException(status_code=500, detail="Cannot retrieve account info")

    positions = mt5.positions_get()
    position_list = []
    total_profit = 0.0

    if positions:
        for pos in positions:
            position_list.append({
                "ticket": pos.ticket,
                "symbol": pos.symbol,
                "direction": "BUY" if pos.type == mt5.POSITION_TYPE_BUY else "SELL",
                "volume": pos.volume,
                "entry_price": pos.price_open,
                "current_price": pos.price_current,
                "sl": pos.sl,
                "tp": pos.tp,
                "profit": pos.profit,
            })
            total_profit += pos.profit

    margin_level = (acc.equity / acc.margin * 100) if acc.margin > 0 else 0

    return {
        "success": True,
        "balance": acc.balance,
        "equity": acc.equity,
        "margin": acc.margin,
        "free_margin": acc.margin_free,
        "margin_level": round(margin_level, 2),
        "open_count": len(position_list),
        "total_profit": round(total_profit, 2),
        "positions": position_list,
    }


@app.get("/trades/history")
def get_trade_history(token: Annotated[str, Depends(verify_token)], hours: int = 0):
    """Get closed trade history from MT5."""
    if not provider.initialized:
        raise HTTPException(status_code=400, detail="MT5 not initialized")

    from datetime import datetime, timedelta

    # Remove timezone issues by getting extreme dates. 0 hours = ALL history.
    if hours > 0:
        from_time = datetime.now() - timedelta(hours=hours)
    else:
        # Use Year 2000 instead of 1970 to prevent Windows OSError (Errno 22) in MT5
        from_time = datetime(2000, 1, 1)

    to_time = datetime.now() + timedelta(days=5) # Safe future buffer

    deals = mt5.history_deals_get(from_time, to_time)
    if deals is None:
        return {"success": True, "count": 0, "deals": []}

    # 1. First Pass: Map Position IDs to their original Opening Comment
    position_comments = {}
    for d in deals:
        if d.entry == 0 and d.comment:  # DEAL_ENTRY_IN (OPEN)
            position_comments[d.position_id] = d.comment

    deal_list = []
    for deal in deals:
        # Deal Entry types: 0=OPEN, 1=CLOSE, 2=INOUT, 3=CLOSE_BY, 4=STATE
        # We only want to show closed positions in history (where PNL is realized)
        if deal.entry == 0 or deal.entry >= 4:
            continue
            
        entry_label = {0: "OPEN", 1: "CLOSE", 2: "INOUT", 3: "CLOSE_BY"}.get(deal.entry, f"UNKNOWN({deal.entry})")

        # Use utcfromtimestamp to prevent Python from shifting the broker time to your local timezone
        broker_time = datetime.utcfromtimestamp(deal.time).strftime("%Y-%m-%d %H:%M:%S")

        # 2. Inherit comment: If closing deal has no comment (or only SL/TP tag), pull from original position
        final_comment = deal.comment if deal.comment else ""
        orig_comment = position_comments.get(deal.position_id, "")
        
        if not final_comment:
            final_comment = orig_comment
        elif final_comment.lower() in ["[tp]", "tp", "[sl]", "sl"] and orig_comment:
            final_comment = f"{orig_comment} {final_comment}"

        deal_list.append({
            "ticket": deal.order,
            "symbol": deal.symbol,
            "direction": "BUY" if deal.type == getattr(mt5, 'DEAL_TYPE_BUY', 0) else "SELL",
            "volume": deal.volume,
            "price": deal.price,
            "profit": deal.profit,
            "swap": deal.swap,
            "commission": deal.commission,
            "comment": final_comment,
            "time": broker_time,
            "entry": entry_label,
            "deal_type": deal.type,
        })

    return {
        "success": True,
        "count": len(deal_list),
        "deals": deal_list,
    }


@app.post("/shutdown")
def shutdown_mt5(token: Annotated[str, Depends(verify_token)]):
    """Shutdown MT5 connection"""
    provider.shutdown()
    return {"success": True, "message": "MT5 connection closed"}

# ============================================================================
# Entry Point
# ============================================================================
if __name__ == '__main__':
    # Initial attempt to connect MT5 with startup path
    print("\n" + "=" * 60)
    print("  MT5 Data Server — Interactive + Secure Mode")
    print("=" * 60)
    
    if provider.initialize_mt5(STARTUP_PATH):
        print(f"✅ Auto-Connected to MT5 Terminal")
        acc = mt5.account_info()
        if acc: print(f"   Account: {acc.login} | Server: {acc.server}")
    else:
        print(f"⚠️  Manual MT5 initialization required (Call /initialize via API)")

    print(f"\n🚀 API Server starting on http://{SERVER_IP}:{PORT}")
    print(f"🔑 Security Token ACTIVE: {MT5_API_TOKEN}")
    print(f"📜 Docs (Swagger UI): http://{SERVER_IP}:{PORT}/docs")
    print("=" * 60 + "\n")

    # Clean Port Disposal Handler
    def signal_handler(sig, frame):
        print("\n🛑 Shutting down server and releasing port...")
        provider.shutdown()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)

    uvicorn.run(app, host="0.0.0.0", port=PORT)
