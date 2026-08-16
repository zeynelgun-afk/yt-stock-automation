"""Story Pool Collector — gathers every viral-story candidate for the day.

ROADMAP Faz 1: before each video, one collection pass pulls congress trades,
insider activity, analyst shocks, earnings, macro events, movers and Reddit
sentiment into a single structured pool. Faz 2 (story selection engine) will
score these candidates and pick the day's angle/franchise.

Failure policy: index quotes and market movers are the backbone of every
video — if they fail, FMPDataError propagates and the pipeline must abort.
All other sections are enrichment: they degrade to empty lists and record
the error in pool["errors"], but never fabricate data.
"""
import logging
import re
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

from data_fetcher import FMPDataFetcher, FMPDataError, ny_now

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

CONGRESS_LOOKBACK_DAYS = 7
INSIDER_MIN_VALUE_USD = 1_000_000
EARNINGS_MIN_REVENUE_EST = 1_000_000_000
BIG_PT_REVISION_PCT = 30.0

_AMOUNT_RE = re.compile(r"\$([\d,]+)")


def _parse_amount_min(amount: str) -> int:
    """Min dollars from a disclosure range like '$15,001 - $50,000'."""
    m = _AMOUNT_RE.search(amount or "")
    return int(m.group(1).replace(",", "")) if m else 0


class StoryPoolCollector:
    def __init__(self, fetcher: Optional[FMPDataFetcher] = None):
        self.fetcher = fetcher or FMPDataFetcher()

    def collect(self) -> Dict[str, Any]:
        errors: List[str] = []

        def soft(section: str, fn, default):
            # Enrichment sections are degradable by definition, so ANY failure
            # (a KeyError on an FMP schema change, not just FMPDataError) must
            # degrade to the default instead of crashing the whole slot
            try:
                return fn()
            except Exception as e:
                logger.warning(f"Story pool section '{section}' failed: {e}")
                errors.append(f"{section}: {e}")
                return default

        # Backbone — failures here propagate and abort the pipeline
        indexes = self.fetcher.get_index_quotes()
        gainers = self.fetcher.get_top_gainers(10)
        losers = self.fetcher.get_top_losers(10)
        actives = self.fetcher.get_most_actives(10)

        pool: Dict[str, Any] = {
            "collected_at": datetime.now().isoformat(timespec="seconds"),
            "core": {
                "indexes": indexes,
                "sectors": soft("sectors", self.fetcher.get_sector_performance, []),
                "fear_greed": self.fetcher.get_fear_greed_index(),  # None if unavailable
            },
            "movers": {"gainers": gainers, "losers": losers, "actives": actives},
            "mover_news": soft("mover_news", lambda: self._mover_news(gainers, losers), {}),
            "congress": soft("congress", self._congress_trades, []),
            "insider": soft("insider", self._insider_trades, {"big_trades": [], "cluster_buys": []}),
            "analyst": soft("analyst", self._analyst_moves, {"grades": [], "price_targets": []}),
            "earnings": soft("earnings", self._earnings, {"reported_today": [], "upcoming": []}),
            "economic": soft("economic", self._economic_events, []),
            "reddit": self._reddit_trending(),  # already soft inside fetcher
            "errors": errors,
        }
        return pool

    def _mover_news(self, gainers: List[Dict], losers: List[Dict]) -> Dict[str, List[Dict]]:
        """Headlines for the top movers — the 'why' behind each big move."""
        symbols = [g["symbol"] for g in gainers[:3]] + [l["symbol"] for l in losers[:3]]
        news = self.fetcher.get_stock_news(symbols, limit=30)
        by_symbol: Dict[str, List[Dict]] = {}
        for item in news:
            sym = item.get("symbol", "")
            if sym in symbols and len(by_symbol.setdefault(sym, [])) < 3:
                by_symbol[sym].append({
                    "title": item.get("title", ""),
                    "publishedDate": item.get("publishedDate", ""),
                })
        return by_symbol

    def _congress_trades(self) -> List[Dict[str, Any]]:
        """Recent Senate + House disclosures, biggest first."""
        cutoff = (ny_now() - timedelta(days=CONGRESS_LOOKBACK_DAYS)).strftime("%Y-%m-%d")
        trades = []
        seen = set()
        for chamber, rows in (
            ("Senate", self.fetcher.get_senate_trades()),
            ("House", self.fetcher.get_house_trades()),
        ):
            for row in rows:
                if (row.get("disclosureDate") or "") < cutoff:
                    continue
                # Feed repeats multi-leg filings as near-identical rows whose
                # assetDescription differs only by a trailing "(1)"/"(2)" — one story each
                asset = re.sub(r"\s*\(\d+\)\s*$", "", row.get("assetDescription") or "")
                key = (
                    row.get("firstName"), row.get("lastName"), row.get("symbol"),
                    asset, row.get("type"), row.get("amount"), row.get("transactionDate"),
                )
                if key in seen:
                    continue
                seen.add(key)
                trades.append({
                    "chamber": chamber,
                    "politician": f"{row.get('firstName', '')} {row.get('lastName', '')}".strip(),
                    "district": row.get("district", ""),
                    "symbol": row.get("symbol", ""),
                    "asset": row.get("assetDescription", ""),
                    "type": row.get("type", ""),
                    "amount": row.get("amount", ""),
                    "amount_min_usd": _parse_amount_min(row.get("amount", "")),
                    "transactionDate": row.get("transactionDate", ""),
                    "disclosureDate": row.get("disclosureDate", ""),
                })
        trades.sort(key=lambda t: t["amount_min_usd"], reverse=True)
        return trades[:15]

    def _insider_trades(self) -> Dict[str, Any]:
        """$1M+ insider buys/sells plus cluster-buy signals (3+ distinct buyers).

        Multi-leg Form 4 filings (same insider, same stock, same direction)
        are aggregated into one total — one story, not five near-duplicates.
        """
        rows = self.fetcher.get_insider_trades()
        agg: Dict[tuple, Dict[str, Any]] = {}
        buyers_per_symbol: Dict[str, set] = {}
        for row in rows:
            ttype = row.get("transactionType", "")
            if not (ttype.startswith("P-") or ttype.startswith("S-")):
                continue
            value = (row.get("securitiesTransacted") or 0) * (row.get("price") or 0)
            if ttype.startswith("P-"):
                buyers_per_symbol.setdefault(row["symbol"], set()).add(row.get("reportingName"))
            if not value:
                continue
            key = (row.get("reportingName"), row.get("symbol"), ttype[0])
            entry = agg.setdefault(key, {
                "symbol": row.get("symbol", ""),
                "insider": row.get("reportingName", ""),
                "role": row.get("typeOfOwner", ""),
                "type": "BUY" if ttype.startswith("P-") else "SELL",
                "value_usd": 0,
                "shares": 0,
                "transactions": 0,
                "transactionDate": row.get("transactionDate", ""),
            })
            entry["value_usd"] += round(value)
            entry["shares"] += row.get("securitiesTransacted") or 0
            entry["transactions"] += 1
            entry["transactionDate"] = max(entry["transactionDate"], row.get("transactionDate", ""))

        big = [t for t in agg.values() if t["value_usd"] >= INSIDER_MIN_VALUE_USD]
        big.sort(key=lambda t: t["value_usd"], reverse=True)
        cluster_buys = [s for s, names in buyers_per_symbol.items() if len(names) >= 3]
        return {"big_trades": big[:15], "cluster_buys": cluster_buys}

    def _analyst_moves(self) -> Dict[str, Any]:
        """Latest rating changes and price-target revisions; big revisions flagged."""
        grades = [{
            "symbol": g.get("symbol", ""),
            "newGrade": g.get("newGrade", ""),
            "previousGrade": g.get("previousGrade", ""),
            "company": g.get("gradingCompany", ""),
            "action": g.get("action", ""),
            "headline": g.get("newsTitle", ""),
            "publishedDate": g.get("publishedDate", ""),
        } for g in self.fetcher.get_grade_news(15)]

        targets = []
        for t in self.fetcher.get_price_target_news(15):
            target = t.get("priceTarget") or 0
            price = t.get("priceWhenPosted") or 0
            upside_pct = round((target - price) / price * 100, 1) if price else None
            targets.append({
                "symbol": t.get("symbol", ""),
                "analyst": t.get("analystName", ""),
                "priceTarget": target,
                "priceWhenPosted": price,
                "upside_pct": upside_pct,
                "is_shock": upside_pct is not None and abs(upside_pct) >= BIG_PT_REVISION_PCT,
                "headline": t.get("newsTitle", ""),
                "publishedDate": t.get("publishedDate", ""),
            })
        return {"grades": grades, "price_targets": targets}

    def _earnings(self) -> Dict[str, Any]:
        """Today's reported results (with beat/miss) + notable upcoming reports."""
        # ET, not runner-local: on UTC CI runners, 20:00-24:00 ET is already
        # "tomorrow" in UTC, which silently emptied reported_today every evening
        today = ny_now().strftime("%Y-%m-%d")
        rows = self.fetcher.get_earnings_calendar(days_ahead=7)

        reported_today, upcoming = [], []
        for row in rows:
            est = row.get("epsEstimated")
            actual = row.get("epsActual")
            if row.get("date") == today and actual is not None:
                surprise_pct = (
                    round((actual - est) / abs(est) * 100, 1) if est else None
                )
                reported_today.append({
                    "symbol": row["symbol"],
                    "epsActual": actual,
                    "epsEstimated": est,
                    "surprise_pct": surprise_pct,
                    "revenueActual": row.get("revenueActual"),
                    "revenueEstimated": row.get("revenueEstimated"),
                })
            elif row.get("date", "") > today and (row.get("revenueEstimated") or 0) >= EARNINGS_MIN_REVENUE_EST:
                upcoming.append({
                    "symbol": row["symbol"],
                    "date": row["date"],
                    "epsEstimated": est,
                    "revenueEstimated": row.get("revenueEstimated"),
                })

        reported_today.sort(key=lambda r: abs(r["surprise_pct"] or 0), reverse=True)
        upcoming.sort(key=lambda r: r["revenueEstimated"], reverse=True)
        return {"reported_today": reported_today[:15], "upcoming": upcoming[:15]}

    def _economic_events(self) -> List[Dict[str, Any]]:
        """Notable US macro events in the next few days (CPI, FOMC, NFP...)."""
        rows = self.fetcher.get_economic_calendar(days_ahead=3)
        events = [{
            "date": row.get("date", ""),
            "event": row.get("event", ""),
            "impact": row.get("impact", ""),
            "previous": row.get("previous"),
            "estimate": row.get("estimate"),
            "actual": row.get("actual"),
        } for row in rows
            if row.get("country") == "US"
            and row.get("impact") in ("High", "Medium")
            and "CFTC" not in (row.get("event") or "")]
        events.sort(key=lambda e: e["date"])
        return events[:15]

    def _reddit_trending(self) -> List[Dict[str, Any]]:
        """Top WSB tickers with 24h momentum."""
        trending = []
        for row in self.fetcher.get_reddit_trending(10):
            mentions = row.get("mentions") or 0
            prev = row.get("mentions_24h_ago") or 0
            trending.append({
                "ticker": row.get("ticker", ""),
                "name": row.get("name", ""),
                "rank": row.get("rank"),
                "mentions": mentions,
                "mentions_change_pct": round((mentions - prev) / prev * 100, 1) if prev else None,
            })
        return trending


def compact_pool(pool: Dict[str, Any]) -> Dict[str, Any]:
    """Trimmed, prompt-sized view of the pool for LLM consumption."""
    return {
        "market": {
            "indexes": [
                {"symbol": q["symbol"], "price": q.get("price"),
                 "changePercentage": q.get("changePercentage")}
                for q in pool["core"]["indexes"]
            ],
            "sectors": pool["core"]["sectors"][:5],
            "fear_greed": pool["core"]["fear_greed"],
        },
        "gainers": [
            {"symbol": g["symbol"], "name": g.get("name"), "price": g.get("price"),
             "changesPercentage": g.get("changesPercentage")}
            for g in pool["movers"]["gainers"][:5]
        ],
        "losers": [
            {"symbol": l["symbol"], "name": l.get("name"), "price": l.get("price"),
             "changesPercentage": l.get("changesPercentage")}
            for l in pool["movers"]["losers"][:5]
        ],
        "mover_news": pool.get("mover_news") or {},
        "congress": pool["congress"][:5],
        "insider": pool["insider"]["big_trades"][:5],
        "cluster_buys": pool["insider"]["cluster_buys"],
        "analyst_shocks": [t for t in pool["analyst"]["price_targets"] if t["is_shock"]][:5],
        "earnings_today": pool["earnings"]["reported_today"][:5],
        "earnings_upcoming": pool["earnings"]["upcoming"][:5],
        "economic": pool["economic"][:5],
        "reddit": pool["reddit"][:5],
    }


def summarize_pool(pool: Dict[str, Any]) -> str:
    """Human/LLM-readable digest of the pool — used in logs and (Faz 2) prompts."""
    lines = [f"STORY POOL @ {pool['collected_at']}"]

    # NOTE: batch-quote uses 'changePercentage'; mover endpoints use 'changesPercentage'
    idx = ", ".join(
        f"{q['symbol']} {q.get('changePercentage', 0):+.2f}%"
        for q in pool["core"]["indexes"]
    )
    lines.append(f"Indexes: {idx}")

    fg = pool["core"]["fear_greed"]
    lines.append(f"Fear/Greed: {fg['score']} ({fg['rating']})" if fg else "Fear/Greed: unavailable")

    g = pool["movers"]["gainers"][0]
    l = pool["movers"]["losers"][0]
    lines.append(
        f"Top gainer: {g['symbol']} {g.get('changesPercentage', 0):+.1f}% | "
        f"Top loser: {l['symbol']} {l.get('changesPercentage', 0):+.1f}%"
    )

    for trade in pool["congress"][:3]:
        lines.append(
            f"Congress: {trade['politician']} ({trade['chamber']}/{trade['district']}) "
            f"{trade['type']} {trade['symbol'] or trade['asset']} {trade['amount']}"
        )
    for trade in pool["insider"]["big_trades"][:3]:
        lines.append(
            f"Insider: {trade['insider']} ({trade['symbol']}) {trade['type']} "
            f"${trade['value_usd']:,}"
        )
    if pool["insider"]["cluster_buys"]:
        lines.append(f"Cluster buys: {', '.join(pool['insider']['cluster_buys'])}")

    shocks = [t for t in pool["analyst"]["price_targets"] if t["is_shock"]]
    for t in shocks[:3]:
        lines.append(f"Analyst shock: {t['symbol']} PT ${t['priceTarget']} ({t['upside_pct']:+.0f}%)")

    for r in pool["earnings"]["reported_today"][:3]:
        lines.append(
            f"Earnings today: {r['symbol']} EPS {r['epsActual']} vs {r['epsEstimated']} "
            f"({r['surprise_pct']:+.1f}%)" if r["surprise_pct"] is not None
            else f"Earnings today: {r['symbol']} EPS {r['epsActual']}"
        )
    for e in pool["economic"][:3]:
        lines.append(f"Macro: {e['event']} @ {e['date']}")
    for r in pool["reddit"][:3]:
        chg = f" ({r['mentions_change_pct']:+.0f}% 24h)" if r["mentions_change_pct"] is not None else ""
        lines.append(f"Reddit #{r['rank']}: {r['ticker']} {r['mentions']} mentions{chg}")

    if pool["errors"]:
        lines.append(f"Errors: {'; '.join(pool['errors'])}")
    return "\n".join(lines)


if __name__ == "__main__":
    collector = StoryPoolCollector()
    pool = collector.collect()
    print(summarize_pool(pool))
    print(
        f"\nCounts — congress: {len(pool['congress'])}, "
        f"insider: {len(pool['insider']['big_trades'])}, "
        f"grades: {len(pool['analyst']['grades'])}, "
        f"PTs: {len(pool['analyst']['price_targets'])}, "
        f"earnings today: {len(pool['earnings']['reported_today'])}, "
        f"upcoming: {len(pool['earnings']['upcoming'])}, "
        f"macro: {len(pool['economic'])}, reddit: {len(pool['reddit'])}"
    )
