//+------------------------------------------------------------------+
//| FixSymbol.mq5                                                    |
//| Lists every symbol the terminal knows that matches a filter,     |
//| then force-selects the target into Market Watch. The Strategy    |
//| Tester only offers symbols present in Market Watch, so a symbol  |
//| can exist on disk and still be unpickable.                       |
//+------------------------------------------------------------------+
#property strict
#property script_show_inputs

input string Filter = "VOO";      // substring to list
input string Target = "VOO_D1";   // symbol to force into Market Watch

void OnStart()
{
   Print("===== FixSymbol =====");

   int total = SymbolsTotal(false);   // false = all known, not just Market Watch
   PrintFormat("terminal knows %d symbols total", total);

   int hits = 0;
   for(int i = 0; i < total; i++)
   {
      string name = SymbolName(i, false);
      if(StringFind(name, Filter) < 0)
         continue;

      hits++;
      bool inWatch = SymbolInfoInteger(name, SYMBOL_SELECT);
      bool custom  = SymbolInfoInteger(name, SYMBOL_CUSTOM);
      // No Bars()/history call here on purpose: on an unsynced broker symbol
      // with no server connection it blocks for minutes per symbol.
      PrintFormat("  [%s] path='%s' custom=%s inMarketWatch=%s",
                  name,
                  SymbolInfoString(name, SYMBOL_PATH),
                  custom  ? "yes" : "no",
                  inWatch ? "YES" : "no");
   }
   if(hits == 0)
      Print("  no symbol matched '", Filter, "'");

   //--- force the target visible ---
   if(!SymbolSelect(Target, true))
      Print("SymbolSelect(", Target, ") FAILED, error ", GetLastError());
   else
   {
      Print(Target, " selected into Market Watch");
      // Safe to ask here: the target is a custom symbol whose bars are
      // already on disk, so this returns without a server round-trip.
      PrintFormat("%s: D1 bars=%d  first=%s",
                  Target,
                  Bars(Target, PERIOD_D1),
                  TimeToString((datetime)SeriesInfoInteger(Target, PERIOD_D1, SERIES_FIRSTDATE), TIME_DATE));
   }
   Print("===== end =====");
}
//+------------------------------------------------------------------+
