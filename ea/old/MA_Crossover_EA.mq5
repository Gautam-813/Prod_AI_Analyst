#property copyright ""
#property link      ""
#property version   "1.00"
#property strict

#include <Trade/Trade.mqh>

input group "=== MA Settings ==="
input int MaPeriod = 50;
input ENUM_MA_METHOD MaMethod = MODE_EMA;
input ENUM_APPLIED_PRICE MaAppliedPrice = PRICE_CLOSE;

input group "=== Timeframe ==="
input ENUM_TIMEFRAMES Timeframe = PERIOD_H1;

input group "=== Trade Settings ==="
input double LotSize = 0.1;
input int MagicNumber = 20260317;

input group "=== TP/SL Settings (in price units) ==="
input double TakeProfit = 100;
input double StopLoss = 50;
input double ConfirmationDistance = 20;

CTrade trade;
datetime lastCandleTime = 0;
double lastSignalCandlePrice = 0;
bool signalType = false;
int maHandle = INVALID_HANDLE;

int OnInit()
{
   maHandle = iMA(_Symbol, Timeframe, MaPeriod, 0, MaMethod, MaAppliedPrice);
   if(maHandle == INVALID_HANDLE)
   {
      Alert("Failed to create MA indicator!");
      return INIT_FAILED;
   }
   
   if(LotSize <= 0)
   {
      Alert("Invalid LotSize!");
      return INIT_PARAMETERS_INCORRECT;
   }
   
   if(MaPeriod <= 0)
   {
      Alert("Invalid MaPeriod!");
      return INIT_PARAMETERS_INCORRECT;
   }
   
   trade.SetExpertMagicNumber(MagicNumber);
   
   ENUM_ORDER_TYPE_FILLING fillMode = ORDER_FILLING_FOK;
   long fillingMode = SymbolInfoInteger(_Symbol, SYMBOL_FILLING_MODE);
   
   if((fillingMode & SYMBOL_FILLING_IOC) != 0)
      fillMode = ORDER_FILLING_IOC;
   else if((fillingMode & SYMBOL_FILLING_FOK) != 0)
      fillMode = ORDER_FILLING_FOK;
   else
      fillMode = ORDER_FILLING_BOC;
   
   trade.SetTypeFilling(fillMode);
   trade.SetDeviationInPoints(10);
   
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   if(maHandle != INVALID_HANDLE)
      IndicatorRelease(maHandle);
}

void OnTick()
{
   if(!IsNewCandle())
      return;
   
   if(PositionsTotal() > 0)
   {
      CheckSL();
      return;
   }
   
   double maArray[];
   ArraySetAsSeries(maArray, true);
   if(CopyBuffer(maHandle, 0, 1, 2, maArray) < 2)
      return;
   
   double ma = maArray[0];
   double maPrev = maArray[1];
   double close1 = iClose(_Symbol, Timeframe, 1);
   double close2 = iClose(_Symbol, Timeframe, 2);
   double high1 = iHigh(_Symbol, Timeframe, 1);
   double low1 = iLow(_Symbol, Timeframe, 1);
   
   bool bullishCrossover = (close2 < maPrev && close1 > ma);
   bool bearishCrossover = (close2 > maPrev && close1 < ma);
   
   if(bullishCrossover)
   {
      lastSignalCandlePrice = high1;
      signalType = true;
   }
   else if(bearishCrossover)
   {
      lastSignalCandlePrice = low1;
      signalType = false;
   }
   
   if(lastSignalCandlePrice > 0)
   {
      double currentPrice = SymbolInfoDouble(_Symbol, SYMBOL_BID);
      double entryPrice = 0;
      
      if(signalType)
      {
         entryPrice = lastSignalCandlePrice + ConfirmationDistance;
         if(currentPrice > entryPrice)
         {
            ExecuteBuy();
            lastSignalCandlePrice = 0;
         }
      }
      else
      {
         entryPrice = lastSignalCandlePrice - ConfirmationDistance;
         if(currentPrice < entryPrice)
         {
            ExecuteSell();
            lastSignalCandlePrice = 0;
         }
      }
   }
}

bool IsNewCandle()
{
   datetime currentTime = iTime(_Symbol, Timeframe, 0);
   if(currentTime != lastCandleTime)
   {
      lastCandleTime = currentTime;
      return true;
   }
   return false;
}

void ExecuteBuy()
{
   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double sl = ask - StopLoss;
   double tp = ask + TakeProfit;
   
   if(trade.Buy(LotSize, _Symbol, ask, sl, tp, "MA_Crossover_Buy"))
   {
      Print("Buy order opened: ", trade.ResultOrder());
   }
   else
   {
      Print("Buy order failed: ", trade.ResultRetcodeDescription());
   }
}

void ExecuteSell()
{
   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double sl = bid + StopLoss;
   double tp = bid - TakeProfit;
   
   if(trade.Sell(LotSize, _Symbol, bid, sl, tp, "MA_Crossover_Sell"))
   {
      Print("Sell order opened: ", trade.ResultOrder());
   }
   else
   {
      Print("Sell order failed: ", trade.ResultRetcodeDescription());
   }
}

void CheckSL()
{
   double maArray[];
   ArraySetAsSeries(maArray, true);
   if(CopyBuffer(maHandle, 0, 1, 1, maArray) < 1)
      return;
   
   double ma = maArray[0];
   double close1 = iClose(_Symbol, Timeframe, 1);
   
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      if(PositionSelectByTicket(i))
      {
         if(PositionGetSymbol(i) == _Symbol && PositionGetInteger(POSITION_MAGIC) == MagicNumber)
         {
            ENUM_POSITION_TYPE posType = (ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);
            
            if(posType == POSITION_TYPE_BUY)
            {
               if(close1 < ma)
               {
                  ClosePosition(PositionGetTicket(i));
                  Print("BUY closed - Opposite crossover (bearish)");
               }
            }
            else if(posType == POSITION_TYPE_SELL)
            {
               if(close1 > ma)
               {
                  ClosePosition(PositionGetTicket(i));
                  Print("SELL closed - Opposite crossover (bullish)");
               }
            }
         }
      }
   }
}

void ClosePosition(ulong ticket)
{
   if(trade.PositionClose(ticket))
   {
      Print("Position closed: ", ticket);
   }
   else
   {
      Print("Failed to close position: ", ticket, " - ", trade.ResultRetcodeDescription());
   }
}
