"""
Database Models for Autopilot System
"""

from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, Text, JSON
from datetime import datetime, timezone
from database import Base


class AutopilotLog(Base):
    """Stores autopilot execution logs"""
    __tablename__ = "autopilot_logs"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
    level = Column(String, nullable=False, index=True)  # INFO, SUCCESS, WARNING, ERROR, CRITICAL
    message = Column(Text, nullable=False)
    metadata_json = Column(JSON)  # Additional structured data
    prompt_num = Column(Integer, index=True)
    symbol = Column(String, index=True)

    def to_dict(self):
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat(),
            "level": self.level,
            "message": self.message,
            "metadata": self.metadata_json,
            "prompt_num": self.prompt_num,
            "symbol": self.symbol
        }


class TradeRecord(Base):
    """Stores executed trades"""
    __tablename__ = "trades"

    id = Column(Integer, primary_key=True, index=True)
    ticket = Column(Integer, unique=True, index=True, nullable=False)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
    symbol = Column(String, nullable=False, index=True)
    direction = Column(String, nullable=False)  # BUY or SELL
    order_type = Column(String, nullable=False)  # BUY_STOP, SELL_LIMIT, etc.
    entry_price = Column(Float, nullable=False)
    stop_loss = Column(Float)
    take_profit = Column(Float)
    lot_size = Column(Float, nullable=False)
    status = Column(String, nullable=False, default="OPEN")  # OPEN, CLOSED, SL_HIT, TP_HIT
    close_price = Column(Float)
    profit = Column(Float)
    close_timestamp = Column(DateTime)
    prompt_num = Column(Integer)
    reasoning = Column(Text)
    execution_time = Column(Float)  # Seconds to execute order

    def to_dict(self):
        return {
            "id": self.id,
            "ticket": self.ticket,
            "timestamp": self.timestamp.isoformat(),
            "symbol": self.symbol,
            "direction": self.direction,
            "order_type": self.order_type,
            "entry_price": self.entry_price,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "lot_size": self.lot_size,
            "status": self.status,
            "close_price": self.close_price,
            "profit": self.profit,
            "close_timestamp": self.close_timestamp.isoformat() if self.close_timestamp else None,
            "prompt_num": self.prompt_num,
            "reasoning": self.reasoning,
            "execution_time": self.execution_time
        }


class AutopilotConfig(Base):
    """Stores autopilot configuration"""
    __tablename__ = "autopilot_config"

    id = Column(Integer, primary_key=True, default=1)
    enabled = Column(Boolean, default=False, nullable=False)
    interval_seconds = Column(Integer, default=300, nullable=False)  # 5 minutes default
    lot_size = Column(Float, default=0.10, nullable=False)
    symbol = Column(String, default="XAUUSD", nullable=False)
    timeframe = Column(String, default="1m", nullable=False)
    candle_count = Column(Integer, default=1000)
    
    # AI Provider settings
    ai_provider = Column(String, default="NVIDIA", nullable=False)
    api_key = Column(String, nullable=False)
    model_name = Column(String, nullable=False)
    base_url = Column(String, nullable=False)
    
    # MT5 settings
    mt5_url = Column(String, default="http://localhost:5000", nullable=False)
    mt5_token = Column(String, nullable=False)
    
    # Statistics
    success_count = Column(Integer, default=0)
    error_count = Column(Integer, default=0)
    last_run_timestamp = Column(DateTime)
    next_run_timestamp = Column(DateTime)
    
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        return {
            "id": self.id,
            "enabled": self.enabled,
            "interval_seconds": self.interval_seconds,
            "interval_minutes": self.interval_seconds / 60,
            "lot_size": self.lot_size,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "candle_count": self.candle_count,
            "ai_provider": self.ai_provider,
            "model_name": self.model_name,
            "mt5_url": self.mt5_url,
            "success_count": self.success_count,
            "error_count": self.error_count,
            "last_run_timestamp": self.last_run_timestamp.isoformat() if self.last_run_timestamp else None,
            "next_run_timestamp": self.next_run_timestamp.isoformat() if self.next_run_timestamp else None,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat()
        }


class PromptTemplate(Base):
    """Stores available prompts"""
    __tablename__ = "prompt_templates"

    id = Column(Integer, primary_key=True, index=True)
    prompt_num = Column(Integer, unique=True, index=True, nullable=False)
    prompt_text = Column(Text, nullable=False)
    category = Column(String, index=True)  # e.g., "resistance", "breakout", "reversal"
    active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    usage_count = Column(Integer, default=0)
    success_rate = Column(Float, default=0.0)

    def to_dict(self):
        return {
            "id": self.id,
            "prompt_num": self.prompt_num,
            "prompt_text": self.prompt_text,
            "category": self.category,
            "active": self.active,
            "usage_count": self.usage_count,
            "success_rate": self.success_rate
        }
