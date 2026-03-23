//+------------------------------------------------------------------+
//|                 MA Crossover Impulse Data Collector              |
//|                 Logs impulse in points and percent               |
//|                 This EA does NOT trade                           |
//+------------------------------------------------------------------+
#property strict
#property copyright "You"
#property version   "1.00"

//--- inputs
input ENUM_MA_METHOD      InpMAMethod          = MODE_SMA;
input int                 InpMAPeriod          = 50;
input ENUM_APPLIED_PRICE  InpPrice             = PRICE_CLOSE;
input int                 InpMAShift           = 0;
input ENUM_TIMEFRAMES     InpTimeframe         = PERIOD_CURRENT;

// threshold-reversal tracking parameters
input double              InpThresholdPoints   = 10.0;   // Price distance for threshold
input double              InpReversalPercent   = 30.0;   // % of actual move for reversal

input string              InpFileName          = "ma_impulse_data.csv";

//--- global variables
int      maHandle        = INVALID_HANDLE;
int      fileHandle      = INVALID_HANDLE;

bool     active          = false;      // tracking after a crossover?
int      crossDirection  = 0;          // +1 bullish, -1 bearish
double   crossPrice      = 0.0;
datetime crossTime       = 0;

// overall extreme (highest high for bullish, lowest low for bearish)
double   sequenceExtremePrice = 0.0;
datetime sequenceExtremeTime  = 0;

// crossover end time (time when opposite side close happens)
datetime crossEndTime         = 0;

// threshold-reversal tracking variables
bool     thresholdHit         = false;       // has threshold been hit?
double   thresholdHitPrice    = 0.0;         // price when threshold was hit
datetime thresholdHitTime      = 0;           // time when threshold was hit
double   actualMoveAtThreshold = 0.0;        // actual price move when threshold was hit

bool     reversalTriggered    = false;       // has reversal % been hit?
double   reversalTriggerPrice = 0.0;         // price when reversal was triggered
datetime reversalTriggerTime  = 0;           // time when reversal was triggered
double   reversalExtremePrice = 0.0;         // lowest/highest price during reversal
datetime reversalExtremeTime  = 0;           // time of extreme during reversal
datetime reversalTrackingStart = 0;          // time when reversal tracking started (to ensure at least 2 bars)

// cached offset between server time and UTC (GMT)
int      serverToUtcOffsetSec = 0;

//+------------------------------------------------------------------+
int OnInit()
{
   //--- cache server->UTC offset (in seconds)
   serverToUtcOffsetSec = (int)(TimeGMT() - TimeCurrent());

   //--- create MA handle
   maHandle = iMA(_Symbol, InpTimeframe,
                  InpMAPeriod, InpMAShift, InpMAMethod, InpPrice);
   if(maHandle == INVALID_HANDLE)
   {
      Print("MA_Impulse_Logger: failed to create MA handle. Error: ", GetLastError());
      return(INIT_FAILED);
   }

   //--- open / create CSV (comma separated) file
   // FILE_READ | FILE_WRITE lets us append without losing existing data.
   fileHandle = FileOpen(InpFileName,
                         FILE_READ | FILE_WRITE | FILE_CSV | FILE_ANSI,
                         ',');
   if(fileHandle == INVALID_HANDLE)
   {
      Print("MA_Impulse_Logger: failed to open file: ", InpFileName,
            " Error: ", GetLastError());
      return(INIT_FAILED);
   }

    //--- if file is new, write header
    if(FileSize(fileHandle) == 0)
    {
       FileWrite(fileHandle,
          "symbol",
          "session",
          "cross_time",
          "cross_end_time",
          "cross_price",
          "cross_type",
          "threshold_points",
          "reversal_percent",
          "threshold_index",
          "threshold_hit_time",
          "threshold_hit_price",
          "actual_move_at_threshold",
          "reversal_trigger_time",
          "reversal_trigger_price",
          "reversal_extreme_price",
          "reversal_extreme_time",
          "reversal_move_points",
          "reversal_move_percent",
          "is_final"
       );
    }

   //--- move to end of file for appending
   FileSeek(fileHandle, 0, SEEK_END);

   Print("MA_Impulse_Logger initialized. Logging to file: ", InpFileName);
   return(INIT_SUCCEEDED);
}

//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   if(fileHandle != INVALID_HANDLE)
      FileClose(fileHandle);
   if(maHandle != INVALID_HANDLE)
      IndicatorRelease(maHandle);
}

//+------------------------------------------------------------------+
void OnTick()
{
   static datetime lastBarTime = 0;

   //--- get last 3 bars on selected timeframe
   MqlRates rates[3];
   if(CopyRates(_Symbol, InpTimeframe, 0, 3, rates) != 3)
      return;

   //--- check new bar
   if(rates[0].time != lastBarTime)
   {
      // new bar formed, check crossovers on the closed bar
      CheckForCrossover(rates);
      lastBarTime = rates[0].time;
   }

   //--- if we are tracking an active crossover, update impulse
   if(active)
      UpdateImpulse();
}

//+------------------------------------------------------------------+
//| Detect MA crossovers on closed bars                              |
//+------------------------------------------------------------------+
void CheckForCrossover(const MqlRates &rates[])
{
   double ma[3];
   if(CopyBuffer(maHandle, 0, 0, 3, ma) != 3)
      return;

   // indexes:
   // rates[0] -> current forming bar
   // rates[1] -> just closed bar
   // rates[2] -> previous closed bar
   double close0 = rates[1].close; // just closed
   double ma0    = ma[1];

   // side of price relative to MA for the just‑closed candle
   int side = 0;
   if(close0 > ma0)  side = +1;   // above MA -> bullish side
   if(close0 < ma0)  side = -1;   // below MA -> bearish side

   // if we are not yet tracking anything and we have a clear side, start it
   if(!active && side != 0)
   {
      StartNewCrossover(side, close0, rates[1].time);
      return;
   }

   // if we are tracking and the closed candle is on the opposite side,
   // then the current crossover ENDS here and a new one immediately BEGINS
   if(active && side != 0 && side != crossDirection)
   {
      // record crossover end time at this closed bar
      crossEndTime = rates[1].time;
      // end previous sequence and write its data
      FinalizeSequence(true);
      // start new sequence from this closed candle
      StartNewCrossover(side, close0, rates[1].time);
   }
}

//+------------------------------------------------------------------+
//| Start tracking a new crossover                                   |
//+------------------------------------------------------------------+
void StartNewCrossover(int direction, double price, datetime timeCross)
{
    // if already active, finalize the previous sequence
    if(active)
       FinalizeSequence(false);

    active            = true;
    crossDirection    = direction;
    crossPrice        = price;
    crossTime         = timeCross;

    // reset threshold-reversal tracking variables
    thresholdHit           = false;
    thresholdHitPrice      = 0.0;
    thresholdHitTime       = 0;
    actualMoveAtThreshold  = 0.0;
    reversalTriggered      = false;
    reversalTriggerPrice   = 0.0;
    reversalTriggerTime    = 0;
    reversalExtremePrice   = 0.0;
    reversalExtremeTime    = 0;
    reversalTrackingStart  = 0;

    // reset extreme tracking
    sequenceExtremePrice = price;
    sequenceExtremeTime  = timeCross;

    Print("MA_Impulse_Logger: new crossover dir=", direction,
          " price=", DoubleToString(price, _Digits),
          " time=", TimeToString(timeCross, TIME_DATE|TIME_SECONDS));
}

//+------------------------------------------------------------------+
//| Update impulse on every tick                                     |
//+------------------------------------------------------------------+
void UpdateImpulse()
{
    double price = SymbolInfoDouble(_Symbol, SYMBOL_BID);
    double point = _Point;
    datetime currentTime = TimeCurrent();

    if(point <= 0.0)
       return;

    // update true extreme using bar high/low of current bar
    double barHigh = iHigh(_Symbol, InpTimeframe, 0);
    double barLow  = iLow(_Symbol,  InpTimeframe, 0);

    // compute favorable move using true extremes (not synthetic levels),
    // and keep track of the max favorable extreme price and its time
    double favorableMovePoints = 0.0;
    if(crossDirection == +1) // bullish
    {
       // update bullish extreme as highest high seen since crossover
       if(barHigh > sequenceExtremePrice || sequenceExtremePrice == 0.0)
       {
          sequenceExtremePrice = barHigh;
          sequenceExtremeTime  = currentTime;
       }

       if(sequenceExtremePrice > crossPrice)
          favorableMovePoints = (sequenceExtremePrice - crossPrice) / point;
    }
    else if(crossDirection == -1) // bearish
    {
       // update bearish extreme as lowest low seen since crossover
       if(barLow < sequenceExtremePrice || sequenceExtremePrice == 0.0)
       {
          sequenceExtremePrice = barLow;
          sequenceExtremeTime  = currentTime;
       }

       if(sequenceExtremePrice < crossPrice)
          favorableMovePoints = (crossPrice - sequenceExtremePrice) / point;
    }

    //-----------------------------------------------------------
    // THRESHOLD-REVERSAL TRACKING LOGIC
    //-----------------------------------------------------------
    
    double favorableMovePrice = favorableMovePoints * point; // convert to price units

    // PHASE 1: Check if threshold is hit for the first time
    if(!thresholdHit && favorableMovePrice >= InpThresholdPoints)
    {
       // Threshold hit for first time
       thresholdHit = true;
       thresholdHitPrice = sequenceExtremePrice;
       thresholdHitTime = currentTime;
       actualMoveAtThreshold = favorableMovePrice;
       
       // Initialize reversal tracking
       reversalTrackingStart = currentTime;
       reversalExtremePrice = 0.0;
       reversalExtremeTime = 0;
       
       Print("MA_Impulse_Logger: Threshold hit. Price=", DoubleToString(thresholdHitPrice, _Digits),
             " Move=", DoubleToString(actualMoveAtThreshold, _Digits),
             " Starting reversal tracking...");
    }
    
    // PHASE 2: Track reversal after threshold is hit
    if(thresholdHit)
    {
       // Update thresholdHitPrice to track the extreme reached
       thresholdHitPrice = sequenceExtremePrice;
       actualMoveAtThreshold = favorableMovePrice;
       
       // Only track reversal after at least 1 bar has passed
       if(reversalTrackingStart > 0 && currentTime > reversalTrackingStart)
       {
          // For bullish: track lowest low during reversal
          // For bearish: track highest high during reversal
          if(crossDirection == +1)
          {
             if(reversalExtremePrice == 0.0)
             {
                reversalExtremePrice = barLow;
                reversalExtremeTime = currentTime;
             }
             else if(barLow < reversalExtremePrice)
             {
                reversalExtremePrice = barLow;
                reversalExtremeTime = currentTime;
             }
          }
          else // bearish
          {
             if(reversalExtremePrice == 0.0)
             {
                reversalExtremePrice = barHigh;
                reversalExtremeTime = currentTime;
             }
             else if(barHigh > reversalExtremePrice)
             {
                reversalExtremePrice = barHigh;
                reversalExtremeTime = currentTime;
             }
          }
          
          // Check if reversal % is hit
          double reversalAmount = actualMoveAtThreshold * InpReversalPercent / 100.0;
          
          if(crossDirection == +1) // bullish
          {
             double currentReversal = thresholdHitPrice - barLow;
             if(currentReversal >= reversalAmount)
             {
                // Reversal % hit - SAVE to CSV
                reversalTriggerPrice = barLow;
                reversalTriggerTime = currentTime;
                WriteThresholdReversal(1);
                
                Print("MA_Impulse_Logger: Bullish reversal complete. Rev=", DoubleToString(currentReversal, _Digits));
                
                // Reset for next cycle
                thresholdHit = false;
                reversalExtremePrice = 0.0;
                reversalExtremeTime = 0;
                reversalTrackingStart = 0;
             }
          }
          else // bearish
          {
             double currentReversal = barHigh - thresholdHitPrice;
             if(currentReversal >= reversalAmount)
             {
                // Reversal % hit - SAVE to CSV
                reversalTriggerPrice = barHigh;
                reversalTriggerTime = currentTime;
                WriteThresholdReversal(1);
                
                Print("MA_Impulse_Logger: Bearish reversal complete. Rev=", DoubleToString(currentReversal, _Digits));
                
                // Reset for next cycle
                thresholdHit = false;
                reversalExtremePrice = 0.0;
                reversalExtremeTime = 0;
                reversalTrackingStart = 0;
             }
          }
       }
    }
}


//+------------------------------------------------------------------+
//| Finalize a sequence (e.g. when opposite crossover appears)       |
//| Here called only when starting a new crossover.                  |
//+------------------------------------------------------------------+
void FinalizeSequence(bool oppositeCross)
{
    if(!active)
       return;

    // If we have an active threshold that was being tracked, save it now
    if(thresholdHit)
    {
       // Set crossEndTime for this final row
       if(crossEndTime == 0)
          crossEndTime = TimeCurrent();
       
       // Save the pending threshold-reversal as final
       WriteThresholdReversal(1);
    }
    // If no threshold was ever hit during the crossover, write a row with zeros
    else if(!thresholdHit)
    {
       // Set crossEndTime for this final row
       if(crossEndTime == 0)
          crossEndTime = TimeCurrent();
       
       // Write one final row with all zeros to indicate no threshold was hit
       string crossTypeText = (crossDirection == 1) ? "BULLISH" : "BEARISH";
       
       string sessionName;
       datetime utcTime = crossTime + serverToUtcOffsetSec;
       MqlDateTime tm;
       TimeToStruct(utcTime, tm);
       int hour = tm.hour;
       if((hour >= 21 && hour <= 23) || (hour >= 0 && hour < 6))
          sessionName = "SYDNEY";
       else if(hour >= 23 || hour < 8)
          sessionName = "TOKYO";
       else if(hour >= 8 && hour < 13)
          sessionName = "LONDON";
       else if(hour >= 13 && hour < 22)
          sessionName = "NEW_YORK";
       else
          sessionName = "OFF_SESSION";

       FileWrite(fileHandle,
          _Symbol,                                                // symbol
          sessionName,                                            // session
          TimeToString(crossTime, TIME_DATE|TIME_SECONDS),        // cross_time
          TimeToString(crossEndTime, TIME_DATE|TIME_SECONDS),     // cross_end_time
          DoubleToString(crossPrice, _Digits),                    // cross_price
          crossTypeText,                                          // cross_type
          InpThresholdPoints,                                      // threshold_points
          InpReversalPercent,                                     // reversal_percent
          0,                                                      // threshold_index (0 = no threshold hit)
          "",                                                     // threshold_hit_time
          "",                                                     // threshold_hit_price
          0.0,                                                   // actual_move_at_threshold
          "",                                                     // reversal_trigger_time
          "",                                                     // reversal_trigger_price
          "",                                                     // reversal_extreme_price
          "",                                                     // reversal_extreme_time
          0.0,                                                   // reversal_move_points
          0.0,                                                   // reversal_move_percent
          1                                                       // is_final (1 = end of crossover)
       );

       FileFlush(fileHandle);
    }

    active = false;
}

//+------------------------------------------------------------------+
//| Write threshold-reversal data to CSV                            |
//+------------------------------------------------------------------+
void WriteThresholdReversal(int thresholdIndex)
{
    if(fileHandle == INVALID_HANDLE)
       return;

    // reversal_trigger_time is when the NEXT threshold was breached (current time)
    // reversal_extreme_price/time is the extreme reached during reversal (before next threshold breach)
    
    // Calculate reversal move: from threshold hit price to the extreme reached during reversal
    double reversalMovePoints = 0.0;
    if(thresholdHitPrice != 0.0 && reversalExtremePrice != 0.0)
    {
       if(crossDirection == +1) // bullish - extreme is lowest
          reversalMovePoints = thresholdHitPrice - reversalExtremePrice;
       else // bearish - extreme is highest
          reversalMovePoints = reversalExtremePrice - thresholdHitPrice;
    }

    // Calculate reversal percent (based on actual move at threshold)
    double reversalPercent = 0.0;
    if(actualMoveAtThreshold > 0.0)
       reversalPercent = (reversalMovePoints / actualMoveAtThreshold) * 100.0;

    // human-readable labels for direction fields
    string crossTypeText;
    if(crossDirection == 1)
       crossTypeText = "BULLISH";
    else if(crossDirection == -1)
       crossTypeText = "BEARISH";
    else
       crossTypeText = "NONE";

    // derive session name based on UTC time
    string sessionName;
    datetime utcTime = thresholdHitTime + serverToUtcOffsetSec;
    MqlDateTime tm;
    TimeToStruct(utcTime, tm);
    int hour = tm.hour;

    // Four main sessions, using standard UTC windows:
    if((hour >= 21 && hour <= 23) || (hour >= 0 && hour < 6))
       sessionName = "SYDNEY";
    else if(hour >= 23 || hour < 8)
       sessionName = "TOKYO";
    else if(hour >= 8 && hour < 13)
       sessionName = "LONDON";
    else if(hour >= 13 && hour < 22)
       sessionName = "NEW_YORK";
    else
       sessionName = "OFF_SESSION";

    FileWrite(fileHandle,
       _Symbol,                                                // symbol
       sessionName,                                            // session
       TimeToString(crossTime, TIME_DATE|TIME_SECONDS),        // cross_time
       TimeToString(crossEndTime, TIME_DATE|TIME_SECONDS),     // cross_end_time
       DoubleToString(crossPrice, _Digits),                    // cross_price
       crossTypeText,                                          // cross_type
       InpThresholdPoints,                                      // threshold_points
       InpReversalPercent,                                     // reversal_percent
       thresholdIndex,                                         // threshold_index
       TimeToString(thresholdHitTime, TIME_DATE|TIME_SECONDS), // threshold_hit_time
       DoubleToString(thresholdHitPrice, _Digits),            // threshold_hit_price
       actualMoveAtThreshold,                                  // actual_move_at_threshold
       TimeToString(reversalTriggerTime, TIME_DATE|TIME_SECONDS), // reversal_trigger_time
       DoubleToString(reversalTriggerPrice, _Digits),          // reversal_trigger_price
       DoubleToString(reversalExtremePrice, _Digits),         // reversal_extreme_price (lowest/highest during reversal)
       TimeToString(reversalExtremeTime, TIME_DATE|TIME_SECONDS), // reversal_extreme_time
       reversalMovePoints,                                     // reversal_move_points
       reversalPercent,                                        // reversal_move_percent
       0                                                       // is_final (0 = not end of crossover)
    );

     FileFlush(fileHandle);
}

