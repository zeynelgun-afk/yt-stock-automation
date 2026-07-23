---
name: fmp-integration
description: Comprehensive guide for integrating Financial Modeling Prep (FMP) API, covering stable endpoints, migration from legacy versions, and usage examples. Use this skill whenever Claude needs to fetch real financial data from FMP API including stock quotes, financial statements, technical indicators, earnings data, analyst estimates, screener, news, insider trading, ETF holdings, economic calendar, and more. This is the master reference for ALL FMP API calls.
---

# FMP API Integration — Premium Plan Reference

> **Last verified**: February 2026 | **Plan**: Premium | **Base URL**: `https://financialmodelingprep.com/stable/`

---

## Authentication

```
https://financialmodelingprep.com/stable/quote?symbol=AAPL&apikey=YOUR_API_KEY
```

API key always goes as `apikey` query parameter. Key is stored in user memory.

---

## Plan Limits (Premium)

| Item | Value |
|------|-------|
| Daily calls | 2,500 |
| Calls per minute | 750 |
| Bandwidth (30-day) | 50GB |
| Historical data | 30+ years |
| Coverage | US, UK, Canada |

> **⚠️ CRITICAL**: Legacy `/api/v3/` and `/api/v4/` routes are **completely blocked** (403 "Legacy Endpoint" error). **Always use `/stable/` only.**

---

## Standard Python Pattern

```python
import requests

FMP_API_KEY = "YOUR_API_KEY"  # From user memory
FMP_BASE = "https://financialmodelingprep.com/stable"

def fmp_get(endpoint, params=None):
    if params is None:
        params = {}
    params['apikey'] = FMP_API_KEY
    url = f"{FMP_BASE}/{endpoint}"
    try:
        r = requests.get(url, params=params, timeout=30)
        r.raise_for_status()
        data = r.json()
        if isinstance(data, dict) and 'Error Message' in data:
            print(f"FMP Error: {data['Error Message']}")
            return None
        return data
    except requests.exceptions.RequestException as e:
        print(f"Request failed: {e}")
        return None
```

---

## ✅ VERIFIED ENDPOINTS (Tested Feb 2026)

### ⚠️ CRITICAL: Endpoint Name Traps

Many endpoints were renamed. Wrong names silently return `[]`. Always use these:

| ❌ Wrong Name (404) | ✅ Correct Name | Notes |
|---|---|---|
| `market-biggest-gainers` | `biggest-gainers` | |
| `market-biggest-losers` | `biggest-losers` | |
| `market-most-active` | `most-actives` | |
| `enterprise-value` | `enterprise-values` | plural |
| `sector-performance` | `sector-performance-snapshot` | + requires `date` param |
| `press-releases` | `news/press-releases` | under news/ prefix |
| `news/general` | `fmp-articles` | completely renamed |
| `rating` | `ratings-snapshot` | completely renamed |
| `financial-score` | `financial-scores` | plural |
| `senate-trading` | `senate-latest` / `house-latest` | verified Jul 2026; no symbol filter |
| `insider-trading` | `insider-trading/latest` (all) / `insider-trading/search` | verified Jul 2026 |
| `upgrades-downgrades` | `grades` (symbol) / `grades-latest-news` (all) | verified Jul 2026 |

---

### 1. SEARCH & DIRECTORY

| Endpoint | Params | Description |
|----------|--------|-------------|
| `search-symbol` | `query` | Ticker search |
| `search-name` | `query` | Company name search |
| `company-screener` | see below | Multi-filter screener |
| `stock-list` | `limit` | 48,000+ symbols |
| `etf-list` | `limit` | 9,700+ ETFs |
| `actively-trading-list` | `limit` | Currently trading |
| `symbol-change` | `page`, `limit` | Ticker changes |
| `available-exchanges` | — | 73 exchanges |
| `available-sectors` | — | 11 sectors |
| `available-industries` | — | 159 industries |
| `available-countries` | — | 117 countries |

**Screener params**: `marketCapMoreThan`, `marketCapLowerThan`, `priceMoreThan`, `priceLowerThan`, `betaMoreThan`, `betaLowerThan`, `volumeMoreThan`, `volumeLowerThan`, `dividendMoreThan`, `dividendLowerThan`, `isEtf`, `isFund`, `isActivelyTrading`, `sector`, `industry`, `country`, `exchange`, `limit`

```python
screener = fmp_get("company-screener", {
    "marketCapMoreThan": 2000000000,
    "sector": "Energy",
    "exchange": "NYSE,NASDAQ",
    "isActivelyTrading": "true",
    "limit": 50
})
```

---

### 2. COMPANY PROFILE

| Endpoint | Params | Description |
|----------|--------|-------------|
| `profile` | `symbol` | Full profile (price, mktcap, sector, CEO, desc) |
| `stock-peers` | `symbol` | Same-sector peers |
| `market-capitalization` | `symbol` | Current market cap |
| `market-capitalization-batch` | `symbols` | Comma-sep batch |
| `historical-market-capitalization` | `symbol`, `from`, `to`, `limit` | Historical mktcap |
| `key-executives` | `symbol` | CEO, CFO, etc. |
| `governance-executive-compensation` | `symbol` | Compensation data |
| `employee-count` | `symbol` | Current headcount |
| `historical-employee-count` | `symbol` | Historical headcount |
| `shares-float` | `symbol` | Float & outstanding |
| `shares-float-all` | `page`, `limit` | All companies |
| `delisted-companies` | `page`, `limit` | Delisted stocks |
| `mergers-acquisitions-latest` | `page`, `limit` | Recent M&A |
| `mergers-acquisitions-search` | `name` | Search M&A |

---

### 3. QUOTES

| Endpoint | Params | Description |
|----------|--------|-------------|
| `quote` | `symbol` | Full quote — stocks, ETF, forex, crypto, commodity |
| `quote-short` | `symbol` | Price + volume only |
| `batch-quote` | `symbols` | Comma-sep multiple |
| `batch-quote-short` | `symbols` | Comma-sep condensed |
| `stock-price-change` | `symbol` | % change 1D/5D/1M/3M/6M/YTD/1Y/3Y/5Y/10Y/max |
| `aftermarket-quote` | `symbol` | Pre/post-market |
| `aftermarket-trade` | `symbol` | Post-market trades |

```python
# Portfolio batch quote
quotes = fmp_get("batch-quote", {"symbols": "SM,KOS,MO,XLE,RGLD,FCX"})
# Forex/Crypto/Commodity — same endpoint
eurusd = fmp_get("quote", {"symbol": "EURUSD"})
btc = fmp_get("quote", {"symbol": "BTCUSD"})
gold = fmp_get("quote", {"symbol": "GCUSD"})
```

---

### 4. HISTORICAL PRICES

| Endpoint | Params | Description |
|----------|--------|-------------|
| `historical-price-eod/full` | `symbol`, `from`, `to`, `limit` | Full OHLCV daily |
| `historical-price-eod/light` | `symbol`, `from`, `to`, `limit` | Date + close only |
| `historical-chart/1min` | `symbol`, `from`, `to` | 1-min intraday |
| `historical-chart/5min` | `symbol`, `from`, `to` | 5-min intraday |
| `historical-chart/15min` | `symbol`, `from`, `to` | 15-min intraday |
| `historical-chart/30min` | `symbol`, `from`, `to` | 30-min intraday |
| `historical-chart/1hour` | `symbol`, `from`, `to` | 1-hour intraday |
| `historical-chart/4hour` | `symbol`, `from`, `to` | 4-hour intraday |

Works for stocks, ETFs, forex pairs, crypto, and commodities.

```python
prices = fmp_get("historical-price-eod/full", {
    "symbol": "AAPL", "from": "2025-01-01", "to": "2026-02-20"
})
intraday = fmp_get("historical-chart/1hour", {
    "symbol": "AAPL", "from": "2026-02-18", "to": "2026-02-20"
})
```

---

### 5. FINANCIAL STATEMENTS

| Endpoint | Params | Description |
|----------|--------|-------------|
| `income-statement` | `symbol`, `period`, `limit` | P&L |
| `balance-sheet-statement` | `symbol`, `period`, `limit` | Balance sheet |
| `cash-flow-statement` | `symbol`, `period`, `limit` | Cash flows |
| `income-statement-growth` | `symbol`, `period`, `limit` | Growth rates |
| `enterprise-values` | `symbol`, `period`, `limit` | EV (**plural, not singular**) |
| `revenue-product-segmentation` | `symbol` | Revenue by product |
| `revenue-geographic-segmentation` | `symbol` | Revenue by geography |

**period**: `annual` or `quarter`

```python
income = fmp_get("income-statement", {"symbol": "AAPL", "period": "quarter", "limit": 8})
ev = fmp_get("enterprise-values", {"symbol": "AAPL", "period": "annual", "limit": 5})
geo = fmp_get("revenue-geographic-segmentation", {"symbol": "AAPL"})
```

---

### 6. RATIOS, METRICS & SCORES

| Endpoint | Params | Description |
|----------|--------|-------------|
| `ratios` | `symbol`, `period`, `limit` | All financial ratios |
| `ratios-ttm` | `symbol` | TTM ratios |
| `key-metrics` | `symbol`, `period`, `limit` | Key metrics |
| `key-metrics-ttm` | `symbol` | TTM key metrics |
| `discounted-cash-flow` | `symbol` | DCF valuation |
| `owner-earnings` | `symbol` | Owner earnings |
| `ratings-snapshot` | `symbol` | Overall rating + sub-scores (**NOT `rating`**) |
| `financial-scores` | `symbol` | Altman Z-score, Piotroski score (**NOT `financial-score`**) |

```python
rating = fmp_get("ratings-snapshot", {"symbol": "AAPL"})
# Returns: symbol, rating, overallScore, discountedCashFlowScore, etc.

scores = fmp_get("financial-scores", {"symbol": "AAPL"})
# Returns: altmanZScore, piotroskiScore, workingCapital, etc.
```

---

### 7. ANALYST & GRADES

| Endpoint | Params | Description |
|----------|--------|-------------|
| `analyst-estimates` | `symbol`, `period`, `limit` | EPS/revenue estimates |
| `analyst-recommendations` | `symbol`, `limit` | Buy/sell recs |
| `price-target` | `symbol`, `limit` | Individual price targets |
| `price-target-summary` | `symbol` | Aggregated target stats |
| `price-target-latest-news` | `limit` | Latest PT changes market-wide ✅ (Jul 2026) |
| `grades` | `symbol`, `limit` | Analyst stock grades per symbol |
| `grades-latest-news` | `limit` | Latest rating changes market-wide ✅ (Jul 2026) |
| `grades-consensus` | `symbol` | StrongBuy/Buy/Hold/Sell/StrongSell counts |

> ⚠️ `upgrades-downgrades` returns **404** as of Jul 2026 — use `grades` (per symbol) or `grades-latest-news` (market-wide) instead.

```python
grades = fmp_get("grades", {"symbol": "AAPL", "limit": 20})
consensus = fmp_get("grades-consensus", {"symbol": "AAPL"})
# Returns: strongBuy, buy, hold, sell, strongSell counts
```

---

### 8. MARKET MOVERS ⚠️

```python
# ✅ CORRECT names
gainers = fmp_get("biggest-gainers", {"limit": 20})
losers = fmp_get("biggest-losers", {"limit": 20})
active = fmp_get("most-actives", {"limit": 20})

# ❌ WRONG — these return 404
# fmp_get("market-biggest-gainers")
# fmp_get("market-most-active")
```

---

### 9. MARKET PERFORMANCE ⚠️ Requires `date` param!

| Endpoint | Required Params | Description |
|----------|----------------|-------------|
| `sector-performance-snapshot` | `date=YYYY-MM-DD` | All sectors daily change |
| `industry-performance-snapshot` | `date=YYYY-MM-DD` | All industries daily change |
| `historical-sector-performance` | `sector=Technology` | Historical sector perf |
| `sector-pe-snapshot` | `date=YYYY-MM-DD` | Sector P/E ratios |
| `industry-pe-snapshot` | `date=YYYY-MM-DD` | Industry P/E ratios |
| `historical-sector-pe` | `sector=Technology` | Historical sector P/E |

```python
from datetime import datetime, timedelta
today = datetime.now().strftime("%Y-%m-%d")

# ✅ CORRECT — must include date
sectors = fmp_get("sector-performance-snapshot", {"date": today})
# Returns: date, sector, exchange, averageChange

# Get all sectors snapshot
industries = fmp_get("industry-performance-snapshot", {"date": today})

# Historical sector performance
tech_hist = fmp_get("historical-sector-performance", {
    "sector": "Technology",
    "from": "2026-01-01",
    "to": "2026-02-20"
})

# ❌ WRONG — returns 404
# fmp_get("sector-performance")
```

**Valid sector names**: `Technology`, `Healthcare`, `Financial Services`, `Energy`, `Consumer Cyclical`, `Industrials`, `Consumer Defensive`, `Basic Materials`, `Real Estate`, `Communication Services`, `Utilities`

---

### 10. INDEXES (Premium — Accessible)

```python
sp500 = fmp_get("sp500-constituent")       # 503 stocks
nasdaq = fmp_get("nasdaq-constituent")     # 101 stocks
dow = fmp_get("dowjones-constituent")      # 30 stocks
```

---

### 11. TECHNICAL INDICATORS

| Endpoint | Params | Timeframes |
|----------|--------|------------|
| `technical-indicators/sma` | `symbol`, `periodLength`, `timeframe` | 1min, 5min, 15min, 30min, 1hour, 4hour, 1day |
| `technical-indicators/ema` | same | same |
| `technical-indicators/rsi` | same | same |
| `technical-indicators/macd` | same | same |
| `technical-indicators/adx` | same | same |
| `technical-indicators/williams` | same | same |
| `technical-indicators/roc` | same | same |

```python
rsi = fmp_get("technical-indicators/rsi", {"symbol": "AAPL", "periodLength": 14, "timeframe": "1day"})
sma200 = fmp_get("technical-indicators/sma", {"symbol": "AAPL", "periodLength": 200, "timeframe": "1day"})
macd = fmp_get("technical-indicators/macd", {"symbol": "AAPL", "periodLength": 12, "timeframe": "1day"})
```

---

### 12. NEWS ⚠️ Correct endpoints!

| Endpoint | Params | Description |
|----------|--------|-------------|
| `news/stock` | `symbols` (comma-sep), `limit` | Stock news ✅ |
| `news/press-releases` | `symbol`, `limit` | Press releases ✅ (**NOT `press-releases`**) |
| `news/crypto` | `limit` | Crypto news ✅ |
| `news/forex` | `limit` | Forex news ✅ |
| `fmp-articles` | `limit` | FMP market articles ✅ (**NOT `news/general`**) |

```python
# Stock news
news = fmp_get("news/stock", {"symbols": "AAPL,MSFT", "limit": 20})
# Portfolio news
port_news = fmp_get("news/stock", {"symbols": "SM,KOS,MO,XLE,RGLD,FCX", "limit": 30})

# Press releases
pr = fmp_get("news/press-releases", {"symbol": "AAPL", "limit": 10})

# General market articles
articles = fmp_get("fmp-articles", {"limit": 20})

# ❌ WRONG — these return 404
# fmp_get("press-releases", {"symbol": "AAPL"})
# fmp_get("news/general")
```

---

### 13. EARNINGS & CALENDAR

| Endpoint | Params | Description |
|----------|--------|-------------|
| `earnings-calendar` | `from`, `to` | Upcoming earnings (max 90 days) |
| `analyst-estimates` | `symbol`, `period`, `limit` | EPS/revenue estimates |
| `dividends` | `symbol` | Dividend history |
| `stock-split-calendar` | `from`, `to` | Stock splits |
| `ipo-calendar` | `from`, `to` | IPO calendar |
| `economic-calendar` | `from`, `to` | Economic events |

> **Note**: `earnings-surprise` / `earnings-surprises` are **not available** on Premium plan (requires Ultimate or Bulk tier). Use `analyst-estimates` instead.

---

### 14. INSIDER & INSTITUTIONAL

| Endpoint | Params | Description |
|----------|--------|-------------|
| `insider-trading/latest` | `page`, `limit` | Latest insider transactions market-wide ✅ (Jul 2026) |
| `insider-trading/search` | `symbol`, `limit` | Insider transactions per symbol ✅ (Jul 2026) |
| `insider-trading-statistics` | `symbol` | Insider summary stats |
| `institutional-holders` | `symbol`, `limit` | Institutional ownership |
| `senate-latest` | `page`, `limit` | Latest Senate trade disclosures ✅ (Jul 2026) |
| `house-latest` | `page`, `limit` | Latest House trade disclosures ✅ (Jul 2026) |

> ⚠️ `senate-trading` and bare `insider-trading` return **404** as of Jul 2026 — use the names above.
> Senate/House rows: `firstName`, `lastName`, `district`, `type` (Purchase/Sale), `amount` (range string like `"$15,001 - $50,000"`), `assetDescription`, `disclosureDate`, `transactionDate`, `link`.
> Insider rows: `transactionType` (`P-Purchase`/`S-Sale`), `securitiesTransacted`, `price`, `reportingName`, `typeOfOwner`.
| `form-13f` | `cik`, `date` | 13F filing data |
| `form-13f-filing-dates` | `cik` | Available 13F dates |

---

### 15. ETF

| Endpoint | Params | Description |
|----------|--------|-------------|
| `etf/holdings` | `symbol`, `date` | ETF constituents |
| `etf/info` | `symbol` | ETF details |
| `etf/sector-weightings` | `symbol` | Sector breakdown |
| `etf/country-weightings` | `symbol` | Country breakdown |

---

### 16. ECONOMICS

| Endpoint | Params | Description |
|----------|--------|-------------|
| `treasury-rates` | `from`, `to` | US treasury yields |
| `economic-indicators` | `name`, `from`, `to` | GDP, CPI, unemployment, etc. |
| `market-risk-premium` | `date` | Country risk premiums |

---

### 17. FOREX / CRYPTO / COMMODITIES

Use standard `quote` and `historical-price-eod/full` with appropriate symbols:

```python
fmp_get("forex-list")           # All forex symbols
fmp_get("crypto-list")          # All crypto symbols
fmp_get("commodity-list")       # All commodity symbols

# Quotes work for all asset types
fmp_get("quote", {"symbol": "EURUSD"})   # Forex
fmp_get("quote", {"symbol": "BTCUSD"})   # Crypto
fmp_get("quote", {"symbol": "GCUSD"})    # Gold
fmp_get("quote", {"symbol": "CLUSD"})    # Crude Oil

# Historical works for all
fmp_get("historical-price-eod/full", {"symbol": "BTCUSD", "from": "2025-01-01"})
```

---

## 🔒 NOT Available on Premium (Requires Ultimate)

| Feature | Plan Needed |
|---------|-------------|
| Earnings Call Transcripts | Ultimate |
| ETF & Mutual Fund Holdings (full) | Ultimate |
| 13F Institutional Holdings (full analytics) | Ultimate |
| 1-Minute Intraday Charting | Ultimate |
| `income-statement-ttm` | Returns 402 |
| `earnings-surprises` / `earnings-surprise` | Ultimate (Bulk only) |
| Bulk delivery endpoints | Ultimate |

---

## READY-TO-USE WORKFLOWS

### Portfolio Monitoring
```python
symbols = "SM,KOS,MO,XLE,RGLD,FCX"
quotes = fmp_get("batch-quote", {"symbols": symbols})
news = fmp_get("news/stock", {"symbols": symbols, "limit": 30})
for sym in symbols.split(","):
    change = fmp_get("stock-price-change", {"symbol": sym})
```

### Market Overview
```python
from datetime import datetime
today = datetime.now().strftime("%Y-%m-%d")

gainers = fmp_get("biggest-gainers", {"limit": 20})
losers = fmp_get("biggest-losers", {"limit": 20})
active = fmp_get("most-actives", {"limit": 20})
sectors = fmp_get("sector-performance-snapshot", {"date": today})
articles = fmp_get("fmp-articles", {"limit": 10})
econ = fmp_get("economic-calendar", {"from": today, "to": "2026-02-28"})
```

### Fundamental Analysis
```python
symbol = "AAPL"
profile = fmp_get("profile", {"symbol": symbol})
income = fmp_get("income-statement", {"symbol": symbol, "period": "annual", "limit": 5})
balance = fmp_get("balance-sheet-statement", {"symbol": symbol, "period": "annual", "limit": 5})
cashflow = fmp_get("cash-flow-statement", {"symbol": symbol, "period": "annual", "limit": 5})
metrics = fmp_get("key-metrics-ttm", {"symbol": symbol})
ratios = fmp_get("ratios-ttm", {"symbol": symbol})
dcf = fmp_get("discounted-cash-flow", {"symbol": symbol})
ev = fmp_get("enterprise-values", {"symbol": symbol, "period": "annual", "limit": 5})
rating = fmp_get("ratings-snapshot", {"symbol": symbol})
scores = fmp_get("financial-scores", {"symbol": symbol})
geo_rev = fmp_get("revenue-geographic-segmentation", {"symbol": symbol})
peers = fmp_get("stock-peers", {"symbol": symbol})
```

### Technical Analysis
```python
symbol = "TSLA"
prices = fmp_get("historical-price-eod/full", {"symbol": symbol, "from": "2025-08-01"})
rsi = fmp_get("technical-indicators/rsi", {"symbol": symbol, "periodLength": 14, "timeframe": "1day"})
sma20 = fmp_get("technical-indicators/sma", {"symbol": symbol, "periodLength": 20, "timeframe": "1day"})
sma50 = fmp_get("technical-indicators/sma", {"symbol": symbol, "periodLength": 50, "timeframe": "1day"})
sma200 = fmp_get("technical-indicators/sma", {"symbol": symbol, "periodLength": 200, "timeframe": "1day"})
macd = fmp_get("technical-indicators/macd", {"symbol": symbol, "periodLength": 12, "timeframe": "1day"})
adx = fmp_get("technical-indicators/adx", {"symbol": symbol, "periodLength": 14, "timeframe": "1day"})
```

### Analyst & Sentiment
```python
symbol = "META"
estimates = fmp_get("analyst-estimates", {"symbol": symbol, "period": "quarter", "limit": 8})
targets = fmp_get("price-target-summary", {"symbol": symbol})
consensus = fmp_get("grades-consensus", {"symbol": symbol})
grades = fmp_get("grades", {"symbol": symbol, "limit": 20})
insider = fmp_get("insider-trading/search", {"symbol": symbol, "limit": 50})

# Market-wide (no symbol) — story discovery
grade_news = fmp_get("grades-latest-news", {"limit": 20})
pt_news = fmp_get("price-target-latest-news", {"limit": 20})
insider_all = fmp_get("insider-trading/latest", {"limit": 100})
senate = fmp_get("senate-latest", {"limit": 100})
house = fmp_get("house-latest", {"limit": 100})
```

---

## ERROR HANDLING

| Status | Cause | Fix |
|--------|-------|-----|
| `404` + empty `[]` | Wrong endpoint name | Check correct name in this skill |
| `402` Restricted | Not in Premium plan | Requires Ultimate |
| `403` Legacy | Used v3/v4 route | Switch to `/stable/` |
| `400` Query Error | Missing required param | Add `date`, `sector`, etc. |
| `{"Error Message": "Limit Reach"}` | Daily limit hit | Wait 24h (2500/day) |
| `{"Error Message": "Invalid API KEY"}` | Wrong key | Check memory |
| Empty `[]` with `200` | No data for params | Check symbol, date range |

```python
import time

def fmp_get_retry(endpoint, params=None, max_retries=3):
    for attempt in range(max_retries):
        result = fmp_get(endpoint, params)
        if result is not None and result != []:
            return result
        time.sleep(2 ** attempt)
    return None
```

---

## LEGACY ENDPOINT MAPPING

All v3/v4 routes are **blocked**. Use these stable equivalents:

| Legacy (BLOCKED) | Stable ✅ |
|------------------|-----------|
| `/api/v3/quote/AAPL` | `/stable/quote?symbol=AAPL` |
| `/api/v3/income-statement/AAPL` | `/stable/income-statement?symbol=AAPL` |
| `/api/v3/historical-price-full/AAPL` | `/stable/historical-price-eod/full?symbol=AAPL` |
| `/api/v3/technical_indicator/daily/AAPL?type=rsi&period=14` | `/stable/technical-indicators/rsi?symbol=AAPL&periodLength=14&timeframe=1day` |
| `/api/v3/earning_calendar` | `/stable/earnings-calendar` |
| `/api/v3/stock_news` | `/stable/news/stock` |
| `/api/v3/stock-screener` | `/stable/company-screener` |
| `/api/v3/discounted-cash-flow/AAPL` | `/stable/discounted-cash-flow?symbol=AAPL` |
| `/api/v3/biggest-gainers` | `/stable/biggest-gainers` |

**Key changes**:
- Symbols moved from path to query param: `/AAPL` → `?symbol=AAPL`
- Technical indicators: `type=rsi` → URL path `/rsi`; `period` → `periodLength`
- News reorganized under `/news/` prefix
- Screener: `stock-screener` → `company-screener`
- Market movers renamed (remove `market-` prefix)
- Enterprise value: singular → plural (`enterprise-values`)
