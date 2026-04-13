"""
Core Autopilot Execution Engine
Orchestrates the entire flow: Load prompts → Fetch data → AI analysis → Execute trades
"""

import io
import time
import random
import traceback
from datetime import datetime, timezone
from typing import Dict, Optional

from database import SessionLocal
from models import AutopilotLog, TradeRecord, AutopilotConfig, PromptTemplate
from mt5_client import MT5Client
from ai_analyzer import AIAnalyzer


class AutopilotEngine:
    """Main autopilot execution engine"""
    
    def __init__(self, db_session=None):
        self.db = db_session or SessionLocal()
        self.mt5 = None
        self.ai = None
        self.config = None
    
    def load_config(self):
        """Load autopilot configuration from database"""
        self.config = self.db.query(AutopilotConfig).first()
        if not self.config:
            raise Exception("No autopilot configuration found in database")
        
        # Initialize MT5 client
        self.mt5 = MT5Client(
            base_url=self.config.mt5_url,
            token=self.config.mt5_token
        )
        
        # Initialize AI analyzer
        self.ai = AIAnalyzer(
            provider=self.config.ai_provider,
            api_key=self.config.api_key,
            model=self.config.model_name,
            base_url=self.config.base_url
        )
    
    def log(self, level: str, message: str, metadata: Optional[Dict] = None, 
            prompt_num: Optional[int] = None, symbol: Optional[str] = None):
        """Add log entry to database"""
        log_entry = AutopilotLog(
            timestamp=datetime.now(timezone.utc),
            level=level,
            message=message,
            metadata_json=metadata,
            prompt_num=prompt_num,
            symbol=symbol
        )
        self.db.add(log_entry)
        self.db.commit()
        return log_entry
    
    def execute_cycle(self) -> Dict:
        """
        Execute one complete autopilot cycle
        Returns dict with execution results
        """
        start_time = time.time()
        timestamp = datetime.now(timezone.utc)
        
        try:
            # Load config
            if not self.config:
                self.load_config()
            
            symbol = self.config.symbol
            result = {
                "success": False,
                "trade_placed": False,
                "timestamp": timestamp.isoformat(),
                "details": {}
            }
            
            # 1. Load prompts
            self.log("INFO", "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
            prompt = self._load_random_prompt()
            if not prompt:
                self.log("ERROR", "No prompts available")
                self.config.error_count += 1
                self.db.commit()
                result["details"]["error"] = "No prompts available"
                return result
            
            result["details"]["prompt_num"] = prompt.prompt_num
            result["details"]["prompt_text"] = prompt.prompt_text
            
            self.log("INFO", f"📝 Prompt #{prompt.prompt_num}: {prompt.prompt_text}", 
                    prompt_num=prompt.prompt_num)
            self.log("INFO", f"📊 Analyzing {symbol} | {self.config.candle_count} candles | TF: {self.config.timeframe}",
                    symbol=symbol)
            
            # 2. Fetch market data
            try:
                df = self.mt5.get_candles(
                    symbol=symbol,
                    timeframe=self.config.timeframe,
                    count=self.config.candle_count
                )
                
                if df.empty:
                    self.log("ERROR", f"Failed to fetch market data for {symbol}", symbol=symbol)
                    self.config.error_count += 1
                    self.db.commit()
                    result["details"]["error"] = "No market data"
                    return result
                    
            except Exception as e:
                self.log("ERROR", f"Data fetch error: {str(e)}", symbol=symbol)
                self.config.error_count += 1
                self.db.commit()
                result["details"]["error"] = f"Data fetch error: {str(e)}"
                return result
            
            # 3. Send to AI for analysis
            ai_start = time.time()
            self.log("INFO", f"🤖 Sending to {self.config.ai_provider} for analysis...")

            # Capture df.info() output properly (it returns None, must use StringIO)
            df_info_buf = io.StringIO()
            df.info(buf=df_info_buf)
            df_info = df_info_buf.getvalue()
            df_samples = df.tail(5).to_string()
            
            ai_response = self.ai.analyze_market(
                prompt_text=prompt.prompt_text,
                df_metadata=df_info,
                df_samples=df_samples
            )
            
            ai_time = time.time() - ai_start
            
            if not ai_response["success"]:
                self.log("ERROR", f"AI API Error: {ai_response.get('error', 'Unknown error')}")
                self.config.error_count += 1
                self.db.commit()
                result["details"]["error"] = ai_response.get("error")
                return result
            
            # Log AI response
            ai_summary = ai_response["text"][:200].replace('\n', ' ')
            self.log("INFO", f"🤖 AI Response ({ai_time:.1f}s): {ai_summary}...")
            result["details"]["ai_response_time"] = ai_time
            
            # 4. Check for trade setup
            setup = ai_response.get("setup")
            if not setup:
                self.log("WARNING", f"🟡 No trade setup identified by AI")
                self.log("INFO", f"💡 Market conditions didn't match prompt criteria")
                result["details"]["setup_found"] = False
                return result
            
            # 5. Trade setup found!
            self.log("SUCCESS", f"🎯 TRADE SETUP IDENTIFIED!", 
                    metadata=setup, prompt_num=prompt.prompt_num, symbol=symbol)
            result["details"]["setup_found"] = True
            result["details"]["setup"] = setup
            
            direction = setup["direction"].upper()
            entry = float(setup.get("entry_price", 0))
            sl = setup.get("stop_loss")
            tp = setup.get("take_profit")
            reasoning = setup.get("reasoning", "No reasoning provided")
            
            self.log("SUCCESS", f"   Direction: {'🟢 BUY' if direction == 'BUY' else '🔴 SELL'}")
            self.log("SUCCESS", f"   Symbol: {setup.get('symbol', symbol)}")
            self.log("SUCCESS", f"   Entry: {entry} | SL: {sl} | TP: {tp}")
            self.log("SUCCESS", f"   Reasoning: {reasoning}")
            
            # 6. Get live tick data for order classification
            try:
                tick = self.mt5.get_symbol_info(setup.get("symbol", symbol))
                ask = tick.get("ask")
                bid = tick.get("bid")
                
                if not (entry and ask and bid):
                    self.log("ERROR", f"Tick data unavailable - cannot place order")
                    self.config.error_count += 1
                    self.db.commit()
                    result["details"]["error"] = "No tick data"
                    return result
                    
            except Exception as e:
                self.log("ERROR", f"Tick data error: {str(e)}")
                self.config.error_count += 1
                self.db.commit()
                result["details"]["error"] = f"Tick error: {str(e)}"
                return result
            
            # 7. Classify order type
            if direction == "BUY":
                smart_action = "BUY_LIMIT" if entry < ask else "BUY_STOP"
            else:
                smart_action = "SELL_LIMIT" if entry > bid else "SELL_STOP"
            
            position_desc = "below" if "LIMIT" in smart_action else "above"
            self.log("INFO", f"📋 Order Type: {smart_action} (Entry {position_desc} current market)")
            
            # 8. Place order
            order_start = time.time()
            try:
                comment = f"[AUTO][P:{prompt.prompt_num}]"
                order_result = self.mt5.place_order(
                    symbol=setup.get("symbol", symbol),
                    action=smart_action,
                    volume=self.config.lot_size,
                    sl=sl if sl else None,
                    tp=tp if tp else None,
                    price=entry,
                    comment=comment
                )
                
                order_time = time.time() - order_start
                ticket = order_result.get("ticket", "N/A")
                
                # Log success
                self.log("SUCCESS", f"✅✅✅ TRADE EXECUTED SUCCESSFULLY! ✅✅✅")
                self.log("SUCCESS", f"   Ticket: #{ticket}")
                self.log("SUCCESS", f"   Type: {smart_action}")
                self.log("SUCCESS", f"   Entry: {entry} | SL: {sl} | TP: {tp}")
                self.log("SUCCESS", f"   Lot: {self.config.lot_size} | Symbol: {setup.get('symbol', symbol)}")
                self.log("SUCCESS", f"   Execution Time: {order_time:.2f}s")
                self.log("SUCCESS", f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
                
                # Save trade to database
                trade = TradeRecord(
                    ticket=ticket if ticket != "N/A" else 0,
                    timestamp=datetime.now(timezone.utc),
                    symbol=setup.get("symbol", symbol),
                    direction=direction,
                    order_type=smart_action,
                    entry_price=entry,
                    stop_loss=sl if sl else None,
                    take_profit=tp if tp else None,
                    lot_size=self.config.lot_size,
                    status="OPEN",
                    prompt_num=prompt.prompt_num,
                    reasoning=reasoning,
                    execution_time=order_time
                )
                self.db.add(trade)
                
                # Update config stats
                self.config.success_count += 1
                self.config.last_run_timestamp = datetime.now(timezone.utc)
                self.db.commit()
                
                result["success"] = True
                result["trade_placed"] = True
                result["details"]["ticket"] = ticket
                result["details"]["execution_time"] = order_time
                
            except Exception as e:
                self.log("ERROR", f"Trade execution error: {str(e)}")
                self.log("WARNING", f"📝 Order was NOT placed - check MT5 connection")
                self.log("SUCCESS", f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
                
                self.config.error_count += 1
                self.db.commit()
                result["details"]["error"] = str(e)
            
            return result
            
        except Exception as e:
            # Critical error
            self.log("CRITICAL", f"🔴 Critical Autopilot Error: {str(e)}")
            self.log("CRITICAL", f"📝 Traceback: {traceback.format_exc()}")
            self.log("CRITICAL", f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
            
            if self.config:
                self.config.error_count += 1
                self.db.commit()
            
            return {
                "success": False,
                "trade_placed": False,
                "timestamp": timestamp.isoformat(),
                "error": str(e),
                "traceback": traceback.format_exc()
            }
        finally:
            # Update next run time
            if self.config:
                next_run = datetime.now(timezone.utc).timestamp() + self.config.interval_seconds
                from datetime import datetime as dt
                self.config.next_run_timestamp = dt.fromtimestamp(next_run, tz=timezone.utc)
                self.db.commit()
            
            if not self.db.in_nested_transaction():
                self.db.close()
    
    def _load_random_prompt(self) -> Optional[PromptTemplate]:
        """Load a random active prompt from database"""
        prompts = self.db.query(PromptTemplate).filter(PromptTemplate.active == True).all()
        
        if not prompts:
            return None
        
        selected = random.choice(prompts)
        
        # Increment usage count
        selected.usage_count += 1
        self.db.commit()
        
        return selected
