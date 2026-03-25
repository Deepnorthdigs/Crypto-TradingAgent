import pytest
import json
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))


class MockConfig:
    def __init__(self):
        self._data = {
            "alpaca": {
                "paper_key": "test_key",
                "paper_secret": "test_secret",
                "base_url": "https://paper-api.alpaca.markets",
            },
            "trading": {
                "dry_run": True,
                "max_positions": 20,
                "position_size_pct": 0.05,
                "max_sector_exposure_pct": 0.20,
                "stop_loss_pct": 0.10,
                "take_profit_pct": 0.20,
                "min_confidence": 0.65,
            },
            "risk": {
                "max_position_value": 50000,
            },
        }
    
    def get(self, key, default=None):
        return self._data.get(key, default)


@pytest.fixture
def mock_config():
    return MockConfig()


class TestTradingExecutor:
    def test_executor_initialization_dry_run(self):
        from src.executor import TradingExecutor
        
        config = {
            "alpaca": {
                "paper_key": "test",
                "paper_secret": "test",
                "base_url": "https://paper-api.alpaca.markets",
            },
            "trading": {
                "dry_run": True,
                "max_positions": 20,
                "position_size_pct": 0.05,
            },
            "risk": {
                "max_position_value": 50000,
            },
        }
        
        executor = TradingExecutor(config)
        
        assert executor.dry_run is True
        assert executor._api is None
    
    def test_get_account_info_dry_run(self, mock_config):
        from src.executor import TradingExecutor
        
        config = mock_config._data
        executor = TradingExecutor(config)
        
        account = executor.get_account_info()
        
        assert account["equity"] == 100000.0
        assert account["buying_power"] == 100000.0
    
    def test_get_current_price_dry_run(self, mock_config):
        from src.executor import TradingExecutor
        
        config = mock_config._data
        executor = TradingExecutor(config)
        
        with patch("yfinance.Ticker") as mock_yf_ticker:
            mock_ticker = MagicMock()
            mock_ticker.info = {"currentPrice": 150.0}
            mock_yf_ticker.return_value = mock_ticker
            
            price = executor.get_current_price("AAPL")
        
        assert price == 150.0
    
    def test_calculate_position_size(self, mock_config):
        from src.executor import TradingExecutor
        
        config = mock_config._data
        executor = TradingExecutor(config)
        
        signal = {
            "ticker": "AAPL",
            "confidence": 0.75,
        }
        
        with patch.object(executor, "get_current_price", return_value=150.0):
            qty, price = executor.calculate_position_size(signal, 100000.0)
        
        assert qty > 0
        assert price == 150.0
    
    def test_validate_order_prices_valid(self, mock_config):
        from src.executor import TradingExecutor
        
        config = mock_config._data
        executor = TradingExecutor(config)
        
        result = executor._validate_order_prices("AAPL", 150.0, 180.0, 135.0)
        
        assert result is True
    
    def test_validate_order_prices_invalid(self, mock_config):
        from src.executor import TradingExecutor
        
        config = mock_config._data
        executor = TradingExecutor(config)
        
        result = executor._validate_order_prices("AAPL", 150.0, 160.0, 155.0)
        
        assert result is False


class TestBracketOrderSubmission:
    def test_submit_bracket_order_dry_run(self, mock_config):
        from src.executor import TradingExecutor
        
        config = mock_config._data
        executor = TradingExecutor(config)
        
        order = executor.submit_bracket_order(
            ticker="AAPL",
            quantity=10,
            side="buy",
            target_price=180.0,
            stop_price=135.0,
            signal={}
        )
        
        assert order is not None
        assert order["symbol"] == "AAPL"
        assert order["status"] == "dry_run"


class TestExecuteSignals:
    def test_execute_signals_skips_existing_position(self, mock_config):
        from src.executor import TradingExecutor
        
        config = mock_config._data
        executor = TradingExecutor(config)
        
        signals = [
            {
                "ticker": "AAPL",
                "recommendation": "BUY",
                "confidence": 0.75,
                "target_price": 180.0,
                "stop_loss": 135.0,
            }
        ]
        
        with patch.object(executor, "get_current_positions", return_value=[{"symbol": "AAPL"}]):
            with patch.object(executor, "get_current_price", return_value=150.0):
                report = executor.execute_signals(signals)
        
        assert len(report["skipped"]) == 1
        assert report["skipped"][0]["reason"] == "already_holding"


class TestRiskChecks:
    def test_position_size_respects_max_value(self, mock_config):
        from src.executor import TradingExecutor
        
        config = mock_config._data
        config["risk"]["max_position_value"] = 1000
        
        executor = TradingExecutor(config)
        
        signal = {
            "ticker": "AAPL",
            "confidence": 0.90,
        }
        
        with patch.object(executor, "get_current_price", return_value=50.0):
            qty, price = executor.calculate_position_size(signal, 100000.0)
        
        max_value = config["risk"]["max_position_value"]
        assert qty * price <= max_value + 50
