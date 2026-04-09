import pytest
import pandas as pd
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestCryptoMarketData:
    @patch("ccxt.bybit")
    def test_initialization(self, mock_ccxt):
        from src.market_data import CryptoMarketData
        
        config = {
            "exchange": {
                "name": "bybit",
                "testnet": True,
            }
        }
        
        market_data = CryptoMarketData(config)
        assert market_data.config == config
    
    def test_calculate_rsi(self):
        from src.market_data import CryptoMarketData
        
        config = {
            "exchange": {"name": "bybit", "testnet": True}
        }
        
        market_data = CryptoMarketData(config)
        
        df = pd.DataFrame({
            "close": [100, 102, 101, 103, 105, 104, 106, 108, 107, 109, 110, 112, 111, 113, 115]
        })
        
        rsi = market_data.calculate_rsi(df, 14)
        
        assert rsi is not None
        assert len(rsi) == len(df)
    
    def test_calculate_macd(self):
        from src.market_data import CryptoMarketData
        
        config = {
            "exchange": {"name": "bybit", "testnet": True}
        }
        
        market_data = CryptoMarketData(config)
        
        df = pd.DataFrame({
            "close": list(range(50, 100))
        })
        
        macd = market_data.calculate_macd(df)
        
        assert "macd" in macd
        assert "signal" in macd
        assert "histogram" in macd
    
    def test_calculate_bollinger_bands(self):
        from src.market_data import CryptoMarketData
        
        config = {
            "exchange": {"name": "bybit", "testnet": True}
        }
        
        market_data = CryptoMarketData(config)
        
        df = pd.DataFrame({
            "close": list(range(50, 100))
        })
        
        bb = market_data.calculate_bollinger_bands(df)
        
        assert "upper" in bb
        assert "middle" in bb
        assert "lower" in bb
    
    def test_get_volume_ma_ratio(self):
        from src.market_data import CryptoMarketData
        
        config = {
            "exchange": {"name": "bybit", "testnet": True}
        }
        
        market_data = CryptoMarketData(config)
        
        close_prices = list(range(100, 140))
        volumes = [1000] * 40
        df = pd.DataFrame({
            "close": close_prices,
            "volume": volumes
        })
        
        ratio = market_data.get_volume_ma_ratio(df, 7, 30)
        
        assert isinstance(ratio, (int, float))
    
    def test_get_price_momentum(self):
        from src.market_data import CryptoMarketData
        
        config = {
            "exchange": {"name": "bybit", "testnet": True}
        }
        
        market_data = CryptoMarketData(config)
        
        df = pd.DataFrame({
            "close": list(range(100, 140))
        })
        
        momentum = market_data.get_price_momentum(df, [7, 30])
        
        assert "7d" in momentum
        assert momentum["7d"] > 0
    
    def test_detect_accumulation_pattern(self):
        from src.market_data import CryptoMarketData
        
        config = {
            "exchange": {"name": "bybit", "testnet": True}
        }
        
        market_data = CryptoMarketData(config)
        
        prices = [100, 99, 100, 98, 99, 100, 101, 100]
        volumes = [500, 600, 700, 800, 900, 1000, 1100, 1200]
        df = pd.DataFrame({"close": prices, "volume": volumes})
        
        detected = market_data.detect_accumulation_pattern(df, 7)
        
        assert isinstance(detected, bool)
    
    def test_detect_higher_lows(self):
        from src.market_data import CryptoMarketData
        
        config = {
            "exchange": {"name": "bybit", "testnet": True}
        }
        
        market_data = CryptoMarketData(config)
        
        df = pd.DataFrame({
            "low": [100, 102, 104, 106, 108],
            "close": [100, 102, 104, 106, 108],
        })
        
        detected = market_data.detect_higher_lows(df, 5)
        
        assert detected is True
        
        df2 = pd.DataFrame({
            "low": [100, 98, 104, 102, 108],
            "close": [100, 98, 104, 102, 108],
        })
        
        detected2 = market_data.detect_higher_lows(df2, 5)
        assert detected2 is False
    
    def test_detect_macd_crossover(self):
        from src.market_data import CryptoMarketData
        
        config = {
            "exchange": {"name": "bybit", "testnet": True}
        }
        
        market_data = CryptoMarketData(config)
        
        df = pd.DataFrame({
            "close": list(range(50, 100))
        })
        
        crossover = market_data.detect_macd_crossover(df)
        
        assert "bullish_cross" in crossover
        assert "bearish_cross" in crossover
    
    def test_format_symbol_for_exchange(self):
        from src.market_data import format_symbol_for_exchange
        
        assert format_symbol_for_exchange("BTC/USDT", "bybit") == "BTCUSDT"
        assert format_symbol_for_exchange("BTCUSDT", "bybit") == "BTCUSDT"
