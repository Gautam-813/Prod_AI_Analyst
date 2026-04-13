"""
AI Analyzer - Multi-provider AI integration
Supports: NVIDIA, Groq, OpenRouter, Gemini, GitHub, Cerebras, Bytez
With dynamic provider selection and model lists
"""

from openai import OpenAI
from typing import Optional, Dict, Any, List
import re
import json


# Provider configurations
PROVIDER_CONFIGS = {
    "NVIDIA": {
        "base_url": "https://integrate.api.nvidia.com/v1",
        "models": [
            "qwen/qwen3.5-122b-a10b",
            "qwen/qwen2.5-coder-32b-instruct",
            "deepseek-ai/deepseek-v3.1",
            "deepseek-ai/deepseek-r1-distill-qwen-32b",
            "nvidia/llama-3.1-405b-instruct"
        ],
        "key_prefix": "nvapi-"
    },
    "Groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "models": [
            "llama-3.3-70b-versatile",
            "llama-3.1-8b-instant",
            "mixtral-8x7b-32768",
            "gemma2-9b-it",
            "deepseek-r1-distill-llama-70b"
        ],
        "key_prefix": ""
    },
    "OpenRouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "models": [
            "anthropic/claude-3.5-sonnet",
            "openai/gpt-4o",
            "meta-llama/llama-3.1-405b-instruct",
            "mistralai/mistral-large",
            "google/gemini-pro-1.5"
        ],
        "key_prefix": ""
    },
    "OpenRouter (Free)": {
        "base_url": "https://openrouter.ai/api/v1",
        "models": [
            "meta-llama/llama-3.1-8b-instruct:free",
            "mistralai/mistral-7b-instruct:free",
            "google/gemma-2-9b-it:free",
            "qwen/qwen-2-7b-instruct:free"
        ],
        "key_prefix": ""
    },
    "Gemini": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "models": [
            "gemini-2.0-flash",
            "gemini-2.0-pro",
            "gemini-1.5-pro"
        ],
        "key_prefix": ""
    },
    "GitHub Models": {
        "base_url": "https://models.inference.ai.azure.com",
        "models": [
            "Meta-Llama-3.1-405B-Instruct",
            "Meta-Llama-3.1-70B-Instruct",
            "Mistral-large",
            "gpt-4o"
        ],
        "key_prefix": ""
    },
    "Cerebras": {
        "base_url": "https://api.cerebras.ai/v1",
        "models": [
            "llama3.1-8b",
            "llama3.1-70b"
        ],
        "key_prefix": ""
    },
    "Bytez": {
        "base_url": "https://api.bytez.com/models/v2/openai/",
        "models": [
            "meta-llama/Meta-Llama-3-8B-Instruct",
            "mistralai/Mistral-7B-Instruct-v0.2",
            "Qwen/Qwen1.5-72B-Chat"
        ],
        "key_prefix": ""
    }
}


def get_available_providers() -> List[str]:
    """Get list of all available AI providers"""
    return list(PROVIDER_CONFIGS.keys())


def get_provider_models(provider: str) -> List[str]:
    """Get available models for a specific provider"""
    if provider in PROVIDER_CONFIGS:
        return PROVIDER_CONFIGS[provider]["models"]
    return []


def get_provider_base_url(provider: str) -> str:
    """Get base URL for a specific provider"""
    if provider in PROVIDER_CONFIGS:
        return PROVIDER_CONFIGS[provider]["base_url"]
    raise ValueError(f"Unknown provider: {provider}")


class AIAnalyzer:
    """Multi-provider AI analyzer for trade setup detection"""
    
    def __init__(self, provider: str, api_key: str, model: str, base_url: Optional[str] = None):
        self.provider = provider
        self.model = model
        self.api_key = api_key
        
        # Resolve base URL if not provided
        self.base_url = base_url or get_provider_base_url(provider)
        
        # Resolve API key format
        final_key = api_key
        if provider == "NVIDIA" and not final_key.startswith("nvapi-"):
            final_key = f"nvapi-{final_key}"
        
        self.client = OpenAI(base_url=self.base_url, api_key=final_key)
    
    def analyze_market(self, prompt_text: str, df_metadata: str, 
                      df_samples: str, temperature: float = 0.2) -> Dict[str, Any]:
        """
        Send market data to AI for analysis
        Returns full response including text and any detected setups
        """
        system_prompt = f"""
        You are a Lead Quant in 2026. USE JSON ONLY FOR TRADES.
        SCHEMA: {df_metadata}
        SAMPLES (Last 5 Rows): {df_samples}
        RULES: 
        1. Output a JSON TRADE_SETUP block if you identify a trade opportunity.
        2. Suggest an ENTRY_PRICE based on your analysis.
        3. Be specific about entry, stop loss, and take profit levels.
        4. Provide clear reasoning for the trade setup.
        
        JSON FORMAT (if trade identified):
        ```json
        {{"action": "TRADE_SETUP", "symbol": "XAUUSD", "direction": "BUY", "order_type": "market", "entry_price": 2345.50, "stop_loss": 2338.00, "take_profit": 2360.00, "lot_size": 0.10, "risk_reward": 1.93, "reasoning": "Brief explanation"}}
        ```
        """
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Analyze current market data and {prompt_text}"}
                ],
                temperature=temperature
            )
            
            ai_text = response.choices[0].message.content
            
            # Try to detect trade setup
            setup = self.detect_trade_setup(ai_text)
            
            return {
                "success": True,
                "text": ai_text,
                "setup": setup,
                "model": self.model,
                "provider": self.provider
            }
            
        except Exception as e:
            return {
                "success": False,
                "text": "",
                "setup": None,
                "error": str(e),
                "model": self.model,
                "provider": self.provider
            }
    
    def detect_trade_setup(self, text: str) -> Optional[Dict]:
        """Detect and parse TRADE_SETUP JSON from AI response"""
        # Look for JSON blocks
        json_pattern = r"```json\s*(.*?)\s*```"
        blocks = re.findall(json_pattern, text, re.S | re.I)
        
        for block in blocks:
            try:
                data = json.loads(block)
                if isinstance(data, dict) and data.get("action") == "TRADE_SETUP":
                    return self._validate_setup(data)
            except json.JSONDecodeError:
                # Try to repair JSON
                try:
                    repaired = self._repair_json(block)
                    data = json.loads(repaired)
                    if isinstance(data, dict) and data.get("action") == "TRADE_SETUP":
                        return self._validate_setup(data)
                except:
                    continue
        
        # Try parsing entire text as JSON
        try:
            data = json.loads(text)
            if isinstance(data, dict) and data.get("action") == "TRADE_SETUP":
                return self._validate_setup(data)
        except:
            pass
        
        return None
    
    def _validate_setup(self, setup: Dict) -> Optional[Dict]:
        """Validate that setup has all required fields"""
        required_fields = ["symbol", "direction", "entry_price"]
        
        for field in required_fields:
            if field not in setup:
                return None
        
        # Validate direction
        if setup["direction"].upper() not in ["BUY", "SELL"]:
            return None
        
        return setup
    
    def _repair_json(self, text: str) -> str:
        """Fix common AI JSON mistakes"""
        # Fix missing commas between key-value pairs
        text = re.sub(
            r'("[\w_]+")\s*:\s*("[^"]*"|-?\d+\.?\d*|true|false|null)\s*\n\s*(")',
            r'\1: \2,\n  \3',
            text
        )
        # Fix trailing commas
        text = re.sub(r',\s*}', '}', text)
        text = re.sub(r',\s*]', ']', text)
        return text
