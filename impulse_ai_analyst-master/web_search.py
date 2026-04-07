
import pandas as pd
from datetime import datetime
from duckduckgo_search import DDGS

def run_web_search(query: str, max_results=5):
    """
    Performs a live web search using DuckDuckGo.
    Returns a list of dictionaries with title, href, and body.
    """
    print(f"🔍 Searching the Web for: {query}...")
    results = []
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
        return results
    except Exception as e:
        print(f"❌ Web Search Error: {e}")
        return []

def get_market_news(symbol: str, max_results=5):
    """
    Specialized search for financial news on a symbol.
    """
    query = f"{symbol} stock market financial news latest"
    return run_web_search(query, max_results=max_results)

def analyze_sentiment(results):
    """
    A simple rule-based sentiment check on search snippets.
    This can be replaced/enhanced by your AI model.
    """
    if not results:
        return "Neutral (No Data)"
    
    positive_words = ["bullish", "growth", "higher", "recovering", "upside", "buy", "gain"]
    negative_words = ["bearish", "fall", "lower", "drop", "downside", "sell", "loss", "recession"]
    
    score = 0
    for r in results:
        text = (r['title'] + " " + r['body']).lower()
        score += sum(1 for w in positive_words if w in text)
        score -= sum(1 for w in negative_words if w in text)
    
    if score > 2: return "Strong Bullish 🚀"
    if score > 0: return "Slightly Bullish 📈"
    if score < -2: return "Strong Bearish 📉"
    if score < 0: return "Slightly Bearish 📉"
    return "Neutral ⚖️"

if __name__ == "__main__":
    # Test
    res = get_market_news("XAUUSD")
    for r in res:
        print(f"- {r['title']} ({r['href']})")
    print(f"\nFinal Sentiment Estimate: {analyze_sentiment(res)}")
