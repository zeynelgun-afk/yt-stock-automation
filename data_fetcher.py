import requests
import logging
from typing import Dict, Any, List
from config import FMP_API_KEY

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BASE_FMP_URL = "https://financialmodelingprep.com/api/v3"

class FMPDataFetcher:
    def __init__(self, api_key: str = FMP_API_KEY):
        self.api_key = api_key

    def get_top_gainers(self) -> List[Dict[str, Any]]:
        """Fetches top gainers stocks of the day."""
        if self.api_key:
            endpoints = [
                f"{BASE_FMP_URL}/stock_market/gainers?apikey={self.api_key}",
                f"{BASE_FMP_URL}/gainers?apikey={self.api_key}",
                f"{BASE_FMP_URL}/stock/gainers?apikey={self.api_key}"
            ]
            for url in endpoints:
                try:
                    res = requests.get(url, timeout=10)
                    if res.status_code == 200:
                        data = res.json()
                        if isinstance(data, list) and len(data) > 0:
                            return data[:5]
                except Exception as e:
                    logger.error(f"Error fetching gainers from {url}: {e}")

        # Fallback default data
        return [
            {"symbol": "NVDA", "name": "NVIDIA Corp", "price": 125.40, "changesPercentage": 6.85},
            {"symbol": "TSLA", "name": "Tesla Inc", "price": 248.20, "changesPercentage": 5.12},
            {"symbol": "AAPL", "name": "Apple Inc", "price": 224.30, "changesPercentage": 3.40}
        ]

    def get_top_losers(self) -> List[Dict[str, Any]]:
        """Fetches top loser stocks of the day."""
        if self.api_key:
            endpoints = [
                f"{BASE_FMP_URL}/stock_market/losers?apikey={self.api_key}",
                f"{BASE_FMP_URL}/losers?apikey={self.api_key}"
            ]
            for url in endpoints:
                try:
                    res = requests.get(url, timeout=10)
                    if res.status_code == 200:
                        data = res.json()
                        if isinstance(data, list) and len(data) > 0:
                            return data[:5]
                except Exception as e:
                    logger.error(f"Error fetching losers: {e}")

        return [
            {"symbol": "INTC", "name": "Intel Corp", "price": 31.10, "changesPercentage": -4.25},
            {"symbol": "AMD", "name": "Advanced Micro Devices", "price": 152.00, "changesPercentage": -3.80}
        ]

    def get_market_news(self, limit: int = 5) -> List[Dict[str, Any]]:
        """Fetches latest stock market news."""
        if self.api_key:
            url = f"{BASE_FMP_URL}/stock_news?limit={limit}&apikey={self.api_key}"
            try:
                res = requests.get(url, timeout=10)
                if res.status_code == 200:
                    data = res.json()
                    if isinstance(data, list) and len(data) > 0:
                        return data
            except Exception as e:
                logger.error(f"Error fetching market news: {e}")

        return [
            {"title": "Tech Rally Drives S&P 500 to All-Time Highs", "text": "Nvidia and Apple lead the market surge amid strong earnings expectation."},
            {"title": "Fed Signals Potential Interest Rate Cuts", "text": "Federal Reserve officials hint at easing inflation pressure."}
        ]

    def get_fear_greed_index(self) -> Dict[str, Any]:
        """Fetches current Fear & Greed Index."""
        try:
            res = requests.get("https://production.dataviz.cnn.io/index/fearandgreed/graphdata", timeout=5)
            if res.status_code == 200:
                data = res.json()
                score = round(data.get("fear_and_greed", {}).get("score", 65))
                rating = data.get("fear_and_greed", {}).get("rating", "greed")
                return {"score": score, "rating": rating}
        except Exception as e:
            logger.error(f"Error fetching Fear/Greed: {e}")
        return {"score": 65, "rating": "greed"}

if __name__ == "__main__":
    fetcher = FMPDataFetcher()
    print("Gainers:", fetcher.get_top_gainers())
    print("Fear/Greed:", fetcher.get_fear_greed_index())
