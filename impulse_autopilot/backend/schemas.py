"""
Pydantic Schemas for API Request/Response Validation
"""

from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, Dict, List
from datetime import datetime


# ===== Autopilot Control =====
class AutopilotStartResponse(BaseModel):
    success: bool
    message: str
    interval_seconds: Optional[int] = None
    next_run: Optional[str] = None

class AutopilotStopResponse(BaseModel):
    success: bool
    message: str

class AutopilotStatusResponse(BaseModel):
    enabled: bool
    scheduler_running: bool
    job_scheduled: bool
    interval_seconds: int
    interval_minutes: float
    next_run: Optional[str] = None
    last_run: Optional[str] = None
    success_count: int
    error_count: int
    lot_size: float
    symbol: str

class AutopilotConfigUpdate(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    
    interval_seconds: Optional[int] = None
    lot_size: Optional[float] = None
    ai_provider: Optional[str] = None
    api_key: Optional[str] = None
    model_name: Optional[str] = None
    base_url: Optional[str] = None
    mt5_url: Optional[str] = None
    mt5_token: Optional[str] = None
    symbol: Optional[str] = None
    timeframe: Optional[str] = None
    candle_count: Optional[int] = None

class AutopilotConfigResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    
    id: int
    enabled: bool
    interval_seconds: int
    interval_minutes: float
    lot_size: float
    symbol: str
    timeframe: str
    candle_count: int
    ai_provider: str
    model_name: str
    mt5_url: str
    success_count: int
    error_count: int
    last_run_timestamp: Optional[str] = None
    next_run_timestamp: Optional[str] = None


# ===== Logs =====
class LogResponse(BaseModel):
    id: int
    timestamp: str
    level: str
    message: str
    metadata: Optional[Dict] = None
    prompt_num: Optional[int] = None
    symbol: Optional[str] = None

class LogsResponse(BaseModel):
    logs: List[LogResponse]
    total: int
    limit: int


# ===== Trades =====
class TradeResponse(BaseModel):
    id: int
    ticket: int
    timestamp: str
    symbol: str
    direction: str
    order_type: str
    entry_price: float
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    lot_size: float
    status: str
    close_price: Optional[float] = None
    profit: Optional[float] = None
    close_timestamp: Optional[str] = None
    prompt_num: Optional[int] = None
    reasoning: Optional[str] = None
    execution_time: Optional[float] = None

class TradesResponse(BaseModel):
    trades: List[TradeResponse]
    total: int
    limit: int


# ===== Prompts =====
class PromptResponse(BaseModel):
    id: int
    prompt_num: int
    prompt_text: str
    category: Optional[str] = None
    active: bool
    usage_count: int
    success_rate: float

class PromptsResponse(BaseModel):
    prompts: List[PromptResponse]
    total: int


# ===== Statistics =====
class StatsResponse(BaseModel):
    total_runs: int
    success_count: int
    error_count: int
    success_rate: float
    total_trades: int
    open_positions: int
    closed_positions: int
    total_pnl: Optional[float] = None
    avg_execution_time: Optional[float] = None


# ===== WebSocket Messages =====
class WSLogMessage(BaseModel):
    type: str = "log"
    timestamp: str
    level: str
    message: str
    data: Optional[Dict] = None

class WSStatusMessage(BaseModel):
    type: str = "status_update"
    timestamp: str
    status: Dict


# ===== AI Chat & Code Execution =====
class AIChatRequest(BaseModel):
    """Request for AI chat with code execution"""
    message: str
    conversation_id: str = "default"  # "history" or "live"
    symbol: Optional[str] = None
    timeframe: Optional[str] = None

class AIChatResponse(BaseModel):
    """Response from AI chat"""
    success: bool
    ai_text: str
    code_executed: bool = False
    code_output: Optional[str] = None
    code_error: Optional[str] = None
    plots: List = []  # Base64 encoded images
    figures: List = []  # Plotly JSON configs
    trade_setup: Optional[Dict] = None
    trade_action: Optional[Dict] = None
    conversation_history: List = []
    self_heal_attempts: int = 0  # Number of retry attempts

class CodeExecuteRequest(BaseModel):
    """Direct code execution request"""
    code: str
    data_id: str  # Identifier for which DataFrame to use

class CodeExecuteResponse(BaseModel):
    success: bool
    stdout: Optional[str] = None
    error: Optional[str] = None
    plots: List = []
    figures: List = []


# ===== File Upload (History Mode) =====
class FileUploadResponse(BaseModel):
    success: bool
    filename: str
    rows: int
    columns: int
    column_names: List[str]
    dtypes: Dict[str, str]
    preview: List[Dict]  # First 10 rows as dict
    message: str

class DataPreviewRequest(BaseModel):
    data_id: str
    limit: int = 20
    offset: int = 0

class DataPreviewResponse(BaseModel):
    data_id: str
    rows: int
    columns: int
    data: List[Dict]
    column_names: List[str]


# ===== Live Market Data (Live Mode) =====
class MT5ConnectRequest(BaseModel):
    url: str
    token: str

class MT5ConnectResponse(BaseModel):
    success: bool
    mt5_initialized: bool
    message: str
    account_info: Optional[Dict] = None

class CandleRequest(BaseModel):
    symbol: str
    timeframe: str
    count: int = 500

class CandleResponse(BaseModel):
    success: bool
    symbol: str
    timeframe: str
    count: int
    data: List[Dict]  # OHLCV candles
    message: str

class SymbolInfoRequest(BaseModel):
    symbol: str

class SymbolInfoResponse(BaseModel):
    success: bool
    symbol: str
    ask: Optional[float] = None
    bid: Optional[float] = None
    spread: Optional[float] = None
    point: Optional[float] = None
    digits: Optional[int] = None
    message: str


# ===== Trade Execution =====
class TradeOrderRequest(BaseModel):
    symbol: str
    action: str  # BUY, SELL, BUY_LIMIT, SELL_LIMIT, BUY_STOP, SELL_STOP
    volume: float
    price: Optional[float] = None
    sl: Optional[float] = None
    tp: Optional[float] = None
    magic: int = 123456
    comment: str = "[AUTOPILOT]"

class TradeOrderResponse(BaseModel):
    success: bool
    ticket: Optional[int] = None
    message: str
    order_info: Optional[Dict] = None

class ClosePositionRequest(BaseModel):
    ticket: int
    volume: Optional[float] = None

class PositionResponse(BaseModel):
    success: bool
    positions: List[Dict] = []
    balance: Optional[float] = None
    equity: Optional[float] = None
    margin_level: Optional[float] = None
    open_count: int = 0
    message: str
