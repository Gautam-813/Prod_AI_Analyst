"""
FastAPI Backend for Impulse Autopilot System
Main application entry point
"""

import os
import asyncio
from datetime import datetime, timezone
from typing import List, Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from sqlalchemy import desc, func
from dotenv import load_dotenv

from database import init_db, SessionLocal, get_db
from models import AutopilotLog, TradeRecord, AutopilotConfig, PromptTemplate
from schemas import (
    AutopilotStartResponse, AutopilotStopResponse, AutopilotStatusResponse,
    AutopilotConfigUpdate, AutopilotConfigResponse,
    LogResponse, LogsResponse,
    TradeResponse, TradesResponse,
    PromptResponse, PromptsResponse,
    StatsResponse,
    WSLogMessage, WSStatusMessage
)
from scheduler import scheduler
from ai_analyzer import get_available_providers, get_provider_models, get_provider_base_url
from routes_chat_and_data import router as chat_data_router

# Load environment variables
load_dotenv()

# ===== WebSocket Manager =====
class WebSocketManager:
    """Manages WebSocket connections for real-time log streaming"""
    
    def __init__(self):
        self.active_connections: List[WebSocket] = []
    
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        print(f"🔌 WebSocket connected. Total connections: {len(self.active_connections)}")
    
    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        print(f"🔌 WebSocket disconnected. Total connections: {len(self.active_connections)}")
    
    async def broadcast(self, message: dict):
        """Send message to all connected clients"""
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                print(f"❌ WebSocket send error: {e}")
                disconnected.append(connection)
        
        # Remove disconnected clients
        for conn in disconnected:
            self.disconnect(conn)

# Global WebSocket manager instance
ws_manager = WebSocketManager()


# ===== Lifespan Events =====
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events"""
    # Startup
    print("\n" + "="*60)
    print("🚀 Impulse Autopilot Backend Starting...")
    print("="*60)

    try:
        # Initialize database
        init_db()

        # Start scheduler
        scheduler.start()

        # Load and schedule autopilot if enabled (non-blocking)
        try:
            scheduler.load_and_schedule_autopilot()
        except Exception as e:
            print(f"⚠️ Autopilot scheduling warning: {e}")
            print("ℹ️ This is normal on first run - configure via dashboard")

        print("✅ Backend ready!\n")
    except Exception as e:
        print(f"❌ Fatal startup error: {e}")
        import traceback
        traceback.print_exc()
        raise

    yield

    # Shutdown
    print("\n⏹️ Shutting down backend...")
    scheduler.stop()
    print("✅ Backend stopped")


# ===== FastAPI App =====
app = FastAPI(
    title="Impulse Autopilot API",
    description="AI-powered trading autopilot system with FastAPI backend",
    version="1.0.0",
    lifespan=lifespan
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins (frontend served separately)
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include chat and data routes
app.include_router(chat_data_router, prefix="/api", tags=["Chat & Data"])


# ===== Dependency =====
def get_db_session():
    """FastAPI dependency to provide database session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ===== WebSocket Endpoint =====
@app.websocket("/ws/logs")
async def websocket_logs(websocket: WebSocket):
    """
    WebSocket endpoint for real-time log streaming
    Clients connect here to receive live log updates
    """
    await ws_manager.connect(websocket)
    try:
        while True:
            # Keep connection alive - receive messages (we mainly push, but need to listen)
            data = await websocket.receive_text()
            # Optionally handle client messages here
            if data == "ping":
                await websocket.send_json({"type": "pong", "timestamp": datetime.now(timezone.utc).isoformat()})
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception as e:
        print(f"WebSocket error: {e}")
        ws_manager.disconnect(websocket)


# ===== Autopilot Control Endpoints =====
@app.post("/autopilot/start", response_model=AutopilotStartResponse)
async def start_autopilot(db: Session = Depends(get_db_session)):
    """Start the autopilot scheduler"""
    result = scheduler.enable_autopilot()
    
    if result["success"]:
        # Broadcast status update
        await ws_manager.broadcast({
            "type": "status_update",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": result
        })
        
        return AutopilotStartResponse(
            success=True,
            message=result["message"],
            interval_seconds=result.get("interval_seconds"),
            next_run=result.get("next_run")
        )
    else:
        raise HTTPException(status_code=400, detail=result.get("error", "Failed to start"))

@app.post("/autopilot/stop", response_model=AutopilotStopResponse)
async def stop_autopilot(db: Session = Depends(get_db_session)):
    """Stop the autopilot scheduler"""
    result = scheduler.disable_autopilot()
    
    if result["success"]:
        # Broadcast status update
        await ws_manager.broadcast({
            "type": "status_update",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": result
        })
        
        return AutopilotStopResponse(
            success=True,
            message=result["message"]
        )
    else:
        raise HTTPException(status_code=400, detail=result.get("error", "Failed to stop"))

@app.get("/autopilot/status", response_model=AutopilotStatusResponse)
async def get_autopilot_status(db: Session = Depends(get_db_session)):
    """Get current autopilot status"""
    status = scheduler.get_status()
    
    if "error" in status:
        raise HTTPException(status_code=500, detail=status["error"])
    
    return AutopilotStatusResponse(**status)


# ===== Configuration Endpoints =====
@app.get("/autopilot/config", response_model=AutopilotConfigResponse)
async def get_config(db: Session = Depends(get_db_session)):
    """Get autopilot configuration"""
    config = db.query(AutopilotConfig).first()
    if not config:
        raise HTTPException(status_code=404, detail="No configuration found")
    
    return AutopilotConfigResponse(**config.to_dict())

@app.post("/autopilot/config", response_model=AutopilotConfigResponse)
async def update_config(
    config_update: AutopilotConfigUpdate,
    db: Session = Depends(get_db_session)
):
    """Update autopilot configuration"""
    config = db.query(AutopilotConfig).first()
    if not config:
        raise HTTPException(status_code=404, detail="No configuration found")
    
    # Update fields
    update_data = config_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(config, field, value)
    
    config.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(config)
    
    # If interval changed, reschedule
    if "interval_seconds" in update_data and config.enabled:
        scheduler.load_and_schedule_autopilot()
    
    return AutopilotConfigResponse(**config.to_dict())


# ===== Log Endpoints =====
@app.get("/autopilot/logs", response_model=LogsResponse)
async def get_logs(
    limit: int = 50,
    offset: int = 0,
    level: Optional[str] = None,
    db: Session = Depends(get_db_session)
):
    """Get autopilot logs with optional filtering"""
    query = db.query(AutopilotLog)
    
    if level:
        query = query.filter(AutopilotLog.level == level)
    
    # Get total count
    total = query.count()
    
    # Get paginated logs (newest first)
    logs = query.order_by(desc(AutopilotLog.timestamp)).offset(offset).limit(limit).all()
    
    return LogsResponse(
        logs=[LogResponse(**log.to_dict()) for log in logs],
        total=total,
        limit=limit
    )


# ===== Trade Endpoints =====
@app.get("/trades", response_model=TradesResponse)
async def get_trades(
    limit: int = 50,
    offset: int = 0,
    status: Optional[str] = None,
    symbol: Optional[str] = None,
    db: Session = Depends(get_db_session)
):
    """Get trade history with optional filtering"""
    query = db.query(TradeRecord)
    
    if status:
        query = query.filter(TradeRecord.status == status)
    if symbol:
        query = query.filter(TradeRecord.symbol == symbol)
    
    # Get total count
    total = query.count()
    
    # Get paginated trades (newest first)
    trades = query.order_by(desc(TradeRecord.timestamp)).offset(offset).limit(limit).all()
    
    return TradesResponse(
        trades=[TradeResponse(**trade.to_dict()) for trade in trades],
        total=total,
        limit=limit
    )


# ===== Prompt Endpoints =====
@app.get("/prompts", response_model=PromptsResponse)
async def get_prompts(
    limit: int = 100,
    active_only: bool = True,
    db: Session = Depends(get_db_session)
):
    """Get available prompts"""
    query = db.query(PromptTemplate)
    
    if active_only:
        query = query.filter(PromptTemplate.active == True)
    
    prompts = query.order_by(PromptTemplate.prompt_num).limit(limit).all()
    
    return PromptsResponse(
        prompts=[PromptResponse(**prompt.to_dict()) for prompt in prompts],
        total=len(prompts)
    )


# ===== Statistics Endpoint =====
@app.get("/autopilot/stats", response_model=StatsResponse)
async def get_stats(db: Session = Depends(get_db_session)):
    """Get comprehensive autopilot statistics"""
    config = db.query(AutopilotConfig).first()
    
    if not config:
        raise HTTPException(status_code=404, detail="No configuration found")
    
    # Trade statistics
    total_trades = db.query(func.count(TradeRecord.id)).scalar()
    open_positions = db.query(func.count(TradeRecord.id)).filter(TradeRecord.status == "OPEN").scalar()
    closed_positions = db.query(func.count(TradeRecord.id)).filter(TradeRecord.status != "OPEN").scalar()
    
    # P&L calculation
    total_pnl_result = db.query(func.sum(TradeRecord.profit)).filter(
        TradeRecord.status != "OPEN",
        TradeRecord.profit.isnot(None)
    ).scalar()
    total_pnl = total_pnl_result if total_pnl_result else 0.0
    
    # Average execution time
    avg_time_result = db.query(func.avg(TradeRecord.execution_time)).scalar()
    avg_execution_time = float(avg_time_result) if avg_time_result else None
    
    # Success rate
    total_runs = config.success_count + config.error_count
    success_rate = (config.success_count / total_runs * 100) if total_runs > 0 else 0.0
    
    return StatsResponse(
        total_runs=total_runs,
        success_count=config.success_count,
        error_count=config.error_count,
        success_rate=success_rate,
        total_trades=total_trades,
        open_positions=open_positions,
        closed_positions=closed_positions,
        total_pnl=total_pnl,
        avg_execution_time=avg_execution_time
    )


# ===== Health Check =====
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "scheduler_running": scheduler.is_running
    }


# ===== AI Provider Endpoints =====
@app.get("/ai/providers")
async def get_ai_providers():
    """Get list of available AI providers and their models"""
    providers = get_available_providers()
    result = {}
    
    for provider in providers:
        result[provider] = {
            "models": get_provider_models(provider),
            "base_url": get_provider_base_url(provider) if provider in ["NVIDIA", "Groq", "OpenRouter", "Gemini"] else "Configured"
        }
    
    return {
        "providers": providers,
        "details": result
    }


# ===== Static Files (Frontend) =====
# Serve frontend static files
FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend")

if os.path.exists(FRONTEND_DIR):
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")
    
    @app.get("/")
    async def serve_frontend():
        """Serve the main frontend HTML file"""
        return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))


# ===== Database Session Helper for WebSocket =====
async def broadcast_log_update(log_entry: AutopilotLog):
    """Helper function to broadcast new log entries via WebSocket"""
    try:
        await ws_manager.broadcast({
            "type": "new_log",
            "timestamp": log_entry.timestamp.isoformat(),
            "data": log_entry.to_dict()
        })
    except Exception as e:
        print(f"Error broadcasting log update: {e}")


# Make helper available globally
app.broadcast_log_update = broadcast_log_update


# ===== Main Entry Point =====
if __name__ == "__main__":
    import uvicorn
    
    # Get configuration from .env
    HOST = os.getenv("HOST", "0.0.0.0")
    PORT = int(os.getenv("PORT", "8000"))
    DEBUG = os.getenv("DEBUG", "False").lower() == "true"
    
    print(f"\n🚀 Starting FastAPI server on {HOST}:{PORT}")
    print(f"📝 Debug mode: {DEBUG}\n")
    
    uvicorn.run(
        "main:app",
        host=HOST,
        port=PORT,
        reload=DEBUG,
        log_level="info"
    )
