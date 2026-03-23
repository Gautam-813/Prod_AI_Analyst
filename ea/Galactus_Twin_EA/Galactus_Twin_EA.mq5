//+------------------------------------------------------------------+
//|                                                        GridEA.mq5 |
//|                         Institutional Grid EA — XAUUSD Hedging    |
//|                         Architecture: Full Modular Pipeline        |
//+------------------------------------------------------------------+
#property copyright   "Institutional GridEA"
#property version     "1.00"
#property strict

#include <Trade\Trade.mqh>
#include <Trade\PositionInfo.mqh>
#include <Trade\OrderInfo.mqh>

//+------------------------------------------------------------------+
//| Enumerations                                                       |
//+------------------------------------------------------------------+
enum ENUM_LOT_MODE
  {
   LOT_FIXED       = 0,  // Fixed Lot
   LOT_MULTIPLIER  = 1,  // Lot Multiplier
   LOT_INCREMENT   = 2   // Lot Increment
  };

enum ENUM_SIDE_STATE
  {
   STATE_IDLE            = 0,  // No activity
   STATE_ACTIVE          = 1,  // Positions open, grid monitoring live
   STATE_WAITING_REENTRY = 2   // TP hit, monitoring re-entry distance
  };

//+------------------------------------------------------------------+
//| Input Parameters                                                   |
//+------------------------------------------------------------------+
input group "=== Ladder Mode Configuration ==="
input bool   InpUseLadderMode  = false;    // Enable Ladder Mode (Trend Ladder)
input double InpLadderBuyDist  = 5.0;      // Ladder Buy Distance
input double InpLadderSellDist = 5.0;      // Ladder Sell Distance

//--- EA Identity
input group              "== EA Identity =="
input int                MagicNumber         = 100001;   // Magic Number
input string             EA_Comment          = "GridEA"; // Order Comment
input int                MaxSpreadPoints     = 9999;    // Maximum Allowed Spread (points)
int                Slippage            = 10000;       // Slippage (points)

//--- TP Configuration
input group              "== TP Configuration =="
input double             BuyTP_Dollars       = 10.0;     // Buy TP in Price Units (e.g. 10 = $10 move)
input double             SellTP_Dollars      = 10.0;     // Sell TP in Price Units

//--- Grid Configuration
input group              "== Grid Configuration =="
input double             BuyGridDistance     = 5.0;      // Buy Grid Distance
input double             SellGridDistance    = 5.0;      // Sell Grid Distance
input double             BuyReEntryDistance  = 5.0;      // Buy Re-Entry Distance
input double             SellReEntryDistance = 5.0;      // Sell Re-Entry Distance

//--- Lot Progression
input group              "== Buy Lot Progression =="
input ENUM_LOT_MODE      BuyLotMode          = LOT_FIXED;    // Buy Lot Mode
input double             BuyInitialLot       = 0.01;         // Buy Initial Lot
input double             BuyLotMultiplier    = 1.1;          // Buy Lot Multiplier
input double             BuyLotIncrement     = 0.01;         // Buy Lot Increment
input double             BuyMaxLot           = 1.0;          // Buy Max Lot

input group              "== Sell Lot Progression =="
input ENUM_LOT_MODE      SellLotMode         = LOT_FIXED;    // Sell Lot Mode
input double             SellInitialLot      = 0.01;         // Sell Initial Lot
input double             SellLotMultiplier   = 1.1;          // Sell Lot Multiplier
input double             SellLotIncrement    = 0.01;         // Sell Lot Increment
input double             SellMaxLot          = 1.0;          // Sell Max Lot

//--- Portfolio Circuit Breaker
input group              "== Circuit Breaker =="
input double             InpTotalProfitTarget = 100.0;  // Total Profit Target ($) (0=off)
input double             InpStopLoss          = 500.0;  // Overall Loss Limit ($) (0=off)

input group "=== Daily Profit/Loss Limit ==="
input double InpMaxDailyProfit   = 0.0; // Max Daily Profit ($) (0 to disable)
input double InpMaxDailyLoss     = 0.0; // Max Daily Loss ($) (0 to disable)

input group "=== Trade on Days ==="
input bool InpTradeMonday    = true;   // Trade on Monday
input bool InpTradeTuesday   = true;   // Trade on Tuesday
input bool InpTradeWednesday = true;   // Trade on Wednesday
input bool InpTradeThursday  = true;   // Trade on Thursday
input bool InpTradeFriday    = true;   // Trade on Friday

input group "=== Global Hedge Settings ==="
input bool   InpUseSessions    = false;    // Use Session Restriction
input bool   InpUseSess1       = true;     // Use Session 1
input string InpSess1Start     = "00:00";  // Sess 1 Start (HH:MM)
input string InpSess1End       = "23:59";  // Sess 1 End (HH:MM)
input bool   InpUseSess2       = false;    // Use Session 2
input string InpSess2Start     = "00:00";  // Sess 2 Start (HH:MM)
input string InpSess2End       = "00:00";  // Sess 2 End (HH:MM)
input bool   InpUseSess3       = false;    // Use Session 3
input string InpSess3Start     = "00:00";  // Sess 1 Start (HH:MM)
input string InpSess3End       = "00:00";  // Sess 1 End (HH:MM)
input bool   InpUseSess4       = false;    // Use Session 4
input string InpSess4Start     = "00:00";  // Sess 4 Start (HH:MM)
input string InpSess4End       = "00:00";  // Sess 4 End (HH:MM)

input group "=== ATR Entry Gate ==="
input double          InpATRValue     = 0.0;          // Min ATR Value (0 to disable)
input ENUM_TIMEFRAMES InpATRTimeframe = PERIOD_CURRENT; // ATR Timeframe
input int             InpATRPeriod    = 14;           // ATR Period

//--- Execution Safety
//input group              "== Execution Safety =="
int                MaxRetryAttempts    = 3;     // Order Retry Attempts
int                RetryDelayMS        = 200;   // Retry Delay (milliseconds)

//+------------------------------------------------------------------+
//| Global State — Minimal Scope                                       |
//+------------------------------------------------------------------+

//--- Broker symbol properties (loaded at init)
double   g_LotStep      = 0.01;
double   g_LotMin       = 0.01;
double   g_LotMax       = 100.0;
int      g_StopsLevel   = 0;
double   g_Point        = 0.0;
int      g_Digits       = 2;
long     g_FillingMode  = ORDER_FILLING_FOK;
bool     g_HaltTrading  = false;

//--- BUY side state
ENUM_SIDE_STATE  g_BuyState          = STATE_IDLE;
double           g_BuyLastEntryPrice = 0.0;
double           g_BuyTPClosePrice   = 0.0;
int              g_BuyGridIndex      = 0;    // 1-based, 0 = no trades

//--- SELL side state
ENUM_SIDE_STATE  g_SellState          = STATE_IDLE;
double           g_SellLastEntryPrice = 0.0;
double           g_SellTPClosePrice   = 0.0;
int              g_SellGridIndex      = 0;

//--- Consecutive failure counter
int      g_ConsecutiveFailures = 0;
int      MAX_CONSECUTIVE_FAIL  = 3;
datetime g_LastBarTime         = 0;

//--- Daily P/L tracking globals ---
datetime g_TrackingDay     = 0;
bool     g_DailyLimitHit   = false;

//--- Trade objects
CTrade   g_Trade;

//--- Indicator handles
int                   hATR_Entry      = INVALID_HANDLE; // ATR Indicator Handle

//+------------------------------------------------------------------+
//| OnInit                                                             |
//+------------------------------------------------------------------+

// NEW: License Expiration Protection
datetime EXPIRATION_DATE = D'2026.12.31 23:59:59';
datetime last_expiration_check = 0;

int OnInit()
  {
   // Check expiration date
   if(TimeCurrent() >= EXPIRATION_DATE)
     {
      Print("LICENSE EXPIRED! Please contact the developer for a renewal.");
      return(INIT_FAILED);
     }

   PrintFormat("[GridEA] OnInit — Magic: %d | Symbol: %s | Account: %s",
               MagicNumber, _Symbol, AccountInfoString(ACCOUNT_NAME));

   if(!ValidateEnvironment())
     {
      Print("[GridEA] CRITICAL: Environment validation failed. EA halted.");
      return INIT_FAILED;
     }

   DetectFillingMode();
   LoadSymbolProperties();
   LogEnvironmentReport();

   g_Trade.SetExpertMagicNumber(MagicNumber);
   g_Trade.SetDeviationInPoints(Slippage);
   g_Trade.SetTypeFilling((ENUM_ORDER_TYPE_FILLING)g_FillingMode);
   g_Trade.SetAsyncMode(false);

   if(!ReconstructOrInitialize())
     {
      Print("[GridEA] CRITICAL: Failed to reconstruct grid state.");
      return INIT_FAILED;
     }

   // Initialize daily tracking
   MqlDateTime _dt; TimeToStruct(TimeCurrent(), _dt);
   _dt.hour = 0; _dt.min = 0; _dt.sec = 0;
   g_TrackingDay   = StructToTime(_dt);
   g_DailyLimitHit = false;

   hATR_Entry = iATR(_Symbol, InpATRTimeframe, InpATRPeriod);
   if(hATR_Entry == INVALID_HANDLE)
     {
      Print("Failed to create ATR Entry handle");
      return(INIT_FAILED);
     }

   return INIT_SUCCEEDED;
  }

//+------------------------------------------------------------------+
//| OnDeinit                                                           |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   PrintFormat("[GridEA] OnDeinit — Reason: %d", reason);
   if(hATR_Entry != INVALID_HANDLE) IndicatorRelease(hATR_Entry);
}

//+------------------------------------------------------------------+
//| OnTick — Orchestration Only                                        |
//+------------------------------------------------------------------+
void OnTick()
  {
   // --- New Candle Detection & Auto-Retry Logic ---
   datetime currentBarTime = iTime(_Symbol, _Period, 0);
   if(currentBarTime > 0 && currentBarTime != g_LastBarTime)
     {
      g_LastBarTime = currentBarTime;
      // If halted due to failures or margin, reset on new candle
      if(g_HaltTrading && !g_DailyLimitHit)
        {
         Print("[GridEA] New candle detected. Resetting failure halt for a fresh attempt.");
         g_HaltTrading = false;
         g_ConsecutiveFailures = 0;
        }
     }

   // Check expiration every 12 hours (43200 seconds)
   if(TimeCurrent() - last_expiration_check >= 43200)
     {
      last_expiration_check = TimeCurrent();
      if(TimeCurrent() >= EXPIRATION_DATE)
        {
         Print("LICENSE EXPIRED! The EA will now remove itself from the chart.");
         ExpertRemove();
         return;
        }
     }

   // Check if day has changed - reset daily limit flag BEFORE halt check
   MqlDateTime _now; TimeToStruct(TimeCurrent(), _now);
   _now.hour = 0; _now.min = 0; _now.sec = 0;
   datetime _today = StructToTime(_now);
   if(_today > g_TrackingDay)
     {
      g_TrackingDay   = _today;
      g_DailyLimitHit = false;
      Print("[DailyLimit] New day detected. Resetting daily limit.");
     }

   if(g_HaltTrading || g_DailyLimitHit)
      {
       // Still monitor P&L even in halt state
       double pnl = ComputeFloatingPnL();
       if(ShouldCircuitBreakerFire(pnl))
         {
          ExecuteCircuitBreaker();
         }
       
       if(g_DailyLimitHit)
          Comment("DAILY LIMIT HIT: Trading halted until next day.");
       else
          Comment("TRADING HALTED: " + (g_ConsecutiveFailures >= MAX_CONSECUTIVE_FAIL ? "Too many failures (" + (string)g_ConsecutiveFailures + "). Retrying on new candle." : "Positions managed by EA."));
          
       return;
      }

   if(!RefreshMarketData())
      return;

   double totalPnL = ComputeFloatingPnL();

   if(ShouldCircuitBreakerFire(totalPnL))
     {
      ExecuteCircuitBreaker();
      return;
     }

      // --- Daily Profit/Loss Limit Check (History-Based) ---
      {
         if(!g_DailyLimitHit)
        {
         double _closedPnL = 0.0;
         if(HistorySelect(_today, TimeCurrent()))
           {
            int _totalDeals = HistoryDealsTotal();
            for(int _d = 0; _d < _totalDeals; _d++)
              {
               ulong _dTicket = HistoryDealGetTicket(_d);
               if(_dTicket > 0
                  && HistoryDealGetString(_dTicket, DEAL_SYMBOL) == _Symbol
                  && (long)HistoryDealGetInteger(_dTicket, DEAL_MAGIC) == (long)MagicNumber
                  && HistoryDealGetInteger(_dTicket, DEAL_ENTRY) != DEAL_ENTRY_IN)
                 {
                  _closedPnL += HistoryDealGetDouble(_dTicket, DEAL_PROFIT)
                               + HistoryDealGetDouble(_dTicket, DEAL_SWAP)
                               + HistoryDealGetDouble(_dTicket, DEAL_COMMISSION);
                 }
              }
           }
         double _openPnL = totalPnL; // already computed by ComputeFloatingPnL()
         double _totalDayPnL = _closedPnL + _openPnL;
         if(InpMaxDailyProfit > 0.0 && _totalDayPnL >= InpMaxDailyProfit)
           {
            g_DailyLimitHit = true;
            Print("[DailyLimit] Max Daily PROFIT hit: $", DoubleToString(_totalDayPnL, 2));
            ExecuteCircuitBreaker();
            return;
           }
         if(InpMaxDailyLoss > 0.0 && _totalDayPnL <= -InpMaxDailyLoss)
           {
            g_DailyLimitHit = true;
            Print("[DailyLimit] Max Daily LOSS hit: $", DoubleToString(_totalDayPnL, 2));
            ExecuteCircuitBreaker();
            return;
           }
        }
   }

   //--- Handle Idle State / Market Open placement
   if(g_BuyState == STATE_IDLE && CountOpenPositions(ORDER_TYPE_BUY) == 0)
      PlaceBuyAnchor();
      
   if(g_SellState == STATE_IDLE && CountOpenPositions(ORDER_TYPE_SELL) == 0)
      PlaceSellAnchor();

   if(!InpUseLadderMode)
     {
      ManageBuySide();
      ManageSellSide();
     }
   else
     {
      ManageLadderMode();
     }

   //--- Status Dashboard
   string status = "EA: Galactus Grid\n";
   status += "--------------------\n";
   if(!IsTradeTimeAllowed())
      status += "STATE: Entries Gated (Session Closed)\n";
   else
     {
      status += "STATE: Trading Active (Session Open)\n";
      if(g_ConsecutiveFailures > 0) 
         status += "FAILURES: " + (string)g_ConsecutiveFailures + "/" + (string)MAX_CONSECUTIVE_FAIL + "\n";
     }
      
   status += "Buy Side: " + (g_BuyState == STATE_ACTIVE ? "ACTIVE (" + (string)g_BuyGridIndex + ")" : (g_BuyState == STATE_WAITING_REENTRY ? "WAITING RE-ENTRY" : "IDLE")) + "\n";
   status += "Sell Side: " + (g_SellState == STATE_ACTIVE ? "ACTIVE (" + (string)g_SellGridIndex + ")" : (g_SellState == STATE_WAITING_REENTRY ? "WAITING RE-ENTRY" : "IDLE")) + "\n";
   status += "Floating PnL: " + DoubleToString(totalPnL, 2) + "\n";
      Comment(status);
  }

void ManageLadderMode();

//+------------------------------------------------------------------+
//| ValidateEnvironment                                                |
//+------------------------------------------------------------------+
bool ValidateEnvironment()
  {
   // Check hedging mode
   long marginMode = AccountInfoInteger(ACCOUNT_MARGIN_MODE);
   if(marginMode != ACCOUNT_MARGIN_MODE_RETAIL_HEDGING)
     {
      PrintFormat("[GridEA] WARNING: Account margin mode is %d. Expected HEDGING (%d).",
                  marginMode, ACCOUNT_MARGIN_MODE_RETAIL_HEDGING);
      // Warn but do not abort — some brokers report differently
     }

   // Check symbol tradeable
   long tradeMode = SymbolInfoInteger(_Symbol, SYMBOL_TRADE_MODE);
   if(tradeMode == SYMBOL_TRADE_MODE_DISABLED)
     {
      Print("[GridEA] CRITICAL: Symbol trade mode is DISABLED.");
      return false;
     }

   // Validate inputs
   if(BuyInitialLot < 0.01 || SellInitialLot < 0.01)
     {
      Print("[GridEA] CRITICAL: InitialLot below minimum 0.01.");
      return false;
     }
   if(BuyTP_Dollars <= 0.0 || SellTP_Dollars <= 0.0)
     {
      Print("[GridEA] CRITICAL: TP_Dollars must be > 0.");
      return false;
     }
   if(BuyGridDistance <= 0.0 || SellGridDistance <= 0.0)
     {
      Print("[GridEA] CRITICAL: GridDistance must be > 0.");
      return false;
     }
   if(BuyReEntryDistance <= 0.0 || SellReEntryDistance <= 0.0)
     {
      Print("[GridEA] CRITICAL: ReEntryDistance must be > 0.");
      return false;
     }
   if(InpTotalProfitTarget < 0.0 || InpStopLoss < 0.0) // Corrected variable names
     {
      Print("[GridEA] CRITICAL: Circuit breaker values must be >= 0.");
      return false;
     }
   if(BuyMaxLot < BuyInitialLot || SellMaxLot < SellInitialLot)
     {
      Print("[GridEA] CRITICAL: MaxLot must be >= InitialLot.");
      return false;
     }

   return true;
  }

//+------------------------------------------------------------------+
//| LoadSymbolProperties                                               |
//+------------------------------------------------------------------+
void LoadSymbolProperties()
  {
   g_LotStep   = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   g_LotMin    = MathMax(0.01, SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN));
   g_LotMax    = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   g_StopsLevel = (int)SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL);
   g_Point     = SymbolInfoDouble(_Symbol, SYMBOL_POINT);
   g_Digits    = (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS);

   if(g_LotStep <= 0.0) g_LotStep = 0.01;
  }

//+------------------------------------------------------------------+
//| DetectFillingMode                                                  |
//+------------------------------------------------------------------+
void DetectFillingMode()
  {
   long filling = SymbolInfoInteger(_Symbol, SYMBOL_FILLING_MODE);

   if((filling & SYMBOL_FILLING_FOK) == SYMBOL_FILLING_FOK)
     {
      g_FillingMode = ORDER_FILLING_FOK;
      Print("[GridEA] Filling Mode: FOK");
     }
   else if((filling & SYMBOL_FILLING_IOC) == SYMBOL_FILLING_IOC)
     {
      g_FillingMode = ORDER_FILLING_IOC;
      Print("[GridEA] Filling Mode: IOC");
     }
   else
     {
      g_FillingMode = ORDER_FILLING_RETURN;
      Print("[GridEA] Filling Mode: RETURN");
     }
  }

//+------------------------------------------------------------------+
//| LogEnvironmentReport                                               |
//+------------------------------------------------------------------+
void LogEnvironmentReport()
  {
   PrintFormat("[GridEA] === Environment Report ===");
   PrintFormat("[GridEA] Symbol     : %s", _Symbol);
   PrintFormat("[GridEA] Digits     : %d", g_Digits);
   PrintFormat("[GridEA] Point      : %.5f", g_Point);
   PrintFormat("[GridEA] LotStep    : %.2f", g_LotStep);
   PrintFormat("[GridEA] LotMin     : %.2f", g_LotMin);
   PrintFormat("[GridEA] LotMax     : %.2f", g_LotMax);
   PrintFormat("[GridEA] StopsLevel : %d points", g_StopsLevel);
   PrintFormat("[GridEA] FillingMode: %d", g_FillingMode);
   PrintFormat("[GridEA] Buy TP Units : %.2f", BuyTP_Dollars);
   PrintFormat("[GridEA] Sell TP Units: %.2f", SellTP_Dollars);
   PrintFormat("[GridEA] Buy Grid Dist: %.2f", BuyGridDistance);
   PrintFormat("[GridEA] Sell Grid Dist: %.2f", SellGridDistance);
   PrintFormat("[GridEA] Buy ReEntry  : %.2f", BuyReEntryDistance);
   PrintFormat("[GridEA] Sell ReEntry : %.2f", SellReEntryDistance);
   PrintFormat("[GridEA] Buy Lot Mode  : %d", BuyLotMode);
   PrintFormat("[GridEA] Sell Lot Mode : %d", SellLotMode);
   PrintFormat("[GridEA] Buy Init Lot  : %.2f", BuyInitialLot);
   PrintFormat("[GridEA] Sell Init Lot : %.2f", SellInitialLot);
   PrintFormat("[GridEA] Buy Max Lot   : %.2f", BuyMaxLot);
   PrintFormat("[GridEA] Sell Max Lot  : %.2f", SellMaxLot);
   PrintFormat("[GridEA] Profit Tgt : %.2f", InpTotalProfitTarget);
   PrintFormat("[GridEA] Loss Limit : %.2f", InpStopLoss);
   PrintFormat("[GridEA] ==============================");
  }

//+------------------------------------------------------------------+
//| ReconstructOrInitialize                                            |
//+------------------------------------------------------------------+
bool ReconstructOrInitialize()
  {
   int buyCount  = CountOpenPositions(ORDER_TYPE_BUY);
   int sellCount = CountOpenPositions(ORDER_TYPE_SELL);

   if(buyCount == 0 && sellCount == 0)
     {
      Print("[GridEA] No existing positions. Waiting for ticks to place anchor trades.");
      return true; // Return true to let OnTick handle the idle state
     }

   // Reconstruct BUY grid state
   if(buyCount > 0)
     {
      ReconstructSideState(ORDER_TYPE_BUY, buyCount);
      PrintFormat("[GridEA] Reconstructed BUY grid. Index: %d | LastEntry: %.5f",
                  g_BuyGridIndex, g_BuyLastEntryPrice);
     }

   // Reconstruct SELL grid state
   if(sellCount > 0)
     {
      ReconstructSideState(ORDER_TYPE_SELL, sellCount);
      PrintFormat("[GridEA] Reconstructed SELL grid. Index: %d | LastEntry: %.5f",
                  g_SellGridIndex, g_SellLastEntryPrice);
     }

   return true;
  }

//+------------------------------------------------------------------+
//| ReconstructSideState                                               |
//+------------------------------------------------------------------+
void ReconstructSideState(ENUM_ORDER_TYPE type, int count)
  {
   double extremePrice = 0.0;

   for(int i = 0; i < PositionsTotal(); i++)
     {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0) continue;
      if(PositionGetString(POSITION_SYMBOL) != _Symbol) continue;
      if((long)PositionGetInteger(POSITION_MAGIC) != MagicNumber) continue;
      if((ENUM_ORDER_TYPE)PositionGetInteger(POSITION_TYPE) != type) continue;

      double entryPrice = PositionGetDouble(POSITION_PRICE_OPEN);

      if(type == ORDER_TYPE_BUY)
        {
         // Worst BUY entry = lowest price (furthest from TP)
         if(extremePrice == 0.0 || entryPrice < extremePrice)
            extremePrice = entryPrice;
        }
      else
        {
         // Worst SELL entry = highest price
         if(extremePrice == 0.0 || entryPrice > extremePrice)
            extremePrice = entryPrice;
        }
     }

   if(type == ORDER_TYPE_BUY)
     {
      g_BuyState          = STATE_ACTIVE;
      g_BuyGridIndex      = count;
      g_BuyLastEntryPrice = extremePrice;
     }
   else
     {
      g_SellState          = STATE_ACTIVE;
      g_SellGridIndex      = count;
      g_SellLastEntryPrice = extremePrice;
     }
  }

//+------------------------------------------------------------------+
//| PlaceBuyAnchor                                                   |
//+------------------------------------------------------------------+
bool PlaceBuyAnchor()
  {
   if(!IsTradeTimeAllowed()) return false;
   
   if(!CheckATR()) return false;

   MqlTick tick;
   if(!SymbolInfoTick(_Symbol, tick)) return false;

   double buyTP = InpUseLadderMode ? 0.0 : NormalizeDouble(tick.ask + BuyTP_Dollars, g_Digits);
   double lot   = NormalizeLot(BuyInitialLot, BuyMaxLot);

   if(!InpUseLadderMode && !ValidateTPDistance(buyTP, tick.ask, ORDER_TYPE_BUY))
      buyTP = NormalizeDouble(tick.ask + MathMax(BuyTP_Dollars, (g_StopsLevel + 1) * g_Point), g_Digits);

   ulong buyTicket = ExecuteOrder(ORDER_TYPE_BUY, lot, buyTP, "Initial Buy");
   if(buyTicket == 0) return false;

   g_BuyState          = STATE_ACTIVE;
   g_BuyGridIndex      = 1;
   g_BuyLastEntryPrice = tick.ask;
   PrintFormat("[GridEA] Anchor BUY placed. Ticket: %d | Entry: %.5f | TP: %.5f", buyTicket, tick.ask, buyTP);
   return true;
  }

//+------------------------------------------------------------------+
//| PlaceSellAnchor                                                  |
//+------------------------------------------------------------------+
bool PlaceSellAnchor()
  {
   if(!IsTradeTimeAllowed()) return false;
   
   if(!CheckATR()) return false;

   MqlTick tick;
   if(!SymbolInfoTick(_Symbol, tick)) return false;

   double sellTP = InpUseLadderMode ? 0.0 : NormalizeDouble(tick.bid - SellTP_Dollars, g_Digits);
   double lot    = NormalizeLot(SellInitialLot, SellMaxLot);

   if(!InpUseLadderMode && !ValidateTPDistance(sellTP, tick.bid, ORDER_TYPE_SELL))
      sellTP = NormalizeDouble(tick.bid - MathMax(SellTP_Dollars, (g_StopsLevel + 1) * g_Point), g_Digits);

   ulong sellTicket = ExecuteOrder(ORDER_TYPE_SELL, lot, sellTP, "Initial Sell");
   if(sellTicket == 0) return false;

   g_SellState          = STATE_ACTIVE;
   g_SellGridIndex      = 1;
   g_SellLastEntryPrice = tick.bid;
   PrintFormat("[GridEA] Anchor SELL placed. Ticket: %d | Entry: %.5f | TP: %.5f", sellTicket, tick.bid, sellTP);
   return true;
  }

//+------------------------------------------------------------------+
//| RefreshMarketData                                                  |
//+------------------------------------------------------------------+
bool RefreshMarketData()
  {
   // Check symbol tradeable
   long tradeMode = SymbolInfoInteger(_Symbol, SYMBOL_TRADE_MODE);
   if(tradeMode == SYMBOL_TRADE_MODE_DISABLED)
     {
      Print("[GridEA] WARNING: Symbol trade disabled. Skipping tick.");
      return false;
     }

   // Check spread
   MqlTick tick;
   if(!SymbolInfoTick(_Symbol, tick))
     {
      Print("[GridEA] WARNING: Cannot retrieve tick data.");
      return false;
     }

   double spreadPoints = (tick.ask - tick.bid) / g_Point;
   if(spreadPoints > MaxSpreadPoints)
     {
      PrintFormat("[GridEA] WARNING: Spread %.1f > Max %d. Blocking new entries.",
                  spreadPoints, MaxSpreadPoints);
      return false;
     }

   return true;
  }

//+------------------------------------------------------------------+
//| ComputeFloatingPnL                                                 |
//+------------------------------------------------------------------+
double ComputeFloatingPnL()
  {
   double total = 0.0;
   for(int i = 0; i < PositionsTotal(); i++)
     {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0) continue;
      if(PositionGetString(POSITION_SYMBOL) != _Symbol) continue;
      if((long)PositionGetInteger(POSITION_MAGIC) != MagicNumber) continue;
      total += PositionGetDouble(POSITION_PROFIT);
     }
   return total;
  }

//+------------------------------------------------------------------+
//| ShouldCircuitBreakerFire                                           |
//+------------------------------------------------------------------+
bool ShouldCircuitBreakerFire(double pnl)
  {
   if(InpTotalProfitTarget > 0.0 && pnl >= InpTotalProfitTarget)
     {
      PrintFormat("[GridEA] CIRCUIT BREAKER: Profit target hit. PnL: %.2f >= %.2f",
                  pnl, InpTotalProfitTarget);
      return true;
     }
   if(InpStopLoss > 0.0 && pnl <= -InpStopLoss)
     {
      PrintFormat("[GridEA] CIRCUIT BREAKER: Loss limit hit. PnL: %.2f <= %.2f",
                  pnl, -InpStopLoss);
      return true;
     }
   return false;
  }

//+------------------------------------------------------------------+
//| ExecuteCircuitBreaker                                              |
//+------------------------------------------------------------------+
void ExecuteCircuitBreaker()
  {
   Print("[GridEA] Executing circuit breaker — closing all positions.");
   CloseAllPositions("Circuit Breaker");
   ResetGridState();
   Sleep(500);
   Print("[GridEA] Circuit breaker complete. Ready for fresh anchor trades.");
  }

//--- CheckZeroOpenTrades removed to allow waiting for re-entry distances on empty account.

//+------------------------------------------------------------------+
//| ManageBuySide                                                      |
//+------------------------------------------------------------------+
void ManageBuySide()
  {
   int openBuys = CountOpenPositions(ORDER_TYPE_BUY);

   if(g_BuyState == STATE_ACTIVE)
     {
      // Reconcile: check if a TP was hit (positions reduced externally)
      if(openBuys < g_BuyGridIndex && openBuys == 0)
        {
         // All BUY positions gone — TP hit on final position
         MqlTick tick;
         SymbolInfoTick(_Symbol, tick);
         g_BuyTPClosePrice = tick.bid;
         g_BuyState        = STATE_WAITING_REENTRY;
         g_BuyGridIndex    = 0;
         PrintFormat("[GridEA] BUY TP hit. Waiting re-entry from: %.5f", g_BuyTPClosePrice);
         return;
        }

      // Check grid trigger: price moved DOWN against BUY by GridDistance
      MqlTick tick;
      if(!SymbolInfoTick(_Symbol, tick)) return;

      double gridTriggerPrice = g_BuyLastEntryPrice - BuyGridDistance;

      if(tick.ask <= gridTriggerPrice)
        {
         int nextIndex = g_BuyGridIndex + 1;
         double lot    = ComputeLot(ORDER_TYPE_BUY, nextIndex);
         double tp     = NormalizeDouble(tick.ask + BuyTP_Dollars, g_Digits);

         if(!ValidateMargin(ORDER_TYPE_BUY, lot))
           {
            Print("[GridEA] WARNING: Insufficient margin for BUY grid trade. Halting new entries.");
            g_HaltTrading = true;
            return;
           }

         string comment = "Buy Grid #" + IntegerToString(nextIndex);
         ulong ticket = ExecuteOrder(ORDER_TYPE_BUY, lot, tp, comment);
         if(ticket > 0)
           {
            g_BuyGridIndex      = nextIndex;
            g_BuyLastEntryPrice = tick.ask;
            PrintFormat("[GridEA] BUY Grid #%d placed. Ticket: %d | Entry: %.5f | TP: %.5f",
                        nextIndex, ticket, tick.ask, tp);
           }
        }
     }
   else if(g_BuyState == STATE_WAITING_REENTRY)
     {
      MqlTick tick;
      if(!SymbolInfoTick(_Symbol, tick)) return;

      bool triggeredUp   = tick.ask >= g_BuyTPClosePrice + BuyReEntryDistance;
      bool triggeredDown = tick.bid <= g_BuyTPClosePrice - BuyReEntryDistance;

      if(triggeredUp || triggeredDown)
        {
         if(!IsTradeTimeAllowed()) return;

         double lot = NormalizeLot(BuyInitialLot, BuyMaxLot);
         double tp  = NormalizeDouble(tick.ask + BuyTP_Dollars, g_Digits);

         ulong ticket = ExecuteOrder(ORDER_TYPE_BUY, lot, tp, "Buy Re-Entry");
         if(ticket > 0)
           {
            g_BuyState          = STATE_ACTIVE;
            g_BuyGridIndex      = 1;
            g_BuyLastEntryPrice = tick.ask;
            PrintFormat("[GridEA] BUY Re-Entry placed. Ticket: %d | Entry: %.5f | TP: %.5f | Lot: %.2f",
                        ticket, tick.ask, tp, lot);
           }
        }
     }
  }

//+------------------------------------------------------------------+
//| ManageSellSide                                                     |
//+------------------------------------------------------------------+
void ManageSellSide()
  {
   int openSells = CountOpenPositions(ORDER_TYPE_SELL);

   if(g_SellState == STATE_ACTIVE)
     {
      // Reconcile: check if a TP was hit
      if(openSells < g_SellGridIndex && openSells == 0)
        {
         MqlTick tick;
         SymbolInfoTick(_Symbol, tick);
         g_SellTPClosePrice = tick.ask;
         g_SellState        = STATE_WAITING_REENTRY;
         g_SellGridIndex    = 0;
         PrintFormat("[GridEA] SELL TP hit. Waiting re-entry from: %.5f", g_SellTPClosePrice);
         return;
        }

      // Check grid trigger: price moved UP against SELL by GridDistance
      MqlTick tick;
      if(!SymbolInfoTick(_Symbol, tick)) return;

      double gridTriggerPrice = g_SellLastEntryPrice + SellGridDistance;

      if(tick.bid >= gridTriggerPrice)
        {
         int nextIndex = g_SellGridIndex + 1;
         double lot    = ComputeLot(ORDER_TYPE_SELL, nextIndex);
         double tp     = NormalizeDouble(tick.bid - SellTP_Dollars, g_Digits);

         if(!ValidateMargin(ORDER_TYPE_SELL, lot))
           {
            Print("[GridEA] WARNING: Insufficient margin for SELL grid trade. Halting new entries.");
            g_HaltTrading = true;
            return;
           }

         string comment = "Sell Grid #" + IntegerToString(nextIndex);
         ulong ticket = ExecuteOrder(ORDER_TYPE_SELL, lot, tp, comment);
         if(ticket > 0)
           {
            g_SellGridIndex      = nextIndex;
            g_SellLastEntryPrice = tick.bid;
            PrintFormat("[GridEA] SELL Grid #%d placed. Ticket: %d | Entry: %.5f | TP: %.5f",
                        nextIndex, ticket, tick.bid, tp);
           }
        }
     }
   else if(g_SellState == STATE_WAITING_REENTRY)
     {
      MqlTick tick;
      if(!SymbolInfoTick(_Symbol, tick)) return;

      bool triggeredUp   = tick.ask >= g_SellTPClosePrice + SellReEntryDistance;
      bool triggeredDown = tick.bid <= g_SellTPClosePrice - SellReEntryDistance;

      if(triggeredUp || triggeredDown)
        {
         if(!IsTradeTimeAllowed()) return;

         double lot = NormalizeLot(SellInitialLot, SellMaxLot);
         double tp  = NormalizeDouble(tick.bid - SellTP_Dollars, g_Digits);

         ulong ticket = ExecuteOrder(ORDER_TYPE_SELL, lot, tp, "Sell Re-Entry");
         if(ticket > 0)
           {
            g_SellState          = STATE_ACTIVE;
            g_SellGridIndex      = 1;
            g_SellLastEntryPrice = tick.bid;
            PrintFormat("[GridEA] SELL Re-Entry placed. Ticket: %d | Entry: %.5f | TP: %.5f | Lot: %.2f",
                        ticket, tick.bid, tp, lot);
           }
        }
     }
  }

//+------------------------------------------------------------------+
//| ExecuteOrder                                                       |
//+------------------------------------------------------------------+
ulong ExecuteOrder(ENUM_ORDER_TYPE type, double lot, double tp, string comment)
  {
   if(!TerminalInfoInteger(TERMINAL_TRADE_ALLOWED) || !MQLInfoInteger(MQL_TRADE_ALLOWED))
     {
      Print("[GridEA] ExecuteOrder: Trading not allowed by Terminal/MQL.");
      return 0;
     }

   MqlTradeRequest request = {};
   MqlTradeResult  result  = {};

   for(int attempt = 1; attempt <= MaxRetryAttempts; attempt++)
     {
      MqlTick tick;
      if(!SymbolInfoTick(_Symbol, tick))
        {
         PrintFormat("[GridEA] ExecuteOrder: Cannot get tick (attempt %d)", attempt);
         Sleep(RetryDelayMS);
         continue;
        }

      // Validate spread before each attempt
      double spreadPoints = (tick.ask - tick.bid) / g_Point;
      if(spreadPoints > MaxSpreadPoints)
        {
         PrintFormat("[GridEA] ExecuteOrder: Spread too wide %.1f > %d (attempt %d)",
                     spreadPoints, MaxSpreadPoints, attempt);
         Sleep(RetryDelayMS);
         continue;
        }

      double price = (type == ORDER_TYPE_BUY) ? tick.ask : tick.bid;

      // Validate TP stops level
      if(!ValidateTPDistance(tp, price, type))
        {
         PrintFormat("[GridEA] ExecuteOrder: TP too close to stops level. TP: %.5f Price: %.5f",
                     tp, price);
         return 0; // Hard fail — not retriable
        }

      ZeroMemory(request);
      ZeroMemory(result);

      request.action       = TRADE_ACTION_DEAL;
      request.symbol       = _Symbol;
      request.volume       = lot;
      request.type         = type;
      request.price        = price;
      request.tp           = tp;
      request.sl           = 0.0;
      request.deviation    = Slippage;
      request.magic        = MagicNumber;
      request.comment      = (comment == "") ? EA_Comment : comment;
      request.type_filling = (ENUM_ORDER_TYPE_FILLING)g_FillingMode;
      request.type_time    = ORDER_TIME_GTC;

      bool sent = OrderSend(request, result);

      if(sent && (result.retcode == TRADE_RETCODE_DONE || 
                  result.retcode == TRADE_RETCODE_PLACED || 
                  result.retcode == TRADE_RETCODE_DONE_PARTIAL || 
                  result.retcode == TRADE_RETCODE_NO_CHANGES))
        {
         g_ConsecutiveFailures = 0;
         PrintFormat("[GridEA] Order filled. Ticket: %d | Type: %s | Lot: %.2f | Price: %.5f | TP: %.5f",
                     result.order,
                     (type == ORDER_TYPE_BUY) ? "BUY" : "SELL",
                     lot, result.price, tp);
         return result.order;
        }

      // Classify retcode
      uint rc = result.retcode;

      if(rc == TRADE_RETCODE_REQUOTE ||
         rc == TRADE_RETCODE_PRICE_CHANGED ||
         rc == TRADE_RETCODE_MARKET_CLOSED
         )
        {
         PrintFormat("[GridEA] Soft rejection (retcode %d: %s). Retry %d/%d.",
                     rc, result.comment, attempt, MaxRetryAttempts);
         if(rc == TRADE_RETCODE_MARKET_CLOSED) Sleep(5000); // Wait longer for market to open
         else Sleep(RetryDelayMS);
         continue;
        }
      else if(rc == TRADE_RETCODE_NO_MONEY)
        {
         Print("[GridEA] CRITICAL: No money. Halting trading.");
         g_HaltTrading = true;
         return 0;
        }
      else if(rc == TRADE_RETCODE_TRADE_DISABLED)
        {
         Print("[GridEA] CRITICAL: Trade disabled on account. Halting.");
         g_HaltTrading = true;
         return 0;
        }
      else
        {
         PrintFormat("[GridEA] Hard rejection (retcode %d). Aborting order.", rc);
         g_ConsecutiveFailures++;
         if(g_ConsecutiveFailures >= MAX_CONSECUTIVE_FAIL)
           {
            PrintFormat("[GridEA] CRITICAL: %d consecutive failures. Halting new entries.",
                        g_ConsecutiveFailures);
            g_HaltTrading = true;
           }
         return 0;
        }
     }

   PrintFormat("[GridEA] ExecuteOrder: All %d retry attempts exhausted.", MaxRetryAttempts);
   // Only increment failure counter if it wasn't a market closed error
   if(result.retcode != TRADE_RETCODE_MARKET_CLOSED && result.retcode != 0)
     {
      g_ConsecutiveFailures++;
      if(g_ConsecutiveFailures >= MAX_CONSECUTIVE_FAIL)
        {
         PrintFormat("[GridEA] CRITICAL: %d consecutive failures. Halting new entries.",
                     g_ConsecutiveFailures);
         g_HaltTrading = true;
        }
     }
   else
     {
      Print("[GridEA] ExecuteOrder: All attempts exhausted (Market Closed or Tick Error). No permanent halt.");
     }
   return 0;
  }

//+------------------------------------------------------------------+
//| CloseAllPositions                                                  |
//+------------------------------------------------------------------+
void CloseAllPositions(string reason = "Exit")
  {
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0) continue;
      if(PositionGetString(POSITION_SYMBOL) != _Symbol) continue;
      if((long)PositionGetInteger(POSITION_MAGIC) != MagicNumber) continue;

      ENUM_POSITION_TYPE type = (ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);
      double volume = PositionGetDouble(POSITION_VOLUME);
      
      MqlTradeRequest request = {};
      MqlTradeResult  result  = {};
      
      request.action       = TRADE_ACTION_DEAL;
      request.position     = ticket;
      request.symbol       = _Symbol;
      request.volume       = volume;
      request.magic        = MagicNumber;
      request.comment      = reason;
      request.type_filling = (ENUM_ORDER_TYPE_FILLING)g_FillingMode;
      request.deviation    = Slippage;
      
      // Close by opposite volume
      if(type == POSITION_TYPE_BUY)
        {
         request.type = ORDER_TYPE_SELL;
         request.price = SymbolInfoDouble(_Symbol, SYMBOL_BID);
        }
      else
        {
         request.type = ORDER_TYPE_BUY;
         request.price = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
        }

      if(!OrderSend(request, result))
        {
         PrintFormat("[GridEA] WARNING: Failed to close ticket %d (%s). Retcode: %d",
                     ticket, reason, result.retcode);
        }
      else
        {
         PrintFormat("[GridEA] Closed ticket %d (%s).", ticket, reason);
        }
     }
  }

//+------------------------------------------------------------------+
//| ResetGridState                                                     |
//+------------------------------------------------------------------+
void ResetGridState()
  {
   g_BuyState          = STATE_IDLE;
   g_BuyLastEntryPrice = 0.0;
   g_BuyTPClosePrice   = 0.0;
   g_BuyGridIndex      = 0;

   g_SellState          = STATE_IDLE;
   g_SellLastEntryPrice = 0.0;
   g_SellTPClosePrice   = 0.0;
   g_SellGridIndex      = 0;

   g_ConsecutiveFailures = 0;
   g_HaltTrading         = false;

   Print("[GridEA] Grid state fully reset.");
  }

//+------------------------------------------------------------------+
//| ComputeLot                                                       |
//+------------------------------------------------------------------+
double ComputeLot(ENUM_ORDER_TYPE type, int gridIndex)
  {
   double initial = (type == ORDER_TYPE_BUY) ? BuyInitialLot : SellInitialLot;
   double mult    = (type == ORDER_TYPE_BUY) ? BuyLotMultiplier : SellLotMultiplier;
   double inc     = (type == ORDER_TYPE_BUY) ? BuyLotIncrement : SellLotIncrement;
   double max     = (type == ORDER_TYPE_BUY) ? BuyMaxLot : SellMaxLot;
   ENUM_LOT_MODE mode = (type == ORDER_TYPE_BUY) ? BuyLotMode : SellLotMode;

   double raw = initial;

   if(mode == LOT_MULTIPLIER)
     {
      raw = initial * MathPow(mult, gridIndex - 1);
     }
   else if(mode == LOT_INCREMENT)
     {
      raw = initial + inc * (gridIndex - 1);
     }

   return NormalizeLot(raw, max);
  }

//+------------------------------------------------------------------+
//| NormalizeLot                                                       |
//+------------------------------------------------------------------+
double NormalizeLot(double rawLot, double maxLimit)
  {
   double step     = g_LotStep;
   double rounded  = MathRound(rawLot / step) * step;
   double clamped  = MathMax(g_LotMin, MathMin(maxLimit, rounded));
   // Apply broker enforced max as final ceiling
   double brokerMax = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   clamped = MathMin(clamped, brokerMax);
   return NormalizeDouble(clamped, 2);
  }

//+------------------------------------------------------------------+
//| ValidateTPDistance                                                 |
//+------------------------------------------------------------------+
bool ValidateTPDistance(double tp, double price, ENUM_ORDER_TYPE type)
  {
   if(tp <= 0.0) return true; // No Take Profit
   double minDistance = g_StopsLevel * g_Point;
   if(minDistance <= 0.0) return true; // Broker has no stops level restriction

   double distance = (type == ORDER_TYPE_BUY) ? (tp - price) : (price - tp);
   return distance >= minDistance;
  }

//+------------------------------------------------------------------+
//| ValidateMargin                                                     |
//+------------------------------------------------------------------+
bool ValidateMargin(ENUM_ORDER_TYPE type, double lot)
  {
   double marginRequired = 0.0;
   MqlTick tick;
   if(!SymbolInfoTick(_Symbol, tick)) return false;

   double price = (type == ORDER_TYPE_BUY) ? tick.ask : tick.bid;

   if(!OrderCalcMargin((ENUM_ORDER_TYPE)type, _Symbol, lot, price, marginRequired))
     {
      Print("[GridEA] ValidateMargin: OrderCalcMargin failed.");
      return false;
     }

   double freeMargin = AccountInfoDouble(ACCOUNT_MARGIN_FREE);
   if(freeMargin < marginRequired * 1.2) // 20% safety buffer
     {
      PrintFormat("[GridEA] Margin check failed. Required: %.2f | Free: %.2f",
                  marginRequired, freeMargin);
      return false;
     }

   return true;
  }

//+------------------------------------------------------------------+
//| CountOpenPositions                                                 |
//+------------------------------------------------------------------+
int CountOpenPositions(ENUM_ORDER_TYPE type)
  {
   int count = 0;
   for(int i = 0; i < PositionsTotal(); i++)
     {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0) continue;
      if(PositionGetString(POSITION_SYMBOL) != _Symbol) continue;
      if((long)PositionGetInteger(POSITION_MAGIC) != MagicNumber) continue;
      if((ENUM_ORDER_TYPE)PositionGetInteger(POSITION_TYPE) == type)
         count++;
     }
   return count;
  }

//+------------------------------------------------------------------+
//| Helper function to check ATR gate                               |
//+------------------------------------------------------------------+
bool CheckATR()
{
   if(InpATRValue <= 0) return true;
   
   double atr[1];
   if(CopyBuffer(hATR_Entry, 0, 0, 1, atr) > 0)
     {
      if(atr[0] < InpATRValue)
        {
         Comment("WAITING FOR VOLATILITY: ATR (", DoubleToString(atr[0], _Digits), ") < ", DoubleToString(InpATRValue, _Digits));
         return false;
        }
     }
   else return false; // Buffer not ready
   
   return true;
}

//+------------------------------------------------------------------+
//| IsTradeTimeAllowed                                               |
//+------------------------------------------------------------------+
bool IsTradeTimeAllowed()
  {
   MqlDateTime dt;
   TimeCurrent(dt);

   // 1. Check Day of Week
   bool dayAllowed = false;
   switch(dt.day_of_week)
     {
      case 1: dayAllowed = InpTradeMonday;    break;
      case 2: dayAllowed = InpTradeTuesday;   break;
      case 3: dayAllowed = InpTradeWednesday; break;
      case 4: dayAllowed = InpTradeThursday;  break;
      case 5: dayAllowed = InpTradeFriday;    break;
      default: dayAllowed = false;            break; // No weekend trading by default
     }
   
   if(!dayAllowed) return false;

   // 2. Check Session
   if(!InpUseSessions) return true;

   int currentMinutes = dt.hour * 60 + dt.min;

   if(InpUseSess1 && IsInSession(currentMinutes, InpSess1Start, InpSess1End)) return true;
   if(InpUseSess2 && IsInSession(currentMinutes, InpSess2Start, InpSess2End)) return true;
   if(InpUseSess3 && IsInSession(currentMinutes, InpSess3Start, InpSess3End)) return true;
   if(InpUseSess4 && IsInSession(currentMinutes, InpSess4Start, InpSess4End)) return true;

   return false;
  }

//+------------------------------------------------------------------+
//| IsInSession Helper                                               |
//+------------------------------------------------------------------+
bool IsInSession(int currentMin, string startStr, string endStr)
  {
   int startMin = ParseHM(startStr);
   int endMin   = ParseHM(endStr);
   
   if(endMin < startMin) // Overnight session
     {
      return (currentMin >= startMin || currentMin <= endMin);
     }
   
   return (currentMin >= startMin && currentMin <= endMin);
  }

//+------------------------------------------------------------------+
//| ParseHM Helper                                                   |
//+------------------------------------------------------------------+
int ParseHM(string hm)
  {
   string parts[];
   if(StringSplit(hm, ':', parts) != 2) return 0;
   return (int)StringToInteger(parts[0]) * 60 + (int)StringToInteger(parts[1]);
  }

//+------------------------------------------------------------------+
//| GetLastPositionTicket                                            |
//+------------------------------------------------------------------+
ulong GetLastPositionTicket(ENUM_POSITION_TYPE type)
{
   ulong lastTicket = 0;
   datetime lastTime = 0;
   for(int i = 0; i < PositionsTotal(); i++)
     {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0) continue;
      if(PositionGetString(POSITION_SYMBOL) != _Symbol) continue;
      if((long)PositionGetInteger(POSITION_MAGIC) != MagicNumber) continue;
      if((ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE) == (ENUM_POSITION_TYPE)type)
        {
         datetime t = (datetime)PositionGetInteger(POSITION_TIME);
         if(t > lastTime)
           {
            lastTime = t;
            lastTicket = ticket;
           }
        }
     }
   return lastTicket;
}

//+------------------------------------------------------------------+
//| CloseMostRecentPosition                                          |
//+------------------------------------------------------------------+
bool CloseMostRecentPosition(ENUM_POSITION_TYPE type)
{
   ulong ticket = GetLastPositionTicket(type);
   if(ticket == 0) return false;
   
   if(!PositionSelectByTicket(ticket)) return false;
   double volume = PositionGetDouble(POSITION_VOLUME);
   ENUM_POSITION_TYPE posType = (ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);
   
   MqlTradeRequest request = {};
   MqlTradeResult  result  = {};
   
   request.action       = TRADE_ACTION_DEAL;
   request.position     = ticket;
   request.symbol       = _Symbol;
   request.volume       = volume;
   request.magic        = MagicNumber;
   request.comment      = "Ladder Close";
   request.type_filling = (ENUM_ORDER_TYPE_FILLING)g_FillingMode;
   request.deviation    = Slippage;
   request.type         = (posType == POSITION_TYPE_BUY) ? ORDER_TYPE_SELL : ORDER_TYPE_BUY;
   request.price        = (posType == POSITION_TYPE_BUY) ? SymbolInfoDouble(_Symbol, SYMBOL_BID) : SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   
   if(!OrderSend(request, result))
     {
      PrintFormat("[Ladder] Failed to close ticket %d. Retcode: %d", ticket, result.retcode);
      return false;
     }
   PrintFormat("[Ladder] Closed most recent %s ticket %d", (posType == POSITION_TYPE_BUY ? "BUY" : "SELL"), ticket);
   return true;
}

//+------------------------------------------------------------------+
//| GetLastPositionPrice                                             |
//+------------------------------------------------------------------+
double GetLastPositionPrice(ENUM_POSITION_TYPE type)
{
   double lastPrice = 0.0;
   datetime lastTime = 0;
   for(int i = 0; i < PositionsTotal(); i++)
     {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0) continue;
      if(PositionGetString(POSITION_SYMBOL) != _Symbol) continue;
      if((long)PositionGetInteger(POSITION_MAGIC) != MagicNumber) continue;
      if((ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE) == type)
        {
         datetime t = (datetime)PositionGetInteger(POSITION_TIME);
         if(t > lastTime)
           {
            lastTime = t;
            lastPrice = PositionGetDouble(POSITION_PRICE_OPEN);
           }
        }
     }
   return lastPrice;
}

//+------------------------------------------------------------------+
//| ManageLadderMode                                                 |
//+------------------------------------------------------------------+
void ManageLadderMode()
{
   MqlTick tick;
   if(!SymbolInfoTick(_Symbol, tick)) return;

   int openBuys  = CountOpenPositions(ORDER_TYPE_BUY);
   int openSells = CountOpenPositions(ORDER_TYPE_SELL);
   
   // Refresh tracking price from actual open positions if they exist
   double lastBuyPrice  = GetLastPositionPrice(POSITION_TYPE_BUY);
   double lastSellPrice = GetLastPositionPrice(POSITION_TYPE_SELL);
   
   if(openBuys > 0)  g_BuyLastEntryPrice  = lastBuyPrice;
   if(openSells > 0) g_SellLastEntryPrice = lastSellPrice;

   // --- CASE 1: BUY LADDER LOGIC ---
   if(g_BuyState == STATE_ACTIVE)
     {
      // 1A. TREND UP
      if(tick.ask >= g_BuyLastEntryPrice + InpLadderBuyDist)
        {
         int nextIndex = openBuys + 1; // Martingale only if 'openBuys' already has positions
         double lot = ComputeLot(ORDER_TYPE_BUY, nextIndex);
         
         ulong bTicket = ExecuteOrder(ORDER_TYPE_BUY, lot, 0, "Ladder Buy #" + (string)nextIndex);
         if(bTicket > 0)
           {
            g_BuyGridIndex = nextIndex;
            g_BuyLastEntryPrice = tick.ask;
            
            if(nextIndex % 2 == 0) 
               CloseMostRecentPosition(POSITION_TYPE_SELL);
            else 
               ExecuteOrder(ORDER_TYPE_SELL, NormalizeLot(SellInitialLot, SellMaxLot), 0, "Ladder Hedge Sell");
           }
        }
      
      // 1B. REVERSAL DOWN
      if(openBuys > 1 && tick.bid <= g_BuyLastEntryPrice - InpLadderSellDist)
        {
         if(CloseMostRecentPosition(POSITION_TYPE_BUY))
           {
            int nextSellIndex = openSells + 1; // Will be 2 if hedge 0.01 exists, or 1 if no hedge exists
            double sLot = ComputeLot(ORDER_TYPE_SELL, nextSellIndex);
            ulong sTicket = ExecuteOrder(ORDER_TYPE_SELL, sLot, 0, "Ladder Rev Sell #" + (string)nextSellIndex);
            
            if(sTicket > 0)
              {
               g_SellGridIndex = nextSellIndex;
               g_BuyGridIndex = openBuys - 1; 
               g_SellLastEntryPrice = tick.bid;
               g_BuyLastEntryPrice  = GetLastPositionPrice(POSITION_TYPE_BUY); // Move memory back to remaining buy
               g_SellState = STATE_ACTIVE;
              }
           }
        }
     }

   // --- CASE 2: SELL LADDER LOGIC ---
   if(g_SellState == STATE_ACTIVE)
     {
      // 2A. TREND DOWN
      if(tick.bid <= g_SellLastEntryPrice - InpLadderSellDist)
        {
         int nextSellIndex = openSells + 1;
         double lot = ComputeLot(ORDER_TYPE_SELL, nextSellIndex);
         
         ulong sTicket = ExecuteOrder(ORDER_TYPE_SELL, lot, 0, "Ladder Sell #" + (string)nextSellIndex);
         if(sTicket > 0)
           {
            g_SellGridIndex = nextSellIndex;
            g_SellLastEntryPrice = tick.bid;
            
            if(nextSellIndex % 2 == 0) 
               CloseMostRecentPosition(POSITION_TYPE_BUY);
            else 
               ExecuteOrder(ORDER_TYPE_BUY, NormalizeLot(BuyInitialLot, BuyMaxLot), 0, "Ladder Hedge Buy");
           }
        }
      
      // 2B. REVERSAL UP
      if(openSells > 1 && tick.ask >= g_SellLastEntryPrice + InpLadderBuyDist)
        {
         if(CloseMostRecentPosition(POSITION_TYPE_SELL))
           {
            int nextBuyIndex = openBuys + 1;
            double bLot = ComputeLot(ORDER_TYPE_BUY, nextBuyIndex);
            ulong bTicket = ExecuteOrder(ORDER_TYPE_BUY, bLot, 0, "Ladder Rev Buy #" + (string)nextBuyIndex);
            
            if(bTicket > 0)
              {
               g_BuyGridIndex = nextBuyIndex;
               g_SellGridIndex = openSells - 1;
               g_BuyLastEntryPrice  = tick.ask;
               g_SellLastEntryPrice = GetLastPositionPrice(POSITION_TYPE_SELL);
               g_BuyState = STATE_ACTIVE;
              }
           }
        }
     }
}

//+------------------------------------------------------------------+
//| End of GridEA.mq5                                                  |
//+------------------------------------------------------------------+