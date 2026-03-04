"""CPO Agent — portfolio overseer. Monitors positions + real-time chart data."""
from src.agents.base import BaseAgent


class CPOAgent(BaseAgent):
    name = "cpo"
    subscribe_channels = [
        "cio/intel",
        "ceo/decisions",
        "chart/candle_closed",
        "system/cycle",
    ]

    async def on_start(self):
        self.log.info("ready")

    async def on_stop(self):
        pass

    async def on_message(self, channel: str, data: dict):
        self.log.info("message_received", channel=channel)

        if channel == "system/cycle":
            await self.on_cycle()
        elif channel == "chart/candle_closed":
            await self._check_position_impact(data)

    async def on_cycle(self):
        """30-min portfolio review with chart data."""
        if not self.charts:
            self.log.info("cycle_tick")
            return

        # Review all tracked pairs
        portfolio_report = {}
        for symbol in ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]:
            price = self.charts.get_price(symbol, "1h")
            change_1h = self.charts.get_price_change(symbol, "1h", periods=1)
            change_4h = self.charts.get_price_change(symbol, "15m", periods=16)

            portfolio_report[symbol] = {
                "current_price": price,
                "change_1h": round(change_1h, 2) if change_1h else None,
                "change_4h": round(change_4h, 2) if change_4h else None,
            }

            # Alert on significant moves
            if change_4h and abs(change_4h) > 15:
                await self.publish("cpo/alerts", {
                    "symbol": symbol,
                    "alert_type": "threshold_breach",
                    "change_4h": round(change_4h, 2),
                    "current_price": price,
                    "recommendation": "sell" if change_4h < -15 else "review",
                })

        # TODO: cross-reference with actual Polymarket positions
        self.log.info("cycle_tick", tracked_pairs=len(portfolio_report))

    async def _check_position_impact(self, candle_data: dict):
        """Check if a closed candle impacts any open position."""
        # TODO: compare with actual portfolio positions
        pass
