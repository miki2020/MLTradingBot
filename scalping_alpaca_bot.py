from lumibot.brokers import Alpaca
from lumibot.strategies.strategy import Strategy
from alpaca_trade_api import REST
from datetime import datetime
import pandas as pd
import ta
import os

API_KEY = os.environ["API_KEY"]
API_SECRET = os.environ["API_SECRET"]
BASE_URL = "https://paper-api.alpaca.markets"

ALPACA_CREDS = {
    "API_KEY": API_KEY,
    "API_SECRET": API_SECRET,
    "PAPER": True
}

class ScalpingAlpacaBot(Strategy):
    def initialize(self, symbol: str = "BTCUSD", cash_at_risk: float = 0.5, timeframe: str = "1H"):
        self.symbol = symbol
        self.cash_at_risk = cash_at_risk
        self.timeframe = timeframe
        self.api = REST(base_url=BASE_URL, key_id=API_KEY, secret_key=API_SECRET)
        self.last_trade = None
        self.sleeptime = "1H"

    def fetch_data(self, limit=100):
        bars = self.api.get_crypto_bars(self.symbol, timeframe=self.timeframe, limit=limit).df
        bars = bars.reset_index()
        bars = bars[["timestamp", "open", "high", "low", "close", "volume"]]
        bars.rename(columns={"timestamp": "Gmt time", "open": "Open", "high": "High", "low": "Low", "close": "Close", "volume": "Volume"}, inplace=True)
        bars["Gmt time"] = pd.to_datetime(bars["Gmt time"])
        bars.set_index("Gmt time", inplace=True)
        return bars

    def calculate_indicators(self, df):
        df["EMA_slow"] = ta.trend.ema_indicator(df["Close"], window=50)
        df["EMA_fast"] = ta.trend.ema_indicator(df["Close"], window=30)
        df["RSI"] = ta.momentum.rsi(df["Close"], window=10)
        bb = ta.volatility.BollingerBands(df["Close"], window=15, window_dev=1.5)
        df["BB_upper"] = bb.bollinger_hband()
        df["BB_middle"] = bb.bollinger_mavg()
        df["BB_lower"] = bb.bollinger_lband()
        df["ATR"] = ta.volatility.average_true_range(df["High"], df["Low"], df["Close"], window=7)
        return df

    def ema_signal(self, df, backcandles=7):
        relevant = df.iloc[-backcandles:]
        if all(relevant["EMA_fast"] < relevant["EMA_slow"]):
            return 1
        elif all(relevant["EMA_fast"] > relevant["EMA_slow"]):
            return 2
        else:
            return 0

    def total_signal(self, df, backcandles=7):
        signal = self.ema_signal(df, backcandles)
        if signal == 2 and df["Close"].iloc[-1] <= df["BB_lower"].iloc[-1]:
            return 2
        if signal == 1 and df["Close"].iloc[-1] >= df["BB_upper"].iloc[-1]:
            return 1
        return 0

    def position_sizing(self, last_price):
        cash = self.get_cash()
        quantity = round(cash * self.cash_at_risk / last_price, 6)
        return cash, last_price, quantity

    def on_trading_iteration(self):
        df = self.fetch_data()
        df = self.calculate_indicators(df)
        signal = self.total_signal(df)
        last_price = df["Close"].iloc[-1]
        cash, last_price, quantity = self.position_sizing(last_price)

        if cash > last_price and quantity > 0:
            if signal == 2 and self.last_trade != "buy":
                self.sell_all()
                order = self.create_order(
                    self.symbol,
                    quantity,
                    "buy",
                    type="bracket",
                    take_profit_price=last_price * 1.015,
                    stop_loss_price=last_price * 0.985
                )
                self.submit_order(order)
                self.last_trade = "buy"
            elif signal == 1 and self.last_trade != "sell":
                self.sell_all()
                order = self.create_order(
                    self.symbol,
                    quantity,
                    "sell",
                    type="bracket",
                    take_profit_price=last_price * 0.985,
                    stop_loss_price=last_price * 1.015
                )
                self.submit_order(order)
                self.last_trade = "sell"

# Example usage:
# from lumibot.traders import Trader
# broker = Alpaca(ALPACA_CREDS)
# strategy = ScalpingAlpacaBot(name='scalpingbot', broker=broker, parameters={"symbol": "BTCUSD", "cash_at_risk": 0.5})
# trader = Trader()
# trader.add_strategy(strategy)
# trader.run_all()
