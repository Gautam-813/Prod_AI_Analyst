# 🚀 Impulse Autopilot

**AI-powered trading autopilot system with FastAPI backend and real-time dashboard**

---

## 📋 Overview

Impulse Autopilot is an autonomous trading system that:
- Connects to MT5 data server for real-time market data
- Uses AI providers (NVIDIA, Groq, OpenRouter, Gemini, etc.) to analyze market conditions
- Automatically identifies trade setups based on prompt-driven analysis
- Executes trades with smart order classification (BUY/SELL STOP/LIMIT)
- Provides a real-time dashboard with live logs, statistics, and trade history

**Architecture:** FastAPI (backend) + HTML/CSS/JS (frontend) + SQLite (database) + APScheduler (background tasks)

---

## ✨ Features

- **Multi-Provider AI Support**: NVIDIA, Groq, OpenRouter, OpenRouter (Free), Gemini, GitHub Models, Cerebras, Bytez
- **Dynamic Model Selection**: Automatically loads available models for each provider
- **Background Scheduler**: Runs continuously even when browser is closed
- **Real-Time Updates**: WebSocket streaming for live logs and status
- **Trade Execution**: Smart pending orders (BUY/SELL STOP/LIMIT) based on AI analysis
- **Database Persistence**: All trades, logs, and configuration stored in SQLite
- **Professional UI**: Dark trading terminal aesthetic with responsive design
- **Error Recovery**: Robust error handling with automatic retry logic

---

## 📁 Project Structure

```
impulse_autopilot/
├── backend/
│   ├── main.py                 # FastAPI application entry point
│   ├── database.py             # SQLAlchemy setup & database initialization
│   ├── models.py               # Database models (AutopilotLog, TradeRecord, etc.)
│   ├── schemas.py              # Pydantic request/response schemas
│   ├── autopilot.py            # Core autopilot execution engine
│   ├── scheduler.py            # APScheduler management
│   ├── mt5_client.py           # MT5 data server client
│   ├── ai_analyzer.py          # Multi-provider AI integration
│   └── init_db.py              # Database seeding script
├── frontend/
│   ├── index.html              # Main dashboard HTML
│   ├── css/
│   │   └── style.css           # Dark theme styling
│   └── js/
│       └── dashboard.js        # WebSocket & UI logic
├── data/
│   └── autopilot.db            # SQLite database (auto-created)
├── .env.example                # Environment variables template
├── .gitignore
├── requirements.txt            # Python dependencies
├── PROGRESS.md                 # Development progress tracker
└── README.md                   # ← You are here
```

---

## 🚀 Quick Start

### 1. Prerequisites

- Python 3.10+
- MT5 data server running (mt5_data_server.py)
- API key from one of the supported AI providers

### 2. Installation

```bash
# Clone or navigate to the project
cd impulse_autopilot

# Create virtual environment (recommended)
python -m venv venv
venv\Scripts\activate  # On Windows
# source venv/bin/activate  # On Linux/Mac

# Install dependencies
pip install -r requirements.txt
```

### 3. Configuration

```bash
# Create .env file from template
cd backend
copy .env.example .env  # On Windows
# cp .env.example .env  # On Linux/Mac

# Edit .env with your settings
```

**Required `.env` variables:**
```env
# AI Provider (choose one)
AI_PROVIDER=NVIDIA
NVIDIA_API_KEY=nvapi-your_key_here
MODEL_NAME=qwen/qwen3.5-122b-a10b

# MT5 Data Server
MT5_URL=http://localhost:5000
MT5_TOKEN=your_mt5_token_here

# Database
DATABASE_URL=sqlite:///data/autopilot.db
```

### 4. Initialize Database

```bash
cd backend
python init_db.py
```

This creates the database and seeds:
- Default autopilot configuration
- Sample prompt templates

### 5. Run the Application

```bash
cd backend
python main.py
```

The server will start on `http://localhost:8000`

### 6. Access the Dashboard

Open your browser and navigate to:
```
http://localhost:8000
```

---

## 🎯 Usage Guide

### First-Time Setup

1. **Configure AI Provider**:
   - Go to "AI Provider Configuration" section
   - Select your AI provider (e.g., NVIDIA, Groq)
   - Choose a model from the dropdown
   - Enter your API key
   - Enter MT5 server URL and token
   - Click "Save Configuration"

2. **Set Run Interval**:
   - Choose how often the autopilot runs (e.g., 5 minutes)
   - Click "Apply"

3. **Start Autopilot**:
   - Click "Start Autopilot" button
   - Watch the status change to "ACTIVE"
   - Logs will appear in real-time

### Monitoring

- **Status Bar**: Shows current status, next run time, countdown, total runs
- **Live Logs**: Real-time execution logs with filtering by level
- **Statistics**: Success/error counts, success rate, total trades, P&L
- **Trade History**: Table of all executed trades with filtering by status

### Stopping

- Click "Stop Autopilot" to pause execution
- The scheduler will be removed but configuration is preserved
- Click "Start" again to resume

---

## 🔧 API Endpoints

### Autopilot Control
- `POST /autopilot/start` - Start autopilot
- `POST /autopilot/stop` - Stop autopilot
- `GET /autopilot/status` - Get current status

### Configuration
- `GET /autopilot/config` - Get configuration
- `POST /autopilot/config` - Update configuration

### Data
- `GET /autopilot/logs?limit=50&level=INFO` - Get logs
- `GET /trades?limit=50&status=OPEN` - Get trades
- `GET /prompts` - Get available prompts
- `GET /autopilot/stats` - Get statistics

### AI Providers
- `GET /ai/providers` - Get list of providers and their models

### WebSocket
- `WS /ws/logs` - Real-time log streaming

### Health
- `GET /health` - Health check

---

## 🤖 Supported AI Providers

| Provider | Base URL | Example Models |
|----------|----------|----------------|
| NVIDIA | https://integrate.api.nvidia.com/v1 | qwen/qwen3.5-122b-a10b, deepseek-ai/deepseek-v3.1 |
| Groq | https://api.groq.com/openai/v1 | llama-3.3-70b-versatile, mixtral-8x7b-32768 |
| OpenRouter | https://openrouter.ai/api/v1 | anthropic/claude-3.5-sonnet, openai/gpt-4o |
| OpenRouter (Free) | https://openrouter.ai/api/v1 | meta-llama/llama-3.1-8b-instruct:free |
| Gemini | https://generativelanguage.googleapis.com/v1beta/openai | gemini-2.0-flash, gemini-2.0-pro |
| GitHub Models | https://models.inference.ai.azure.com | Meta-Llama-3.1-405B-Instruct, gpt-4o |
| Cerebras | https://api.cerebras.ai/v1 | llama3.1-8b, llama3.1-70b |
| Bytez | https://api.bytez.com/models/v2/openai/ | meta-llama/Meta-Llama-3-8B-Instruct |

---

## 🗄️ Database Schema

### Tables
- `autopilot_logs` - Execution logs with timestamps and metadata
- `trades` - All executed trades with entry, SL, TP, P&L
- `autopilot_config` - Current configuration and statistics
- `prompt_templates` - Available prompts for AI analysis

---

## 🔐 Security Notes

- **Never commit `.env` file** - Contains API keys and tokens
- **API keys are masked** in the UI after saving
- **Database file is not tracked** by git (`.gitignore`)
- **Use strong passwords** for MT5 token
- **Rotate API keys** periodically

---

## 🐛 Troubleshooting

### Common Issues

**1. "No autopilot configuration found"**
- Run `python init_db.py` in the backend directory
- Check that `.env` file exists with correct variables

**2. "MT5 GET request failed"**
- Verify MT5 server is running
- Check MT5_URL and MT5_TOKEN in configuration
- Test connection: `curl -H "X-MT5-Token: YOUR_TOKEN" http://localhost:5000/health`

**3. "AI API Error"**
- Verify API key is correct for the selected provider
- Check API key format (NVIDIA keys need `nvapi-` prefix - handled automatically)
- Ensure you have API credits/quota remaining

**4. WebSocket disconnected**
- Check browser console for errors
- Verify server is running
- Refresh page to reconnect

**5. Database locked errors**
- Ensure only one instance of the app is running
- Delete `data/autopilot.db` and re-run `python init_db.py`

---

## 🔄 Migration from Streamlit

This system replaces the old Streamlit-based autopilot with:

| Feature | Streamlit (Old) | FastAPI (New) |
|---------|----------------|---------------|
| Background processes | ❌ Not supported | ✅ APScheduler |
| Real-time updates | ❌ Autorefresh only | ✅ WebSocket streaming |
| Persistent state | ❌ Session state loss | ✅ SQLite database |
| Countdown timer | ❌ Static | ✅ Live client-side |
| Trade execution | ⚠️ Manual | ✅ Automated |
| Multi-provider AI | ⚠️ Manual config | ✅ Dynamic selection |

---

## 📝 Development

### Adding New AI Provider

1. Edit `backend/ai_analyzer.py`
2. Add to `PROVIDER_CONFIGS` dict:
```python
"MyProvider": {
    "base_url": "https://api.myprovider.com/v1",
    "models": ["model-1", "model-2"],
    "key_prefix": ""  # Optional prefix for API key
}
```
3. Restart server - provider appears in UI automatically

### Running in Development Mode

```bash
cd backend
python main.py
```

The server runs with `reload=True` if `DEBUG=True` in `.env`

---

## 📄 License

Private project - All rights reserved

---

## 🙏 Credits

- **FastAPI**: High-performance web framework
- **APScheduler**: Background task scheduling
- **SQLAlchemy**: Database ORM
- **OpenAI**: Unified AI provider interface
- **Font Awesome**: Dashboard icons

---

**Built with ❤️ for algorithmic trading**
