import logging
import time
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests

from config import FMP_API_KEY

NY_TZ = ZoneInfo("America/New_York")


def ny_now() -> datetime:
    """Market time. All 'what day is it' logic must use this, not the naive
    datetime.now(): CI runners are UTC, where every ET evening is already
    'tomorrow' — earnings and event-day checks silently used the wrong day."""
    return datetime.now(NY_TZ)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Legacy /api/v3 routes are permanently blocked by FMP (403 "Legacy Endpoint").
# All calls must use the /stable base. See FMP_SKILL.md for the endpoint catalog.
FMP_BASE_URL = "https://financialmodelingprep.com/stable"

INDEX_SYMBOLS = "^GSPC,^IXIC,^DJI,^VIX"

# CNN blocks default python-requests User-Agent
CNN_FEAR_GREED_URL = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0"
}


class FMPDataError(Exception):
    """Raised when live market data cannot be fetched.

    The pipeline must STOP on this error. Publishing a video with stale or
    fabricated market numbers would destroy channel credibility, so there is
    deliberately no fake-data fallback anywhere in this module.
    """


class FMPDataFetcher:
    def __init__(self, api_key: str = FMP_API_KEY):
        if not api_key:
            raise FMPDataError("FMP_API_KEY is not configured (.env)")
        self.api_key = api_key

    def _get(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Any:
        params = dict(params or {})
        params["apikey"] = self.api_key
        url = f"{FMP_BASE_URL}/{endpoint}"

        # One transient blip used to forfeit the whole publishing slot; a short
        # retry is cheap. Still halt-on-failure — never fabricate data.
        last_err = ""
        for attempt in range(3):
            if attempt:
                time.sleep(3 * attempt)
            try:
                res = requests.get(url, params=params, timeout=15)
            except requests.RequestException as e:
                last_err = f"request failed: {e}"
                continue

            if res.status_code == 429 or res.status_code >= 500:
                last_err = f"HTTP {res.status_code}: {res.text[:200]}"
                continue
            if res.status_code != 200:
                raise FMPDataError(
                    f"FMP '{endpoint}' returned HTTP {res.status_code}: {res.text[:200]}"
                )

            try:
                data = res.json()
            except ValueError as e:
                # A 200 with an HTML/error body used to escape as a raw
                # JSONDecodeError, bypassing the FMPDataError abort path
                raise FMPDataError(f"FMP '{endpoint}' returned non-JSON body: {e}") from e
            if isinstance(data, dict) and "Error Message" in data:
                raise FMPDataError(f"FMP '{endpoint}' error: {data['Error Message']}")
            return data

        raise FMPDataError(f"FMP request failed for '{endpoint}' after 3 attempts: {last_err}")

    def get_top_gainers(self, limit: int = 5) -> List[Dict[str, Any]]:
        data = self._get("biggest-gainers", {"limit": 20})
        if not isinstance(data, list) or not data:
            raise FMPDataError("biggest-gainers returned no data")
        return data[:limit]

    def get_top_losers(self, limit: int = 5) -> List[Dict[str, Any]]:
        data = self._get("biggest-losers", {"limit": 20})
        if not isinstance(data, list) or not data:
            raise FMPDataError("biggest-losers returned no data")
        return data[:limit]

    def get_most_actives(self, limit: int = 5) -> List[Dict[str, Any]]:
        data = self._get("most-actives", {"limit": 20})
        if not isinstance(data, list) or not data:
            raise FMPDataError("most-actives returned no data")
        return data[:limit]

    def get_index_quotes(self) -> List[Dict[str, Any]]:
        """S&P 500, Nasdaq, Dow Jones and VIX quotes in one batch call."""
        data = self._get("batch-quote", {"symbols": INDEX_SYMBOLS})
        if not isinstance(data, list) or not data:
            raise FMPDataError("batch-quote for index symbols returned no data")
        return data

    def get_market_news(self, limit: int = 5) -> List[Dict[str, Any]]:
        """General market articles, normalized to [{'title', 'text'}]."""
        data = self._get("fmp-articles", {"limit": limit})
        if not isinstance(data, list) or not data:
            raise FMPDataError("fmp-articles returned no data")
        return [
            {"title": a.get("title", ""), "text": (a.get("content") or "")[:500]}
            for a in data[:limit]
        ]

    def get_stock_news(self, symbols: List[str], limit: int = 10) -> List[Dict[str, Any]]:
        """News for specific tickers — the 'why' behind each big move."""
        data = self._get("news/stock", {"symbols": ",".join(symbols), "limit": limit})
        if not isinstance(data, list):
            raise FMPDataError("news/stock returned invalid data")
        return data

    def get_intraday_chart(self, symbol: str, interval: str = "5min") -> List[Dict[str, Any]]:
        """Real intraday candles for the most recent trading day, oldest first.

        Fetches a few days back so weekends/holidays still yield the last session.
        """
        to_date = ny_now()
        from_date = to_date - timedelta(days=4)
        data = self._get(
            f"historical-chart/{interval}",
            {
                "symbol": symbol,
                "from": from_date.strftime("%Y-%m-%d"),
                "to": to_date.strftime("%Y-%m-%d"),
            },
        )
        if not isinstance(data, list) or not data:
            raise FMPDataError(f"No intraday data for {symbol}")

        latest_day = max(row["date"][:10] for row in data if row.get("date"))
        session = [row for row in data if row.get("date", "").startswith(latest_day)]
        session.sort(key=lambda row: row["date"])
        if not session:
            raise FMPDataError(f"No intraday session data for {symbol}")
        return session

    def _get_list(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        data = self._get(endpoint, params)
        if not isinstance(data, list):
            raise FMPDataError(f"'{endpoint}' returned invalid data")
        return data

    # --- Story-pool endpoints (all verified live Jul 2026, see FMP_SKILL.md) ---

    def get_senate_trades(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Latest Senate trade disclosures market-wide."""
        return self._get_list("senate-latest", {"limit": limit})

    def get_house_trades(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Latest House trade disclosures market-wide."""
        return self._get_list("house-latest", {"limit": limit})

    def get_insider_trades(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Latest insider (Form 4) transactions market-wide."""
        return self._get_list("insider-trading/latest", {"limit": limit})

    def get_grade_news(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Latest analyst rating changes market-wide."""
        return self._get_list("grades-latest-news", {"limit": limit})

    def get_price_target_news(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Latest analyst price-target changes market-wide."""
        return self._get_list("price-target-latest-news", {"limit": limit})

    def get_sector_performance(self) -> List[Dict[str, Any]]:
        """Sector daily average change. Falls back a few days for weekends/holidays."""
        for days_back in range(5):
            date = (ny_now() - timedelta(days=days_back)).strftime("%Y-%m-%d")
            data = self._get_list("sector-performance-snapshot", {"date": date})
            if data:
                return data
        raise FMPDataError("sector-performance-snapshot returned no data for the last 5 days")

    def get_earnings_calendar(self, days_ahead: int = 7) -> List[Dict[str, Any]]:
        """Earnings from today through `days_ahead` days out."""
        today = ny_now()
        return self._get_list("earnings-calendar", {
            "from": today.strftime("%Y-%m-%d"),
            "to": (today + timedelta(days=days_ahead)).strftime("%Y-%m-%d"),
        })

    def get_economic_calendar(self, days_ahead: int = 3) -> List[Dict[str, Any]]:
        """Economic events from today through `days_ahead` days out."""
        today = ny_now()
        return self._get_list("economic-calendar", {
            "from": today.strftime("%Y-%m-%d"),
            "to": (today + timedelta(days=days_ahead)).strftime("%Y-%m-%d"),
        })

    def get_aftermarket_quote(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Pre/post-market quote for one symbol; None if unavailable."""
        data = self._get_list("aftermarket-quote", {"symbol": symbol})
        return data[0] if data else None

    def get_price_change(self, symbol: str) -> Optional[Dict[str, Any]]:
        """% change over 1D/5D/1M/... — weekly context for a mover."""
        data = self._get_list("stock-price-change", {"symbol": symbol})
        return data[0] if data else None

    def get_reddit_trending(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Top WSB tickers from ApeWisdom (free, no key). Optional enrichment:
        returns [] on failure — never invents sentiment data."""
        try:
            res = requests.get(
                "https://apewisdom.io/api/v1.0/filter/wallstreetbets/page/1",
                headers=BROWSER_HEADERS, timeout=15,
            )
            if res.status_code == 200:
                return res.json().get("results", [])[:limit]
            logger.warning(f"ApeWisdom fetch failed: HTTP {res.status_code}")
        except Exception as e:
            logger.warning(f"ApeWisdom fetch failed: {e}")
        return []

    def get_fear_greed_index(self) -> Optional[Dict[str, Any]]:
        """CNN Fear & Greed. Optional enrichment: returns None on failure
        (the pipeline may continue without it, but must never invent a score)."""
        try:
            res = requests.get(CNN_FEAR_GREED_URL, headers=BROWSER_HEADERS, timeout=10)
            if res.status_code == 200:
                fg = res.json().get("fear_and_greed", {})
                score = fg.get("score")
                rating = fg.get("rating")
                if score is not None and rating:
                    return {"score": round(score), "rating": rating}
            logger.warning(f"Fear/Greed fetch failed: HTTP {res.status_code}")
        except Exception as e:
            logger.warning(f"Fear/Greed fetch failed: {e}")
        return None


if __name__ == "__main__":
    fetcher = FMPDataFetcher()
    print("Gainers:", fetcher.get_top_gainers(3))
    print("Indexes:", [(q["symbol"], q.get("price")) for q in fetcher.get_index_quotes()])
    intraday = fetcher.get_intraday_chart("NVDA")
    print(f"NVDA intraday points: {len(intraday)} (last: {intraday[-1]})")
    print("Fear/Greed:", fetcher.get_fear_greed_index())
