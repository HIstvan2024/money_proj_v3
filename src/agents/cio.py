"""
CIO Agent — Chief Intelligence Officer.
Combines Grok (X/Twitter sentiment), Elfa AI (trending tokens, social mentions),
and real-time chart data to produce actionable intel for other agents.
"""
import orjson
from src.agents.base import BaseAgent


class CIOAgent(BaseAgent):
    name = "cio"
    subscribe_channels = [
        "cso/opportunities",    # CSO found something → research it
        "cpo/alerts",           # CPO flagged movement → find the cause
        "chart/candle_closed",  # New candle closed → check for signals
        "system/cycle",         # 30-min cycle → proactive scan
    ]

    async def on_start(self):
        # Check Elfa API key status on startup
        if self.elfa:
            status = await self.elfa.check_key_status()
            if status:
                self.log.info("elfa.connected", status=status)
            else:
                self.log.warning("elfa.not_available")
        self.log.info("ready")

    async def on_stop(self):
        pass

    async def on_message(self, channel: str, data: dict):
        self.log.info("message_received", channel=channel)

        if channel == "system/cycle":
            await self.on_cycle()
        elif channel == "cso/opportunities":
            # CSO found a new market → gather intel on it
            await self._research_opportunity(data)
        elif channel == "cpo/alerts":
            # Position moved → investigate why
            await self._investigate_movement(data)
        elif channel == "chart/candle_closed":
            # Check for significant price moves
            await self._check_chart_signal(data)

    async def on_cycle(self):
        """30-min proactive intelligence gathering."""
        intel = {}

        # 1. Elfa: trending tokens & narratives
        if self.elfa:
            trending = await self.elfa.get_trending_tokens(time_window="1h")
            if trending:
                intel["trending_tokens"] = trending

            narratives = await self.elfa.get_trending_narratives()
            if narratives:
                intel["trending_narratives"] = narratives

        # 2. Chart data: price changes for tracked pairs
        if self.charts:
            price_changes = {}
            for symbol in ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]:
                change = self.charts.get_price_change(symbol, "1h", periods=2)
                if change is not None:
                    price_changes[symbol] = round(change, 2)
            intel["price_changes_2h"] = price_changes

        # 3. TODO: Grok sentiment analysis on X
        # grok_sentiment = await self._query_grok(...)

        if intel:
            await self.publish("cio/intel", {
                "type": "cycle_report",
                "data": intel,
            })
            self.log.info("cycle_intel_published", keys=list(intel.keys()))

        self.log.info("cycle_tick")

    async def _research_opportunity(self, data: dict):
        """Deep dive on a market opportunity from CSO."""
        market_question = data.get("question", "")
        keywords = data.get("keywords", [])

        intel = {"market_id": data.get("market_id"), "sources": []}

        # Elfa: search for mentions related to this market
        if self.elfa and keywords:
            keyword_str = ",".join(keywords)
            mentions = await self.elfa.search_mentions(keyword_str)
            if mentions:
                intel["elfa_mentions"] = mentions
                intel["sources"].append("elfa")

            # Also grab news
            for kw in keywords[:2]:
                news = await self.elfa.get_token_news(kw)
                if news:
                    intel.setdefault("elfa_news", []).append(news)
                    if "elfa_news" not in intel["sources"]:
                        intel["sources"].append("elfa_news")

        # TODO: Grok analysis
        # intel["grok_analysis"] = await self._query_grok(market_question)

        await self.publish("cio/intel", {
            "type": "opportunity_research",
            "data": intel,
        })

    async def _investigate_movement(self, data: dict):
        """Investigate why a position moved significantly."""
        symbol = data.get("symbol", "")
        if not symbol:
            return

        intel = {"symbol": symbol, "alert_type": data.get("alert_type")}

        # Elfa: check recent mentions for this token
        if self.elfa:
            ticker = symbol.replace("USDT", "").lower()
            mentions = await self.elfa.get_top_mentions(ticker, time_window="1h")
            if mentions:
                intel["recent_mentions"] = mentions

        await self.publish("cio/intel", {
            "type": "movement_investigation",
            "data": intel,
        })

    async def _check_chart_signal(self, data: dict):
        """Check if a closed candle represents a significant move."""
        symbol = data.get("symbol", "")
        if not symbol or not self.charts:
            return

        # Check 2-period price change
        change = self.charts.get_price_change(symbol, data.get("interval", "1h"), periods=2)
        if change is not None and abs(change) > 3.0:  # >3% move
            await self.publish("cio/intel", {
                "type": "chart_signal",
                "data": {
                    "symbol": symbol,
                    "interval": data.get("interval"),
                    "change_pct": round(change, 2),
                    "direction": "up" if change > 0 else "down",
                },
            })
            self.log.info("chart_signal_detected", symbol=symbol, change=f"{change:.2f}%")
