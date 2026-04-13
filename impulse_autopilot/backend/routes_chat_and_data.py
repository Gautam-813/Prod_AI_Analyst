"""
History & Live Mode Endpoints
Handles file uploads, AI chat with code execution, live market data, trade execution,
HuggingFace sync, Yahoo Finance, Web Intel search, and more
"""

import os
import io
import json
import re
import time
import pandas as pd
import numpy as np
from datetime import datetime, timezone
from typing import Optional, Dict, List
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from openai import OpenAI
from pydantic import BaseModel

from database import SessionLocal, get_db
from models import AutopilotConfig
from schemas import (
    AIChatRequest, AIChatResponse,
    CodeExecuteRequest, CodeExecuteResponse,
    FileUploadResponse, DataPreviewResponse,
    MT5ConnectRequest, MT5ConnectResponse,
    CandleRequest, CandleResponse,
    SymbolInfoRequest, SymbolInfoResponse,
    TradeOrderRequest, TradeOrderResponse,
    ClosePositionRequest, PositionResponse
)
from sandbox import CodeSandbox, TradeSetupDetector
from mt5_client import MT5Client
from ai_analyzer import AIAnalyzer
from data_sync import (
    ping_mt5_server, pull_mt5_latest,
    sync_hf_data, push_to_hf, sync_symbol,
    fetch_yahoo_data, sync_yahoo_symbol,
    run_web_search, get_market_news, analyze_sentiment,
    auto_sync_all
)
from dotenv import load_dotenv

load_dotenv()

router = APIRouter()

# ===== Global State =====
# Store uploaded DataFrames in memory (keyed by data_id)
history_datastore: Dict[str, pd.DataFrame] = {}

# Store conversation histories
conversations: Dict[str, List[Dict]] = {}

# Store MT5 connections (keyed by session/user)
mt5_connections: Dict[str, MT5Client] = {}

# Store live data
live_datastore: Dict[str, pd.DataFrame] = {}


# ===== Helper Functions =====
def get_db_session():
    """Get database session"""
    db = SessionLocal()
    try:
        return db
    finally:
        db.close()


def get_ai_config(db: Session) -> Optional[AutopilotConfig]:
    """Get current AI configuration"""
    return db.query(AutopilotConfig).first()


# ===== HISTORY MODE ENDPOINTS =====

@router.post("/history/upload", response_model=FileUploadResponse)
async def upload_history_file(file: UploadFile = File(...)):
    """Upload a CSV or Parquet file for historical analysis"""
    try:
        content = await file.read()
        filename = file.filename

        # Parse file based on extension
        if filename.endswith('.parquet'):
            df = pd.read_parquet(io.BytesIO(content))
        elif filename.endswith('.csv'):
            df = pd.read_csv(io.BytesIO(content), dtype=str, low_memory=False)

            # Convert numeric columns
            numeric_cols = [
                'cross_price', 'segment_index', 'segment_price',
                'segment_size_price', 'segment_move_points',
                'segment_move_percent', 'sequence_extreme_price', 'is_final',
                'DifferencePoints', 'DifferencePercent', 'MovingAveragePeriod',
                'CrossoverStartPrice', 'CrossoverEndPrice', 'AbsolutePeakPrice',
                'ImpulsePeakPrice', 'ReversalPrice', 'MA_At_AbsolutePeak',
                'MA_At_ImpulsePeak', 'MA_At_Reversal', 'DeepestRetracePrice',
                'MA_At_DeepestRetrace', 'open', 'high', 'low', 'close', 'volume'
            ]

            for col in numeric_cols:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')

            # Convert time columns
            time_cols = ['time', 'cross_time', 'cross_end_time', 'segment_time']
            for col in time_cols:
                if col in df.columns:
                    df[col] = pd.to_datetime(df[col], errors='coerce', utc=False)
        else:
            raise HTTPException(status_code=400, detail="Only .csv and .parquet files are supported")

        # Generate data_id
        data_id = f"history_{int(time.time())}_{filename}"
        history_datastore[data_id] = df

        # Prepare response
        preview = df.head(10).to_dict(orient='records')
        dtypes = {col: str(dtype) for col, dtype in df.dtypes.items()}

        return FileUploadResponse(
            success=True,
            filename=filename,
            rows=len(df),
            columns=len(df.columns),
            column_names=list(df.columns),
            dtypes=dtypes,
            preview=preview,
            message=f"Successfully loaded {len(df):,} rows with {len(df.columns)} columns"
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"File upload failed: {str(e)}")


@router.get("/history/data/{data_id}", response_model=DataPreviewResponse)
async def get_history_data(data_id: str, limit: int = 20, offset: int = 0):
    """Get preview of uploaded historical data"""
    if data_id not in history_datastore:
        raise HTTPException(status_code=404, detail="Data not found")

    df = history_datastore[data_id]
    data_slice = df.iloc[offset:offset+limit]

    # Convert to serializable format
    records = []
    for _, row in data_slice.iterrows():
        record = {}
        for col, val in row.items():
            if pd.isna(val):
                record[col] = None
            elif isinstance(val, (pd.Timestamp, datetime)):
                record[col] = val.isoformat()
            elif isinstance(val, (np.integer,)):
                record[col] = int(val)
            elif isinstance(val, (np.floating,)):
                record[col] = float(val)
            else:
                record[col] = val
        records.append(record)

    return DataPreviewResponse(
        data_id=data_id,
        rows=len(df),
        columns=len(df.columns),
        data=records,
        column_names=list(df.columns)
    )


@router.get("/history/datasets")
async def list_history_datasets():
    """List all uploaded datasets"""
    datasets = []
    for data_id, df in history_datastore.items():
        datasets.append({
            "data_id": data_id,
            "filename": data_id.split('_', 2)[-1] if '_' in data_id else "unknown",
            "rows": len(df),
            "columns": len(df.columns),
            "upload_time": data_id.split('_')[1] if '_' in data_id else "unknown"
        })
    return {"datasets": datasets}


@router.delete("/history/data/{data_id}")
async def delete_history_dataset(data_id: str):
    """Delete an uploaded dataset"""
    if data_id in history_datastore:
        del history_datastore[data_id]
        if data_id in conversations:
            del conversations[data_id]
        return {"success": True, "message": f"Dataset {data_id} deleted"}
    raise HTTPException(status_code=404, detail="Dataset not found")


# ===== LIVE MODE ENDPOINTS =====

@router.post("/live/connect", response_model=MT5ConnectResponse)
async def connect_mt5(request: MT5ConnectRequest):
    """Test and establish MT5 connection"""
    try:
        client = MT5Client(base_url=request.url, token=request.token)
        is_connected = client.test_connection()

        if is_connected:
            # Store connection
            mt5_connections["default"] = client

            # Try to get account info
            account_info = None
            try:
                account_info = client._get("account/info")
            except:
                pass

            return MT5ConnectResponse(
                success=True,
                mt5_initialized=True,
                message="MT5 connection established",
                account_info=account_info
            )
        else:
            return MT5ConnectResponse(
                success=False,
                mt5_initialized=False,
                message="MT5 server not responding or not initialized"
            )

    except Exception as e:
        return MT5ConnectResponse(
            success=False,
            mt5_initialized=False,
            message=f"Connection failed: {str(e)}"
        )


@router.post("/live/candles", response_model=CandleResponse)
async def get_live_candles(request: CandleRequest):
    """Fetch live candlestick data from MT5"""
    if "default" not in mt5_connections:
        raise HTTPException(status_code=400, detail="MT5 not connected. Please connect first.")

    try:
        client = mt5_connections["default"]
        df = client.get_candles(
            symbol=request.symbol,
            timeframe=request.timeframe,
            count=request.count
        )

        if df.empty:
            return CandleResponse(
                success=False,
                symbol=request.symbol,
                timeframe=request.timeframe,
                count=0,
                data=[],
                message="No data available"
            )

        # Convert to list of dicts
        candles = []
        for _, row in df.iterrows():
            candle = {}
            for col, val in row.items():
                if pd.isna(val):
                    candle[col] = None
                elif isinstance(val, (pd.Timestamp, datetime)):
                    candle[col] = val.isoformat()
                elif isinstance(val, (np.integer,)):
                    candle[col] = int(val)
                elif isinstance(val, (np.floating,)):
                    candle[col] = float(val)
                else:
                    candle[col] = val
            candles.append(candle)

        # Store in live datastore
        data_id = f"live_{request.symbol}_{request.timeframe}"
        live_datastore[data_id] = df

        return CandleResponse(
            success=True,
            symbol=request.symbol,
            timeframe=request.timeframe,
            count=len(candles),
            data=candles,
            message=f"Loaded {len(candles)} candles for {request.symbol}"
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch candles: {str(e)}")


@router.get("/live/symbol/{symbol}", response_model=SymbolInfoResponse)
async def get_symbol_info(symbol: str):
    """Get current symbol information (ask, bid, spread, etc.)"""
    if "default" not in mt5_connections:
        raise HTTPException(status_code=400, detail="MT5 not connected")

    try:
        client = mt5_connections["default"]
        info = client.get_symbol_info(symbol)

        return SymbolInfoResponse(
            success=True,
            symbol=symbol,
            ask=info.get("ask"),
            bid=info.get("bid"),
            spread=info.get("spread"),
            point=info.get("point"),
            digits=info.get("digits"),
            message="Symbol info retrieved"
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get symbol info: {str(e)}")


@router.get("/live/positions", response_model=PositionResponse)
async def get_open_positions():
    """Get all open positions"""
    if "default" not in mt5_connections:
        raise HTTPException(status_code=400, detail="MT5 not connected")

    try:
        client = mt5_connections["default"]
        positions_data = client.get_positions()

        return PositionResponse(
            success=True,
            positions=positions_data.get("positions", []),
            balance=positions_data.get("balance"),
            equity=positions_data.get("equity"),
            margin_level=positions_data.get("margin_level"),
            open_count=positions_data.get("open_count", 0),
            message="Positions retrieved"
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get positions: {str(e)}")


@router.post("/live/order/place", response_model=TradeOrderResponse)
async def place_trade_order(request: TradeOrderRequest):
    """Place a trade order (market or pending)"""
    if "default" not in mt5_connections:
        raise HTTPException(status_code=400, detail="MT5 not connected")

    try:
        client = mt5_connections["default"]
        result = client.place_order(
            symbol=request.symbol,
            action=request.action,
            volume=request.volume,
            sl=request.sl,
            tp=request.tp,
            price=request.price,
            magic=request.magic,
            comment=request.comment
        )

        return TradeOrderResponse(
            success=True,
            ticket=result.get("ticket"),
            message=f"Order placed successfully",
            order_info=result
        )

    except Exception as e:
        return TradeOrderResponse(
            success=False,
            message=f"Order failed: {str(e)}"
        )


@router.post("/live/order/close", response_model=TradeOrderResponse)
async def close_position(request: ClosePositionRequest):
    """Close an open position"""
    if "default" not in mt5_connections:
        raise HTTPException(status_code=400, detail="MT5 not connected")

    try:
        client = mt5_connections["default"]
        result = client.close_position(
            ticket=request.ticket,
            volume=request.volume
        )

        return TradeOrderResponse(
            success=True,
            message=f"Position #{request.ticket} closed",
            order_info=result
        )

    except Exception as e:
        return TradeOrderResponse(
            success=False,
            message=f"Close failed: {str(e)}"
        )


@router.post("/live/order/modify", response_model=TradeOrderResponse)
async def modify_position(ticket: int, sl: Optional[float] = None, tp: Optional[float] = None):
    """Modify SL/TP of open position"""
    if "default" not in mt5_connections:
        raise HTTPException(status_code=400, detail="MT5 not connected")

    try:
        client = mt5_connections["default"]
        result = client.modify_position(
            ticket=ticket,
            sl=sl,
            tp=tp
        )

        return TradeOrderResponse(
            success=True,
            message=f"Position #{ticket} modified",
            order_info=result
        )

    except Exception as e:
        return TradeOrderResponse(
            success=False,
            message=f"Modify failed: {str(e)}"
        )


# ===== AI CHAT WITH CODE EXECUTION =====

@router.post("/ai/chat", response_model=AIChatResponse)
async def ai_chat_with_code_execution(request: AIChatRequest):
    """
    AI chat with automatic Python code execution
    AI can output Python code blocks that get executed in sandbox
    """
    db = get_db_session()
    config = get_ai_config(db)

    if not config:
        raise HTTPException(status_code=404, detail="No AI configuration found")

    # Get or create conversation
    conv_id = request.conversation_id
    if conv_id not in conversations:
        conversations[conv_id] = []

    conversation = conversations[conv_id]

    # Determine which DataFrame to use
    if conv_id == "history":
        # Use most recent history dataset
        if not history_datastore:
            raise HTTPException(status_code=400, detail="No historical data uploaded")
        data_id = list(history_datastore.keys())[-1]
        df = history_datastore[data_id]
    elif conv_id == "live":
        # Fetch live data
        if not mt5_connections:
            raise HTTPException(status_code=400, detail="MT5 not connected")
        symbol = request.symbol or "XAUUSD"
        timeframe = request.timeframe or "1m"

        try:
            client = mt5_connections["default"]
            df = client.get_candles(symbol=symbol, timeframe=timeframe, count=1000)
            if df.empty:
                raise HTTPException(status_code=400, detail=f"No live data for {symbol}")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to fetch live data: {str(e)}")
    else:
        raise HTTPException(status_code=400, detail=f"Unknown conversation type: {conv_id}")

    # Build system prompt
    df_info = io.StringIO()
    df.info(buf=df_info)
    metadata = df_info.getvalue()

    system_prompt = f"""
You are a Lead Quant Analyst in 2026. Use the provided DataFrame 'df' for your analysis.

SCHEMA: {metadata}
LATEST_CANDLE_RECORDED: {df['time'].iloc[-1] if not df.empty and 'time' in df.columns else 'N/A'}
SAMPLES (Last 5 Rows): {df.tail(5).to_string()}

RULES (STRICT):
1. Analyze only based on the provided data available in 'df'. Ignore local system time.
2. Provide executable Python code in ```python blocks.
3. Use 'st.write()', 'st.plotly_chart()' for results.
4. If you identify a trade opportunity, output a JSON block in ```json format:
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

    # Add user message
    conversation.append({"role": "user", "content": request.message})

    # Prepare API key
    final_key = config.api_key
    if config.ai_provider == "NVIDIA" and not final_key.startswith("nvapi-"):
        final_key = f"nvapi-{final_key}"

    # Call AI
    try:
        base_url = config.base_url
        client = OpenAI(base_url=base_url, api_key=final_key)

        messages = [{"role": "system", "content": system_prompt}] + conversation[-20:]  # Last 20 messages

        response = client.chat.completions.create(
            model=config.model_name,
            messages=messages,
            temperature=0.2,
            stream=False
        )

        ai_text = response.choices[0].message.content

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI API error: {str(e)}")

    # Execute any Python code blocks WITH SELF-HEALING RETRY
    code_pattern = r"```python(.*?)```"
    code_blocks = re.findall(code_pattern, ai_text, re.S | re.I)

    sandbox = CodeSandbox(df)
    all_code = "\n\n".join([b.strip() for b in code_blocks]) if code_blocks else None
    code_output = None
    code_error = None
    plots = []
    figures = []
    retry_count = 0
    max_retries = 2

    if all_code:
        # First execution attempt
        exec_result = sandbox.execute(all_code)
        code_output = exec_result.get("stdout")
        code_error = exec_result.get("error")
        plots = exec_result.get("plots", [])
        figures = exec_result.get("figures", [])

        # Self-Healing: If code fails, ask AI to fix it
        if code_error and retry_count < max_retries:
            print(f"⚠️ Code execution failed, attempting self-heal (attempt 1/{max_retries})...")
            
            # Send error back to AI for fixing
            fix_prompt = f"""
Your previous Python code failed with this error:
ERROR: {code_error}

YOUR ORIGINAL CODE:
```python
{all_code}
```

Please fix the code and provide a corrected version. Make sure it works with this DataFrame schema:
{metadata}

Only output the fixed Python code in ```python blocks. Do not include explanations.
"""
            try:
                fix_messages = conversation[-5:] + [
                    {"role": "user", "content": fix_prompt}
                ]
                
                fix_response = client.chat.completions.create(
                    model=config.model_name,
                    messages=[{"role": "system", "content": "You are a Python expert. Fix the code to work correctly."}] + fix_messages,
                    temperature=0.2,
                    stream=False
                )
                
                fix_text = fix_response.choices[0].message.content
                
                # Extract and execute fixed code
                fix_code_blocks = re.findall(code_pattern, fix_text, re.S | re.I)
                if fix_code_blocks:
                    fixed_code = "\n\n".join([b.strip() for b in fix_code_blocks])
                    
                    # Create new sandbox to reset state
                    sandbox = CodeSandbox(df)
                    fix_result = sandbox.execute(fixed_code)
                    
                    # Update outputs with fixed results
                    code_output = fix_result.get("stdout")
                    code_error = fix_result.get("error")  # May still fail
                    plots = fix_result.get("plots", [])
                    figures = fix_result.get("figures", [])
                    
                    if code_error:
                        print(f"❌ Self-heal attempt 1 also failed: {code_error}")
                    else:
                        print(f"✅ Self-heal successful!")
                        # Append fix to conversation for context
                        conversation.append({"role": "assistant", "content": fix_text})
                    
                    retry_count += 1
                    
            except Exception as e:
                print(f"❌ Self-heal AI call failed: {e}")

    # Detect trade setups/actions
    trade_setup = TradeSetupDetector.detect_trade_setup(ai_text)
    trade_action = TradeSetupDetector.detect_trade_action(ai_text)

    # Store assistant response
    msg_to_store = {"role": "assistant", "content": ai_text}
    if all_code:
        msg_to_store["code"] = all_code
    if code_output:
        msg_to_store["exec_result"] = code_output
    if trade_setup:
        msg_to_store["detected_setup"] = trade_setup
    if trade_action:
        msg_to_store["detected_action"] = trade_action

    conversation.append(msg_to_store)

    return AIChatResponse(
        success=True,
        ai_text=ai_text,
        code_executed=bool(all_code),
        code_output=code_output,
        code_error=code_error,
        plots=plots,
        figures=figures,
        trade_setup=trade_setup,
        trade_action=trade_action,
        conversation_history=conversation[-10:],  # Last 10 messages
        self_heal_attempts=retry_count  # How many times code was retried
    )


@router.post("/ai/chat/reset")
async def reset_conversation(conversation_id: str = "default"):
    """Reset conversation history"""
    if conversation_id in conversations:
        del conversations[conversation_id]
    return {"success": True, "message": f"Conversation {conversation_id} reset"}


@router.get("/ai/chat/history/{conversation_id}")
async def get_conversation_history(conversation_id: str):
    """Get conversation history"""
    if conversation_id in conversations:
        return {"conversation": conversations[conversation_id]}
    return {"conversation": []}


# ===== DEFAULT CONFIG ENDPOINTS =====

@router.get("/config/default-keys")
async def get_default_api_keys():
    """
    Get default API keys from .env file
    Allows users to use pre-configured keys without manual entry
    """
    keys = {
        "nvidia_api_key": os.getenv("NVIDIA_API_KEY", ""),
        "gemini_api_key": os.getenv("GEMINI_API_KEY", ""),
        "groq_api_key": os.getenv("GROQ_API_KEY", ""),
        "open_router_api_key": os.getenv("OPEN_ROUTER_API_KEY", ""),
        "bytez_api_key": os.getenv("Bytez", ""),
        "cerebras_api_key": os.getenv("CEREBRAS_API_KEY", ""),
        "huggingface_api_key": os.getenv("HuggingFace_API_KEY", ""),
        "mt5_url": os.getenv("MT5_URL", "http://localhost:5000"),
        "mt5_token": os.getenv("MT5_TOKEN", "impulse_secure_2026"),
        "default_provider": os.getenv("AI_PROVIDER", "NVIDIA"),
        "default_model": os.getenv("MODEL_NAME", "qwen/qwen3.5-122b-a10b")
    }

    return {
        "success": True,
        "keys": keys,
        "message": "Default keys loaded from .env file"
    }


# ===== HUGGINGFACE & DATA SYNC ENDPOINTS =====

@router.post("/data/sync/mt5")
async def sync_from_mt5(
    symbol: str = "XAUUSD",
    timeframe: str = "1m",
    count: int = 1000,
    push_to_hf: bool = False
):
    """Pull latest data from MT5 and optionally sync to HuggingFace"""
    db = get_db_session()
    config = db.query(AutopilotConfig).first()

    if not config:
        raise HTTPException(status_code=404, detail="No configuration found")

    # Get HF credentials
    hf_repo = os.getenv("HF_REPO_ID", "")
    hf_token = os.getenv("HUGGINGFACE_API_KEY", "")

    try:
        # Pull from MT5
        df = pull_mt5_latest(config.mt5_url, symbol, timeframe, count, config.mt5_token)

        if df.empty:
            return {"success": False, "message": "No data from MT5"}

        # Optionally push to HuggingFace
        if push_to_hf and hf_repo and hf_token:
            push_to_hf(hf_repo, hf_token, df, symbol)

        # Store in history datastore
        data_id = f"sync_{symbol}_{int(time.time())}"
        history_datastore[data_id] = df

        return {
            "success": True,
            "data_id": data_id,
            "rows": len(df),
            "columns": len(df.columns),
            "message": f"Synced {len(df)} candles for {symbol}"
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"MT5 sync failed: {str(e)}")


@router.post("/data/sync/huggingface")
async def sync_huggingface_data(symbol: str = "XAUUSD"):
    """Pull data from HuggingFace Hub"""
    hf_repo = os.getenv("HF_REPO_ID", "")
    hf_token = os.getenv("HUGGINGFACE_API_KEY", "")

    if not hf_repo or not hf_token:
        raise HTTPException(status_code=400, detail="HuggingFace credentials not configured")

    try:
        df = sync_hf_data(hf_repo, hf_token, symbol)

        if df is None or df.empty:
            return {"success": False, "message": f"No data found on HuggingFace for {symbol}"}

        # Store in history datastore
        data_id = f"hf_{symbol}_{int(time.time())}"
        history_datastore[data_id] = df

        return {
            "success": True,
            "data_id": data_id,
            "rows": len(df),
            "columns": len(df.columns),
            "message": f"Loaded {len(df)} rows from HuggingFace"
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"HuggingFace sync failed: {str(e)}")


@router.post("/data/sync/auto")
async def auto_sync_mt5_data(symbols: List[str] = ["XAUUSD", "EURUSD"]):
    """Auto-sync multiple symbols from MT5 to HuggingFace"""
    db = get_db_session()
    config = db.query(AutopilotConfig).first()

    if not config:
        raise HTTPException(status_code=404, detail="No configuration found")

    hf_repo = os.getenv("HF_REPO_ID", "")
    hf_token = os.getenv("HUGGINGFACE_API_KEY", "")

    try:
        results = auto_sync_all(
            hf_repo=hf_repo,
            symbols=symbols,
            hf_token=hf_token,
            mt5_url=config.mt5_url,
            mt5_token=config.mt5_token
        )

        return {
            "success": True,
            "results": results,
            "message": f"Auto-synced {len(symbols)} symbols"
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Auto-sync failed: {str(e)}")


# ===== YAHOO FINANCE ENDPOINTS =====

@router.post("/data/yahoo/fetch")
async def fetch_yahoo_finance_data(
    symbol: str,
    period: str = "1y",
    interval: str = "1d",
    archive_to_hf: bool = False
):
    """Fetch data from Yahoo Finance and optionally archive to HuggingFace"""
    hf_repo = os.getenv("HF_REPO_ID", "")
    hf_token = os.getenv("HUGGINGFACE_API_KEY", "")

    try:
        df, stats = sync_yahoo_symbol(hf_repo if archive_to_hf else "", symbol, hf_token if archive_to_hf else "", period, interval)

        # Store in history datastore
        data_id = f"yahoo_{symbol}_{int(time.time())}"
        history_datastore[data_id] = df

        return {
            "success": True,
            "data_id": data_id,
            "rows": len(df),
            "columns": len(df.columns),
            "stats": stats,
            "archived_to_hf": archive_to_hf,
            "message": f"Fetched {len(df)} rows for {symbol}"
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Yahoo Finance fetch failed: {str(e)}")


# ===== WEB INTEL SEARCH ENDPOINTS =====

class WebSearchRequest(BaseModel):
    query: str
    max_results: int = 5
    search_type: str = "general"  # "general" or "news"

class WebSearchResponse(BaseModel):
    success: bool
    results: List[Dict]
    sentiment: Optional[str] = None
    message: str

@router.post("/data/web/search", response_model=WebSearchResponse)
async def web_intel_search(request: WebSearchRequest):
    """Search the web for market intel, news, and sentiment"""
    try:
        if request.search_type == "news":
            results = get_market_news(request.query, request.max_results)
        else:
            results = run_web_search(request.query, request.max_results)

        if not results:
            return WebSearchResponse(
                success=False,
                results=[],
                sentiment=None,
                message="No results found"
            )

        # Analyze sentiment
        sentiment = analyze_sentiment(results)

        return WebSearchResponse(
            success=True,
            results=results,
            sentiment=sentiment,
            message=f"Found {len(results)} results"
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Web search failed: {str(e)}")


# ===== DATA SOURCE MANAGEMENT =====

@router.get("/data/sources")
async def list_data_sources():
    """List all available data sources"""
    sources = {
        "history_uploads": [
            {
                "data_id": data_id,
                "rows": len(df),
                "columns": len(df.columns)
            }
            for data_id, df in history_datastore.items()
        ],
        "live_data": list(live_datastore.keys()),
        "mt5_connected": len(mt5_connections) > 0
    }
    return sources


@router.post("/data/switch/{data_id}")
async def switch_active_dataset(data_id: str):
    """Switch active dataset for AI analysis"""
    if data_id not in history_datastore:
        raise HTTPException(status_code=404, detail=f"Dataset {data_id} not found")

    # Store active dataset reference
    history_datastore["_active"] = history_datastore[data_id]

    return {
        "success": True,
        "message": f"Switched to dataset {data_id}",
        "rows": len(history_datastore[data_id]),
        "columns": len(history_datastore[data_id].columns)
    }
