import pytest
from unittest.mock import Mock, patch, MagicMock, PropertyMock
from pathlib import Path
from datetime import time
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestCryptoExecutor:
    def test_executor_initialization_dry_run(self):
        from src.executor import TradingExecutor
        
        config = {
            "exchange": {
                "name": "bybit",
                "testnet": True,
            },
            "trading": {
                "dry_run": True,
                "max_positions": 6,
                "position_size_pct": 0.05,
                "quiet_hours_start": "02:00",
                "quiet_hours_end": "05:00",
                "stop_loss_pct": 0.08,
                "take_profit_pct_1": 0.25,
                "take_profit_pct_2": 0.50,
            },
            "risk": {
                "max_position_value": 50000,
            },
        }
        
        executor = TradingExecutor(config)
        
        assert executor.dry_run is True
        assert executor._exchange is None
    
    def test_get_account_info_dry_run(self):
        from src.executor import TradingExecutor
        
        config = {
            "exchange": {"name": "bybit", "testnet": True},
            "trading": {"dry_run": True, "position_size_pct": 0.05},
            "risk": {"max_position_value": 50000},
        }
        
        executor = TradingExecutor(config)
        account = executor.get_account_info()
        
        assert account["equity"] == 100000.0
        assert account["buying_power"] == 100000.0
    
    def test_submit_bracket_order_dry_run(self):
        from src.executor import TradingExecutor
        
        config = {
            "exchange": {"name": "bybit", "testnet": True},
            "trading": {
                "dry_run": True,
                "position_size_pct": 0.05,
                "stop_loss_pct": 0.08,
                "take_profit_pct_1": 0.25,
                "take_profit_pct_2": 0.50,
                "partial_take_profit": True,
            },
            "risk": {"max_position_value": 50000},
        }
        
        executor = TradingExecutor(config)
        
        order = executor.submit_bracket_order(
            symbol="BTC/USDT",
            quantity=0.1,
            side="buy",
            target_price=50000,
            stop_price=46000,
            signal={}
        )
        
        assert order is not None
        assert order["symbol"] == "BTC/USDT"
        assert order["status"] == "dry_run"
        assert "child_orders" in order
    
    def test_validate_order_prices_valid(self):
        from src.executor import TradingExecutor
        
        config = {
            "exchange": {"name": "bybit", "testnet": True},
            "trading": {"dry_run": True, "position_size_pct": 0.05},
            "risk": {"max_position_value": 50000},
        }
        
        executor = TradingExecutor(config)
        
        result = executor._validate_order_prices("BTC/USDT", 50000, 60000, 46000)
        assert result is True
    
    def test_validate_order_prices_invalid(self):
        from src.executor import TradingExecutor
        
        config = {
            "exchange": {"name": "bybit", "testnet": True},
            "trading": {"dry_run": True, "position_size_pct": 0.05},
            "risk": {"max_position_value": 50000},
        }
        
        executor = TradingExecutor(config)
        
        result = executor._validate_order_prices("BTC/USDT", 50000, 52000, 51000)
        assert result is False
    
    def test_execute_signals_skips_existing_position(self):
        from src.executor import TradingExecutor
        
        config = {
            "exchange": {"name": "bybit", "testnet": True},
            "trading": {
                "dry_run": True,
                "max_positions": 6,
                "position_size_pct": 0.05,
                "stop_loss_pct": 0.08,
                "take_profit_pct_1": 0.25,
                "take_profit_pct_2": 0.50,
                "quiet_hours_start": "02:00",
                "quiet_hours_end": "05:00",
            },
            "risk": {"max_position_value": 50000},
        }
        
        executor = TradingExecutor(config)
        
        signals = [
            {
                "symbol": "BTC/USDT",
                "signal": "BUY",
                "confidence": 0.75,
            }
        ]
        
        with patch.object(executor, "get_current_positions", return_value=[{"symbol": "BTC/USDT"}]):
            with patch.object(executor, "get_current_price", return_value=50000):
                with patch("src.executor.datetime") as mock_datetime:
                    mock_dt = MagicMock()
                    mock_dt.time.return_value = time(10, 0)
                    mock_datetime.utcnow.return_value = mock_dt
                    report = executor.execute_signals(signals)
        
        assert len(report["skipped"]) == 1
        assert report["skipped"][0]["reason"] == "already_holding"
    
    def test_cancel_order(self):
        from src.executor import TradingExecutor
        
        config = {
            "exchange": {"name": "bybit", "testnet": True},
            "trading": {"dry_run": True, "position_size_pct": 0.05},
            "risk": {"max_position_value": 50000},
        }
        
        executor = TradingExecutor(config)
        
        result = executor.cancel_order("test_order_123", "BTC/USDT")
        assert result is True


class TestBracketOrderLogic:
    def test_bracket_order_creates_three_orders(self):
        from src.executor import TradingExecutor
        
        config = {
            "exchange": {"name": "bybit", "testnet": True},
            "trading": {
                "dry_run": True,
                "position_size_pct": 0.05,
                "stop_loss_pct": 0.08,
                "take_profit_pct_1": 0.25,
                "take_profit_pct_2": 0.50,
                "partial_take_profit": True,
            },
            "risk": {"max_position_value": 50000},
        }
        
        executor = TradingExecutor(config)
        
        order = executor.submit_bracket_order(
            symbol="ETH/USDT",
            quantity=1.0,
            side="buy",
            target_price=3000,
            stop_price=2760,
            signal={}
        )
        
        assert "tp1" in order["child_orders"]
        assert "tp2" in order["child_orders"]
        assert "sl" in order["child_orders"]
