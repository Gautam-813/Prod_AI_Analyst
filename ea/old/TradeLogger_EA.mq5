//+------------------------------------------------------------------+
//|                                          ML_TradeLogger_v2.mq5   |
//|                         Event-Driven Trade Data Collector for ML  |
//|                                                    Version: 2.00  |
//+------------------------------------------------------------------+
#property copyright "ML Trade Logger v2"
#property version   "2.00"
#property description "Event-driven EA to log all trade events instantly to CSV for ML pattern analysis"

#include <Trade/DealInfo.mqh>
#include <Trade/PositionInfo.mqh>
#include <Trade/OrderInfo.mqh>

//--- Input Parameters — FILE SETTINGS
input string   CSVFolder              = "ML_TradeLogs"; // CSV folder name
input bool     CreateDailyFiles       = true;            // New file every day

//--- Input Parameters — EVENT FILTERS
input bool     LogOpenEvents          = true;            // Log OPEN events
input bool     LogCloseEvents         = true;            // Log CLOSE events
input bool     LogSLChanges           = true;            // Log SL modifications
input bool     LogTPChanges           = true;            // Log TP modifications
input bool     LogVolumeChanges       = true;            // Log partial close / DCA
input bool     LogPendingOrders       = false;           // Log pending order events

//--- Input Parameters — MARKET CONTEXT
input bool     CaptureMarketSnapshot  = true;            // Capture price/indicator context
input int      EMA_Fast_Period        = 20;              // Fast EMA period
input int      EMA_Slow_Period        = 200;             // Slow EMA period (200 EMA strategy)
input int      ATR_Period             = 14;              // ATR period for volatility

//+------------------------------------------------------------------+
//| Global objects                                                     |
//+------------------------------------------------------------------+
CDealInfo      g_Deal;
CPositionInfo  g_Pos;
COrderInfo     g_Order;

string         g_CurrentFile  = "";
datetime       g_LastDate     = 0;
int            g_EMAFastHandle = INVALID_HANDLE;
int            g_EMASlowHandle = INVALID_HANDLE;
int            g_ATRHandle     = INVALID_HANDLE;

//+------------------------------------------------------------------+
//| CSV Header — 30 columns                                           |
//+------------------------------------------------------------------+
//  1  Timestamp             - Server time of event
//  2  Event_Type            - OPEN / CLOSE / SL_CHANGE / TP_CHANGE / VOLUME_CHANGE
//  3  Ticket                - Position ticket
//  4  Deal_Ticket           - Deal ticket (for close events)
//  5  Symbol                - Instrument
//  6  Direction             - BUY / SELL
//  7  Volume                - Current lot size
//  8  Price_Open            - Position open price
//  9  Price_Event           - Price at moment of this event
// 10  SL_Old                - SL before change
// 11  SL_New                - SL after change
// 12  TP_Old                - TP before change
// 13  TP_New                - TP after change
// 14  Profit_Float          - Floating P&L at event time (OPEN/MODIFY events)
// 15  Profit_Realized       - Realized P&L (CLOSE events)
// 16  Commission            - Commission (CLOSE events)
// 17  Swap                  - Swap (CLOSE events)
// 18  Duration_Minutes      - Minutes position was open at event time
// 19  Magic                 - Magic number (0 = manual trade)
// 20  Comment               - Position/deal comment
// 21  EMA_Fast              - Fast EMA value at event
// 22  EMA_Slow              - Slow EMA value at event (200 EMA)
// 23  Price_vs_EMA200       - Price position relative to 200 EMA: ABOVE / BELOW
// 24  ATR                   - ATR value (volatility context)
// 25  Spread                - Current spread in points
// 26  Session               - ASIAN / LONDON / NEWYORK / OVERLAP
// 27  Day_of_Week           - MON/TUE/WED/THU/FRI
// 28  Account_Balance       - Account balance at event
// 29  Account_Equity        - Account equity at event
// 30  Server                - "MT5"

//+------------------------------------------------------------------+
//| Initialization                                                     |
//+------------------------------------------------------------------+
int OnInit()
{
   //--- Create indicators for market context
   if(CaptureMarketSnapshot)
   {
      g_EMAFastHandle = iMA(_Symbol, PERIOD_M1, EMA_Fast_Period, 0, MODE_EMA, PRICE_CLOSE);
      g_EMASlowHandle = iMA(_Symbol, PERIOD_M1, EMA_Slow_Period, 0, MODE_EMA, PRICE_CLOSE);
      g_ATRHandle     = iATR(_Symbol, PERIOD_M1, ATR_Period);
      
      if(g_EMAFastHandle == INVALID_HANDLE || g_EMASlowHandle == INVALID_HANDLE || g_ATRHandle == INVALID_HANDLE)
      {
         Print("WARNING: Indicator handles failed — market snapshot will be empty");
      }
   }
   
   //--- Create folder and first log file
   if(!FolderCreate(CSVFolder, 0))
      Print("Note: Folder may already exist: ", CSVFolder);
   
   g_LastDate = StringToTime(TimeToString(TimeCurrent(), TIME_DATE));
   InitLogFile();
   
   Print("=== ML Trade Logger v2 Initialized ===");
   Print("Mode: Event-Driven (OnTradeTransaction)");
   Print("Log path: ", CSVFolder, "\\", g_CurrentFile);
   Print("Market snapshot: ", CaptureMarketSnapshot ? "ON" : "OFF");
   Print("Watching: OPEN=", LogOpenEvents, " CLOSE=", LogCloseEvents,
         " SL=", LogSLChanges, " TP=", LogTPChanges);
   
   return(INIT_SUCCEEDED);
}

//+------------------------------------------------------------------+
//| Deinitialization                                                   |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   if(g_EMAFastHandle != INVALID_HANDLE) IndicatorRelease(g_EMAFastHandle);
   if(g_EMASlowHandle != INVALID_HANDLE) IndicatorRelease(g_EMASlowHandle);
   if(g_ATRHandle     != INVALID_HANDLE) IndicatorRelease(g_ATRHandle);
   Print("ML Trade Logger v2 stopped. Reason code: ", reason);
}

//+------------------------------------------------------------------+
//| OnTick — only used for daily file rotation check                  |
//+------------------------------------------------------------------+
void OnTick()
{
   if(!CreateDailyFiles) return;
   
   datetime currentDate = StringToTime(TimeToString(TimeCurrent(), TIME_DATE));
   if(currentDate != g_LastDate)
   {
      g_LastDate = currentDate;
      InitLogFile();
      Print("Daily file rotated: ", g_CurrentFile);
   }
}

//+------------------------------------------------------------------+
//| THE CORE — fires instantly on every trade event                   |
//+------------------------------------------------------------------+
void OnTradeTransaction(const MqlTradeTransaction& trans,
                        const MqlTradeRequest&     request,
                        const MqlTradeResult&      result)
{
   //--- We care about these transaction types only
   switch(trans.type)
   {
      //------------------------------------------------------------
      // POSITION OPENED — deal entry IN
      //------------------------------------------------------------
      case TRADE_TRANSACTION_DEAL_ADD:
      {
         if(!HistoryDealSelect(trans.deal)) return;
         g_Deal.Ticket(trans.deal);
         
         ENUM_DEAL_ENTRY entry = g_Deal.Entry();
         
         //--- New position opened
         if(entry == DEAL_ENTRY_IN && LogOpenEvents)
         {
            string symbol  = g_Deal.Symbol();
            ulong  ticket  = g_Deal.PositionId();
            string dir     = (g_Deal.DealType() == DEAL_TYPE_BUY) ? "BUY" : "SELL";
            double volOpen = g_Deal.Volume();
            double priceOpen = g_Deal.Price();
            
            //--- Get SL/TP from position
            double sl = 0, tp = 0, floatPL = 0;
            if(g_Pos.SelectByTicket(ticket))
            {
               sl      = g_Pos.StopLoss();
               tp      = g_Pos.TakeProfit();
               floatPL = g_Pos.Profit();
            }
            
            WriteRow(
               "OPEN",
               ticket,
               trans.deal,
               symbol,
               dir,
               volOpen,
               priceOpen,      // price_open
               priceOpen,      // price_event = same as open
               0, sl,          // sl_old=0, sl_new
               0, tp,          // tp_old=0, tp_new
               floatPL,        // float PL
               0, 0, 0,        // realized, commission, swap
               (datetime)g_Deal.Time(),
               g_Deal.Magic(),
               g_Deal.Comment()
            );
         }
         
         //--- Position closed (full or partial)
         else if((entry == DEAL_ENTRY_OUT || entry == DEAL_ENTRY_OUT_BY) && LogCloseEvents)
         {
            string symbol    = g_Deal.Symbol();
            ulong  ticket    = g_Deal.PositionId();
            string dir       = (g_Deal.DealType() == DEAL_TYPE_BUY) ? "BUY" : "SELL";
            double volClose  = g_Deal.Volume();
            double priceClose = g_Deal.Price();
            double profit    = g_Deal.Profit();
            double commission = g_Deal.Commission();
            double swap      = g_Deal.Swap();
            
            //--- Get original open price from history
            double priceOpen = GetPositionOpenPrice(ticket);
            datetime timeOpen = GetPositionOpenTime(ticket);
            
            string eventType = (entry == DEAL_ENTRY_OUT_BY) ? "CLOSE_HEDGE" : "CLOSE";
            
            //--- Check if partial close (position still exists)
            if(g_Pos.SelectByTicket(ticket))
            {
               eventType = "CLOSE_PARTIAL";
               if(!LogVolumeChanges) return;
            }
            
            WriteRow(
               eventType,
               ticket,
               trans.deal,
               symbol,
               dir,
               volClose,
               priceOpen,
               priceClose,
               0, 0,           // sl old/new (not relevant for close)
               0, 0,           // tp old/new
               0,              // float PL (position closed)
               profit, commission, swap,
               timeOpen,
               g_Deal.Magic(),
               g_Deal.Comment()
            );
         }
         break;
      }
      
      //------------------------------------------------------------
      // POSITION MODIFIED — SL or TP changed
      //------------------------------------------------------------
      case TRADE_TRANSACTION_POSITION:
      {
         ulong ticket = trans.position;
         if(ticket == 0) return;
         if(!g_Pos.SelectByTicket(ticket)) return;
         
         string symbol = g_Pos.Symbol();
         string dir    = (g_Pos.PositionType() == POSITION_TYPE_BUY) ? "BUY" : "SELL";
         
         double slNew = trans.price_sl;
         double tpNew = trans.price_tp;
         
         //--- We detect what changed by comparing with trans values
         //--- trans.price = new SL, trans.price_tp = new TP
         //--- We log both SL and TP in one row since they change together
         
         bool slChanged = (slNew != g_Pos.StopLoss());
         bool tpChanged = (tpNew != g_Pos.TakeProfit());
         
         if(slChanged && LogSLChanges)
         {
            WriteRow(
               "SL_CHANGE",
               ticket,
               0,
               symbol,
               dir,
               g_Pos.Volume(),
               g_Pos.PriceOpen(),
               g_Pos.PriceCurrent(),
               g_Pos.StopLoss(), slNew,   // sl_old, sl_new
               g_Pos.TakeProfit(), tpNew,  // tp_old, tp_new (may also change)
               g_Pos.Profit(),
               0, 0, 0,
               g_Pos.Time(),
               g_Pos.Magic(),
               "SL Modified"
            );
         }
         
         if(tpChanged && !slChanged && LogTPChanges)
         {
            WriteRow(
               "TP_CHANGE",
               ticket,
               0,
               symbol,
               dir,
               g_Pos.Volume(),
               g_Pos.PriceOpen(),
               g_Pos.PriceCurrent(),
               g_Pos.StopLoss(), slNew,
               g_Pos.TakeProfit(), tpNew,
               g_Pos.Profit(),
               0, 0, 0,
               g_Pos.Time(),
               g_Pos.Magic(),
               "TP Modified"
            );
         }
         break;
      }
      
      //------------------------------------------------------------
      // PENDING ORDER events (optional)
      //------------------------------------------------------------
      case TRADE_TRANSACTION_ORDER_ADD:
      case TRADE_TRANSACTION_ORDER_UPDATE:
      case TRADE_TRANSACTION_ORDER_DELETE:
      {
         if(!LogPendingOrders) return;
         
         string evtType = "ORDER_ADD";
         if(trans.type == TRADE_TRANSACTION_ORDER_UPDATE) evtType = "ORDER_UPDATE";
         if(trans.type == TRADE_TRANSACTION_ORDER_DELETE) evtType = "ORDER_DELETE";
         
         WriteRow(
            evtType,
            trans.order,
            0,
            trans.symbol,
            (trans.deal_type == DEAL_TYPE_BUY) ? "BUY" : "SELL",
            trans.volume,
            trans.price,
            trans.price,
            trans.price_sl, trans.price_sl,
            trans.price_tp, trans.price_tp,
            0, 0, 0, 0,
            TimeCurrent(),
            0,
            ""
         );
         break;
      }
      
      default: break;
   }
}

//+------------------------------------------------------------------+
//| Write one row to CSV                                              |
//+------------------------------------------------------------------+
void WriteRow(string   eventType,
              ulong    ticket,
              ulong    dealTicket,
              string   symbol,
              string   direction,
              double   volume,
              double   priceOpen,
              double   priceEvent,
              double   slOld,     double slNew,
              double   tpOld,     double tpNew,
              double   floatPL,
              double   realizedPL, double commission, double swap,
              datetime timeOpen,
              ulong    magic,
              string   comment)
{
   //--- Daily file rotation
   if(CreateDailyFiles)
   {
      datetime today = StringToTime(TimeToString(TimeCurrent(), TIME_DATE));
      if(today != g_LastDate)
      {
         g_LastDate = today;
         InitLogFile();
      }
   }
   
   int handle = FileOpen(g_CurrentFile, FILE_READ | FILE_WRITE | FILE_CSV | FILE_ANSI, ",");
   if(handle == INVALID_HANDLE)
   {
      Print("ERROR: Cannot open log file — ", g_CurrentFile);
      return;
   }
   FileSeek(handle, 0, SEEK_END);
   
   //--- Calculate duration
   datetime now = TimeCurrent();
   int durationMins = (timeOpen > 0) ? (int)((now - timeOpen) / 60) : 0;
   
   //--- Market snapshot
   double emaFast = 0, emaSlow = 0, atr = 0;
   int    spread  = 0;
   string priceVsEMA = "N/A";
   
   if(CaptureMarketSnapshot)
   {
      double bufF[1], bufS[1], bufA[1];
      if(CopyBuffer(g_EMAFastHandle, 0, 0, 1, bufF) > 0) emaFast = bufF[0];
      if(CopyBuffer(g_EMASlowHandle, 0, 0, 1, bufS) > 0) emaSlow = bufS[0];
      if(CopyBuffer(g_ATRHandle,     0, 0, 1, bufA) > 0) atr     = bufA[0];
      
      spread = (int)SymbolInfoInteger(symbol, SYMBOL_SPREAD);
      priceVsEMA = (priceEvent > emaSlow && emaSlow > 0) ? "ABOVE" : "BELOW";
   }
   
   //--- Session detection
   string session = GetSession();
   
   //--- Day of week
   string dow = GetDayOfWeek(now);
   
   //--- Account state
   double balance = AccountInfoDouble(ACCOUNT_BALANCE);
   double equity  = AccountInfoDouble(ACCOUNT_EQUITY);
   
   int digits = (int)SymbolInfoInteger(symbol, SYMBOL_DIGITS);
   if(digits == 0) digits = 5;
   
   FileWrite(handle,
      TimeToString(now, TIME_DATE | TIME_SECONDS),  // 1  Timestamp
      eventType,                                     // 2  Event_Type
      IntegerToString(ticket),                       // 3  Ticket
      IntegerToString(dealTicket),                   // 4  Deal_Ticket
      symbol,                                        // 5  Symbol
      direction,                                     // 6  Direction
      DoubleToString(volume, 2),                     // 7  Volume
      DoubleToString(priceOpen, digits),             // 8  Price_Open
      DoubleToString(priceEvent, digits),            // 9  Price_Event
      DoubleToString(slOld, digits),                 // 10 SL_Old
      DoubleToString(slNew, digits),                 // 11 SL_New
      DoubleToString(tpOld, digits),                 // 12 TP_Old
      DoubleToString(tpNew, digits),                 // 13 TP_New
      DoubleToString(floatPL, 2),                    // 14 Profit_Float
      DoubleToString(realizedPL, 2),                 // 15 Profit_Realized
      DoubleToString(commission, 2),                 // 16 Commission
      DoubleToString(swap, 2),                       // 17 Swap
      IntegerToString(durationMins),                 // 18 Duration_Minutes
      IntegerToString(magic),                        // 19 Magic
      comment,                                       // 20 Comment
      DoubleToString(emaFast, digits),               // 21 EMA_Fast
      DoubleToString(emaSlow, digits),               // 22 EMA_Slow
      priceVsEMA,                                    // 23 Price_vs_EMA200
      DoubleToString(atr, digits),                   // 24 ATR
      IntegerToString(spread),                       // 25 Spread
      session,                                       // 26 Session
      dow,                                           // 27 Day_of_Week
      DoubleToString(balance, 2),                    // 28 Account_Balance
      DoubleToString(equity, 2),                     // 29 Account_Equity
      "MT5"                                          // 30 Server
   );
   
   FileClose(handle);
   
   Print("LOG [", eventType, "] Ticket:", ticket, " ", symbol, " ", direction,
         " Vol:", DoubleToString(volume, 2),
         " PriceEvent:", DoubleToString(priceEvent, digits),
         " PL:", DoubleToString((eventType == "CLOSE" ? realizedPL : floatPL), 2));
}

//+------------------------------------------------------------------+
//| Create / verify log file with header                             |
//+------------------------------------------------------------------+
void InitLogFile()
{
   string dateStr = TimeToString(g_LastDate, TIME_DATE);
   StringReplace(dateStr, ".", "-");
   
   g_CurrentFile = CSVFolder + "\\" + "ml_tradelog_" + dateStr + ".csv";
   
   if(FileIsExist(g_CurrentFile))
   {
      Print("Appending to existing file: ", g_CurrentFile);
      return;
   }
   
   int handle = FileOpen(g_CurrentFile, FILE_WRITE | FILE_CSV | FILE_ANSI, ",");
   if(handle == INVALID_HANDLE)
   {
      Print("CRITICAL ERROR: Cannot create log file: ", g_CurrentFile);
      return;
   }
   
   FileWrite(handle,
      "Timestamp",         "Event_Type",       "Ticket",
      "Deal_Ticket",       "Symbol",            "Direction",
      "Volume",            "Price_Open",        "Price_Event",
      "SL_Old",            "SL_New",            "TP_Old",
      "TP_New",            "Profit_Float",      "Profit_Realized",
      "Commission",        "Swap",              "Duration_Minutes",
      "Magic",             "Comment",           "EMA_Fast",
      "EMA_Slow",          "Price_vs_EMA200",   "ATR",
      "Spread",            "Session",           "Day_of_Week",
      "Account_Balance",   "Account_Equity",    "Server"
   );
   
   FileClose(handle);
   Print("Created new log file: ", g_CurrentFile);
}

//+------------------------------------------------------------------+
//| Get original open price from deal history                        |
//+------------------------------------------------------------------+
double GetPositionOpenPrice(ulong posTicket)
{
   HistorySelect(0, TimeCurrent());
   uint total = HistoryDealsTotal();
   for(uint i = 0; i < total; i++)
   {
      if(HistoryDealSelect(HistoryDealGetTicket(i)))
      {
         if(HistoryDealGetInteger(HistoryDealGetTicket(i), DEAL_POSITION_ID) == (long)posTicket)
         {
            if(HistoryDealGetInteger(HistoryDealGetTicket(i), DEAL_ENTRY) == DEAL_ENTRY_IN)
               return HistoryDealGetDouble(HistoryDealGetTicket(i), DEAL_PRICE);
         }
      }
   }
   return 0;
}

//+------------------------------------------------------------------+
//| Get original open time from deal history                         |
//+------------------------------------------------------------------+
datetime GetPositionOpenTime(ulong posTicket)
{
   HistorySelect(0, TimeCurrent());
   uint total = HistoryDealsTotal();
   for(uint i = 0; i < total; i++)
   {
      ulong dTicket = HistoryDealGetTicket(i);
      if(HistoryDealSelect(dTicket))
      {
         if(HistoryDealGetInteger(dTicket, DEAL_POSITION_ID) == (long)posTicket)
         {
            if(HistoryDealGetInteger(dTicket, DEAL_ENTRY) == DEAL_ENTRY_IN)
               return (datetime)HistoryDealGetInteger(dTicket, DEAL_TIME);
         }
      }
   }
   return TimeCurrent();
}

//+------------------------------------------------------------------+
//| Detect trading session from server time                          |
//+------------------------------------------------------------------+
string GetSession()
{
   MqlDateTime dt;
   TimeToStruct(TimeCurrent(), dt);
   int hour = dt.hour;
   
   //--- Approximate UTC-based sessions
   bool london   = (hour >= 8  && hour < 17);
   bool newYork  = (hour >= 13 && hour < 22);
   bool asian    = (hour >= 0  && hour < 8) || (hour >= 23);
   
   if(london && newYork) return "OVERLAP_LN";   // London-NY overlap (most liquid)
   if(london)            return "LONDON";
   if(newYork)           return "NEWYORK";
   if(asian)             return "ASIAN";
   
   return "OFF";
}

//+------------------------------------------------------------------+
//| Day of week string                                               |
//+------------------------------------------------------------------+
string GetDayOfWeek(datetime t)
{
   MqlDateTime dt;
   TimeToStruct(t, dt);
   string days[] = {"SUN","MON","TUE","WED","THU","FRI","SAT"};
   return days[dt.day_of_week];
}
//+------------------------------------------------------------------+