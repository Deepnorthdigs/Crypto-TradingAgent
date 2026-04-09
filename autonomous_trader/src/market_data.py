"""
Market Data Fetcher for Crypto via CCXT/Bybit
Replaces yfinance stock data fetching.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any
from pathlib import Path

import pandas as pd
import numpy as np

try:
    import ccxt
except ImportError:
    ccxt = None

logger = logging.getLogger("autonomous_trader")


class CryptoMarketData:
    def __init__(self, config: dict):
        self.config = config
        self.exchange_config = config.get("exchange", {})
        self._exchange = None
        self._init_exchange()
    
    def _init_exchange(self):
        if ccxt is None:
            logger.error("CCXT not installed. Run: pip install ccxt")
            return
        
        exchange_name = self.exchange_config.get("name", "bybit")
        testnet = self.exchange_config.get("testnet", True)
        
        try:
            if exchange_name == "bybit":
                if testnet:
                    self._exchange = ccxt.bybit({
                        "enableRateLimit": True,
                        "options": {"defaultType": "spot"},
                    })
                    self._exchange.set_sandbox_mode(True)
                else:
                    self._exchange = ccxt.bybit({
                        "enableRateLimit": True,
                        "apiKey": self.exchange_config.get("api_key"),
                        "secret": self.exchange_config.get("api_secret"),
                        "options": {"defaultType": "spot"},
                    })
            else:
                self._exchange = getattr(ccxt, exchange_name)({
                    "enableRateLimit": True,
                    "apiKey": self.exchange_config.get("api_key"),
                    "secret": self.exchange_config.get("api_secret"),
                })
            
            logger.info(f"Initialized {exchange_name} exchange (testnet={testnet})")
        except Exception as e:
            logger.error(f"Failed to initialize exchange: {e}")
            self._exchange = None
    
    @property
    def exchange(self):
        if self._exchange is None:
            self._init_exchange()
        return self._exchange
    
    def get_ohlcv(self, symbol: str, timeframe: str = "1D", limit: int = 100) -> Optional[pd.DataFrame]:
        """
        Fetch OHLCV candles for a symbol.
        
        Args:
            symbol: Trading pair (e.g., "BTC/USDT", "ETH/USDT")
            timeframe: "1h", "4h", "1D", "1w"
            limit: Number of candles to fetch
            
        Returns:
            DataFrame with columns: timestamp, open, high, low, close, volume
        """
        if self.exchange is None:
            logger.error("Exchange not initialized")
            return None
        
        try:
            ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
            
            if not ohlcv:
                logger.warning(f"No OHLCV data for {symbol}")
                return None
            
            df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
            df.set_index("timestamp", inplace=True)
            
            return df
            
        except Exception as e:
            logger.error(f"Failed to fetch OHLCV for {symbol}: {e}")
            return None
    
    def get_funding_rate(self, symbol: str, limit: int = 7) -> Optional[List[Dict]]:
        """
        Get funding rate history for a symbol (for perpetual futures context).
        For spot trading, this provides market sentiment data.
        
        Returns list of dicts with timestamp and funding_rate.
        """
        if self.exchange is None:
            return None
        
        try:
            if hasattr(self.exchange, "fetch_funding_rate_history"):
                history = self.exchange.fetch_funding_rate_history(symbol, limit=limit)
                return history
            else:
                current = self.exchange.fetch_funding_rate(symbol)
                return [{"timestamp": datetime.now().isoformat(), "fundingRate": current.get("fundingRate", 0)}]
        except Exception as e:
            logger.debug(f"Funding rate not available for {symbol}: {e}")
            return None
    
    def get_orderbook_depth(self, symbol: str, limit: int = 20) -> Optional[Dict]:
        """
        Get orderbook depth for liquidity check.
        
        Returns dict with bids, asks, and spread info.
        """
        if self.exchange is None:
            return None
        
        try:
            orderbook = self.exchange.fetch_order_book(symbol, limit=limit)
            
            best_bid = orderbook["bids"][0][0] if orderbook["bids"] else 0
            best_ask = orderbook["asks"][0][0] if orderbook["asks"] else 0
            spread = (best_ask - best_bid) / best_ask if best_ask > 0 else 0
            
            total_bid_volume = sum(b[1] for b in orderbook["bids"][:10])
            total_ask_volume = sum(a[1] for a in orderbook["asks"][:10])
            
            return {
                "best_bid": best_bid,
                "best_ask": best_ask,
                "spread_pct": spread * 100,
                "bid_volume": total_bid_volume,
                "ask_volume": total_ask_volume,
                "liquidity_ratio": total_bid_volume / total_ask_volume if total_ask_volume > 0 else 1,
            }
        except Exception as e:
            logger.debug(f"Orderbook not available for {symbol}: {e}")
            return None
    
    def get_current_price(self, symbol: str) -> Optional[float]:
        """Get current price for a symbol."""
        if self.exchange is None:
            return None
        
        try:
            ticker = self.exchange.fetch_ticker(symbol)
            return ticker.get("last")
        except Exception as e:
            logger.error(f"Failed to get price for {symbol}: {e}")
            return None
    
    def get_24h_ticker(self, symbol: str) -> Optional[Dict]:
        """Get 24h ticker data."""
        if self.exchange is None:
            return None
        
        try:
            return self.exchange.fetch_ticker(symbol)
        except Exception as e:
            logger.error(f"Failed to get 24h ticker for {symbol}: {e}")
            return None
    
    def calculate_rsi(self, df: pd.DataFrame, period: int = 14) -> pd.Series:
        """Calculate RSI indicator."""
        delta = df["close"].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        
        rs = gain / loss.replace(0, np.inf)
        rsi = 100 - (100 / (1 + rs))
        
        return rsi
    
    def calculate_macd(self, df: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9) -> Dict[str, pd.Series]:
        """Calculate MACD indicator."""
        ema_fast = df["close"].ewm(span=fast, adjust=False).mean()
        ema_slow = df["close"].ewm(span=slow, adjust=False).mean()
        
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal, adjust=False).mean()
        histogram = macd_line - signal_line
        
        return {
            "macd": macd_line,
            "signal": signal_line,
            "histogram": histogram,
        }
    
    def calculate_bollinger_bands(self, df: pd.DataFrame, period: int = 20, std_dev: float = 2.0) -> Dict[str, pd.Series]:
        """Calculate Bollinger Bands."""
        sma = df["close"].rolling(window=period).mean()
        std = df["close"].rolling(window=period).std()
        
        return {
            "upper": sma + (std * std_dev),
            "middle": sma,
            "lower": sma - (std * std_dev),
        }
    
    def calculate_volume_profile(self, df: pd.DataFrame, bins: int = 20) -> Dict:
        """Calculate volume profile over the period."""
        price_range = df["close"].max() - df["close"].min()
        bin_size = price_range / bins
        
        profile = {}
        for i in range(bins):
            lower = df["close"].min() + (i * bin_size)
            upper = lower + bin_size
            mask = (df["close"] >= lower) & (df["close"] < upper)
            profile[f"{lower:.4f}-{upper:.4f}"] = df.loc[mask, "volume"].sum()
        
        return profile
    
    def get_volume_ma_ratio(self, df: pd.DataFrame, short_period: int = 7, long_period: int = 30) -> float:
        """Get ratio of short-term to long-term volume MA (sustained volume growth indicator)."""
        short_ma = df["volume"].rolling(window=short_period).mean().iloc[-1]
        long_ma = df["volume"].rolling(window=long_period).mean().iloc[-1]
        
        return short_ma / long_ma if long_ma > 0 else 1.0
    
    def get_price_momentum(self, df: pd.DataFrame, periods: List[int] = [7, 30]) -> Dict[str, float]:
        """Get price momentum over different periods."""
        current_price = df["close"].iloc[-1]
        momentum = {}
        
        for period in periods:
            if len(df) >= period:
                past_price = df["close"].iloc[-period]
                momentum[f"{period}d"] = (current_price - past_price) / past_price * 100 if past_price > 0 else 0
        
        return momentum
    
    def detect_accumulation_pattern(self, df: pd.DataFrame, period: int = 14) -> bool:
        """
        Detect accumulation pattern:
        - Price relatively stable or declining
        - Volume increasing
        - RSI moving from oversold or staying elevated
        """
        if len(df) < period * 2:
            return False
        
        recent = df.tail(period)
        prior = df.iloc[-period * 2:-period]
        
        price_change = (recent["close"].iloc[-1] - recent["close"].iloc[0]) / recent["close"].iloc[0]
        volume_change = recent["volume"].mean() / prior["volume"].mean() if prior["volume"].mean() > 0 else 1
        
        rsi = self.calculate_rsi(df.tail(period * 2))
        rsi_trend = rsi.iloc[-1] - rsi.iloc[0]
        
        return (abs(price_change) < 0.05 and volume_change > 1.2 and rsi_trend > 5)
    
    def detect_higher_lows(self, df: pd.DataFrame, lookback: int = 10) -> bool:
        """Detect higher lows pattern on daily timeframe."""
        if len(df) < lookback:
            return False
        
        lows = df["low"].tail(lookback)
        
        for i in range(1, len(lows)):
            if lows.iloc[i] < lows.iloc[i - 1]:
                return False
        
        return True
    
    def detect_macd_crossover(self, df: pd.DataFrame) -> Dict[str, bool]:
        """Detect MACD bullish/bearish crossover on most recent candles."""
        macd = self.calculate_macd(df)
        
        current_macd = macd["macd"].iloc[-1]
        current_signal = macd["signal"].iloc[-1]
        prev_macd = macd["macd"].iloc[-2]
        prev_signal = macd["signal"].iloc[-2]
        
        return {
            "bullish_cross": prev_macd < prev_signal and current_macd > current_signal,
            "bearish_cross": prev_macd > prev_signal and current_macd < current_signal,
        }
    
    def get_technical_summary(self, symbol: str) -> Optional[Dict]:
        """
        Get comprehensive technical analysis summary for a symbol.
        Combines data from multiple timeframes.
        """
        daily_df = self.get_ohlcv(symbol, "1D", limit=90)
        if daily_df is None:
            return None
        
        h4_df = self.get_ohlcv(symbol, "4h", limit=100)
        
        summary = {
            "symbol": symbol,
            "current_price": daily_df["close"].iloc[-1],
            "rsi_14d": self.calculate_rsi(daily_df, 14).iloc[-1],
            "price_momentum": self.get_price_momentum(daily_df),
            "volume_ma_ratio": self.get_volume_ma_ratio(daily_df),
        }
        
        if len(daily_df) >= 30:
            summary["rsi_30d"] = self.calculate_rsi(daily_df, 30).iloc[-1]
        
        macd = self.calculate_macd(daily_df)
        summary["macd"] = {
            "value": macd["macd"].iloc[-1],
            "signal": macd["signal"].iloc[-1],
            "histogram": macd["histogram"].iloc[-1],
        }
        
        bb = self.calculate_bollinger_bands(daily_df)
        summary["bollinger"] = {
            "upper": bb["upper"].iloc[-1],
            "middle": bb["middle"].iloc[-1],
            "lower": bb["lower"].iloc[-1],
            "position": (daily_df["close"].iloc[-1] - bb["lower"].iloc[-1]) / (bb["upper"].iloc[-1] - bb["lower"].iloc[-1]),
        }
        
        summary["patterns"] = {
            "accumulation": self.detect_accumulation_pattern(daily_df),
            "higher_lows": self.detect_higher_lows(daily_df),
            "macd_cross": self.detect_macd_crossover(daily_df),
        }
        
        if h4_df is not None:
            summary["rsi_4h"] = self.calculate_rsi(h4_df, 14).iloc[-1]
        
        return summary


def format_symbol_for_exchange(symbol: str, exchange_name: str = "bybit") -> str:
    """Convert generic symbol format to exchange-specific format."""
    symbol = symbol.upper().strip()
    
    if "/" not in symbol:
        if symbol.endswith("USDT"):
            symbol = f"{symbol[:-4]}/USDT"
        elif symbol.endswith("USD"):
            symbol = f"{symbol[:-3]}/USD"
        else:
            symbol = f"{symbol}/USDT"
    
    if exchange_name == "bybit":
        return symbol.replace("/", "")
    
    return symbol
