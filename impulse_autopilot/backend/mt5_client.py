"""
MT5 Data Server Client
Handles communication with the MT5 Data Server (mt5_data_server.py)
Uses the actual API endpoints from the existing MT5 server
"""

import requests
from typing import Optional, Dict, List
import pandas as pd


class MT5Client:
    """Client for MT5 Data Server API"""
    
    def __init__(self, base_url: str, token: str):
        self.base_url = base_url.rstrip('/')
        self.token = token
        self.headers = {"X-MT5-Token": token}
        self.session = requests.Session()
    
    def _get(self, endpoint: str, params: Optional[Dict] = None) -> Dict:
        """Make GET request to MT5 server"""
        try:
            response = self.session.get(
                f"{self.base_url}/{endpoint}",
                headers=self.headers,
                params=params,
                timeout=10
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            raise Exception(f"MT5 GET request failed: {e}")
    
    def _post(self, endpoint: str, payload: Dict) -> Dict:
        """Make POST request to MT5 server"""
        try:
            response = self.session.post(
                f"{self.base_url}/{endpoint}",
                headers=self.headers,
                json=payload,
                timeout=10
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            raise Exception(f"MT5 POST request failed: {e}")
    
    def test_connection(self) -> bool:
        """Test if MT5 server is reachable and initialized"""
        try:
            response = self._get("health")
            return response.get("mt5_initialized", False)
        except:
            return False
    
    def get_symbol_info(self, symbol: str) -> Dict:
        """Get symbol information (ask, bid, point, digits, etc.)"""
        try:
            return self._get(f"symbols/info/{symbol}")
        except Exception as e:
            raise Exception(f"Failed to get symbol info for {symbol}: {e}")
    
    def get_candles(self, symbol: str, timeframe: str, count: int = 1000) -> pd.DataFrame:
        """
        Fetch latest OHLCV candles from MT5 server
        Uses /data/fetch-latest endpoint (position-based, ignores clock differences)
        Returns pandas DataFrame
        """
        payload = {
            "symbol": symbol,
            "timeframe": timeframe,
            "count": count
        }
        
        try:
            data = self._post("data/fetch-latest", payload)
            
            if not data or not data.get("data"):
                return pd.DataFrame()
            
            # Convert to DataFrame
            df = pd.DataFrame(data["data"])
            
            # Ensure time column is datetime
            if "time" in df.columns:
                df["time"] = pd.to_datetime(df["time"])
            
            # Convert numeric columns
            for col in ["open", "high", "low", "close", "volume", "tick_volume", "spread"]:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors="coerce")
            
            return df
            
        except Exception as e:
            raise Exception(f"Failed to fetch candles for {symbol}: {e}")
    
    def place_order(self, symbol: str, action: str, volume: float, 
                    sl: Optional[float] = None, tp: Optional[float] = None,
                    price: Optional[float] = None, magic: int = 123456,
                    comment: str = "[AUTOPILOT]") -> Dict:
        """
        Place order (market or pending)
        action: BUY, SELL, BUY_STOP, SELL_STOP, BUY_LIMIT, SELL_LIMIT
        """
        payload = {
            "symbol": symbol,
            "action": action.upper(),
            "volume": volume,
            "magic": magic,
            "comment": comment
        }
        
        if sl is not None:
            payload["sl"] = sl
        if tp is not None:
            payload["tp"] = tp
        if price is not None:
            payload["price"] = price
        
        return self._post("order/place", payload)
    
    def close_position(self, ticket: int, volume: Optional[float] = None, 
                      comment: str = "[AUTOPILOT]") -> Dict:
        """Close an open position"""
        payload = {
            "ticket": ticket
        }
        if volume is not None:
            payload["volume"] = volume
        if comment:
            payload["comment"] = comment
        
        return self._post("order/close", payload)
    
    def modify_position(self, ticket: int, sl: Optional[float] = None, 
                       tp: Optional[float] = None) -> Dict:
        """Modify SL/TP of open position"""
        payload = {"ticket": ticket}
        if sl is not None:
            payload["sl"] = sl
        if tp is not None:
            payload["tp"] = tp
        
        return self._post("order/modify", payload)
    
    def get_positions(self) -> Dict:
        """Get all open positions"""
        return self._get("positions/summary")
    
    def get_trade_history(self, hours: int = 24) -> Dict:
        """Get trade history"""
        return self._get("trades/history", params={"hours": hours})
