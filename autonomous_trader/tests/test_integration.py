import pytest
import json
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path
import sys
import tempfile
import os
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture
def temp_config():
    return {
        "exchange": {
            "name": "bybit",
            "testnet": True,
        },
        "screener": {
            "universe": "crypto",
            "min_market_cap": 10_000_000,
            "min_age_days": 14,
            "cache_ttl_minutes": 20,
        },
        "analysis": {
            "model": "test",
            "max_tickers_per_run": 5,
            "timeout_minutes": 5,
            "prompt_template": "",
            "weights": {
                "technical": 0.25,
                "sentiment": 0.25,
                "fundamentals": 0.30,
                "project_quality": 0.20,
            },
            "btc_rsi_filter": 35,
        },
        "trading": {
            "dry_run": True,
            "max_positions": 6,
            "position_size_pct": 0.05,
            "stop_loss_pct": 0.08,
            "take_profit_pct_1": 0.25,
            "take_profit_pct_2": 0.50,
            "min_confidence": 0.65,
            "quiet_hours_start": "02:00",
            "quiet_hours_end": "05:00",
        },
        "risk": {
            "max_daily_loss_pct": 0.02,
            "max_drawdown_pct": 0.10,
            "max_position_value": 50000,
            "max_holding_days": 60,
            "holding_alert_days": 45,
            "max_defi_exposure_pct": 0.30,
            "max_l1_exposure_pct": 0.30,
            "max_l2_exposure_pct": 0.30,
            "max_memecoin_exposure_pct": 0.20,
        },
        "schedule": {
            "market_hours_only": False,
            "timezone": "UTC",
        },
        "logging": {
            "level": "INFO",
            "log_file": "logs/test_trading_agent.log",
            "trade_log": "data/test_trade_log.csv",
            "performance_log": "data/test_performance.csv",
        },
        "alerts": {
            "enabled": False,
            "discord_webhook": "",
            "notify_on": [],
        },
    }


class TestFullPipeline:
    @patch("src.screener.CryptoScreener._init_session")
    def test_screening_to_signals_pipeline(self, mock_session, temp_config):
        from src.screener import CryptoScreener
        
        screener = CryptoScreener(temp_config)
        with patch.object(screener, "_get_coingecko_trending", return_value=[]):
            tickers = screener.screen()
            assert isinstance(tickers, list)


class TestIntegrationComponents:
    def test_portfolio_tracking(self, temp_config):
        from src.portfolio import PositionTracker
        
        with tempfile.TemporaryDirectory() as tmpdir:
            positions_file = Path(tmpdir) / "positions.json"
            tracker = PositionTracker(positions_file)
            
            tracker.add_position({
                "symbol": "BTC/USDT",
                "qty": 0.1,
                "avg_entry_price": 50000.0,
                "market_value": 5000.0,
                "category": "L1",
            })
            
            assert tracker.is_holding("BTC/USDT") is True
            assert tracker.get_position_count() == 1
            
            positions = tracker.get_positions()
            assert len(positions) == 1
            assert positions[0]["symbol"] == "BTC/USDT"
    
    def test_category_exposure_tracking(self, temp_config):
        from src.portfolio import PositionTracker
        
        with tempfile.TemporaryDirectory() as tmpdir:
            positions_file = Path(tmpdir) / "positions.json"
            tracker = PositionTracker(positions_file)
            
            tracker.add_position({
                "symbol": "BTC/USDT",
                "qty": 0.1,
                "market_value": 1000.0,
                "category": "L1",
            })
            tracker.add_position({
                "symbol": "ETH/USDT",
                "qty": 1.0,
                "market_value": 1000.0,
                "category": "L1",
            })
            
            exposure = tracker.get_category_exposure()
            
            assert "L1" in exposure
            assert abs(exposure["L1"] - 1.0) < 0.001


class TestRiskManagement:
    def test_risk_manager_position_limits(self, temp_config):
        from src.portfolio import PositionTracker
        from src.risk import RiskManager
        
        with tempfile.TemporaryDirectory() as tmpdir:
            positions_file = Path(tmpdir) / "positions.json"
            tracker = PositionTracker(positions_file)
            
            for i in range(6):
                tracker.add_position({
                    "symbol": f"T{i}/USDT",
                    "qty": 1,
                    "market_value": 100.0,
                    "category": "L1",
                })
            
            risk_manager = RiskManager(temp_config, tracker)
            
            blocked, reason = risk_manager.check_position_limits()
            
            assert blocked is True
            assert "max limit" in reason
    
    def test_risk_manager_category_concentration(self, temp_config):
        from src.portfolio import PositionTracker
        from src.risk import RiskManager
        
        with tempfile.TemporaryDirectory() as tmpdir:
            positions_file = Path(tmpdir) / "positions.json"
            tracker = PositionTracker(positions_file)
            
            tracker.add_position({
                "symbol": "AAVE/USDT",
                "qty": 10,
                "market_value": 8000.0,
                "category": "DeFi",
            })
            tracker.add_position({
                "symbol": "UNI/USDT",
                "qty": 100,
                "market_value": 8000.0,
                "category": "DeFi",
            })
            
            risk_manager = RiskManager(temp_config, tracker)
            
            blocked, reason = risk_manager.check_category_concentration("DeFi")
            
            assert blocked is True


class TestMonitorLogging:
    def test_log_trade_creates_csv_entry(self, temp_config):
        from src.monitor import PortfolioMonitor
        
        with tempfile.TemporaryDirectory() as tmpdir:
            temp_config["logging"]["trade_log"] = os.path.join(tmpdir, "trade_log.csv")
            temp_config["logging"]["performance_log"] = os.path.join(tmpdir, "performance.csv")
            
            monitor = PortfolioMonitor(temp_config)
            
            trade = {
                "symbol": "BTC/USDT",
                "action": "BUY",
                "quantity": 0.1,
                "price": 50000.0,
                "total_value": 5000.0,
                "pnl": 0.0,
                "pnl_pct": 0.0,
                "category": "L1",
                "order_id": "test_order_123",
                "status": "filled",
            }
            
            monitor.log_trade(trade)
            
            log_path = Path(temp_config["logging"]["trade_log"])
            assert log_path.exists()
            
            with open(log_path, "r") as f:
                lines = f.readlines()
                assert len(lines) == 2
                assert "BTC/USDT" in lines[1]
    
    def test_calculate_daily_metrics(self, temp_config):
        from src.monitor import PortfolioMonitor
        
        with tempfile.TemporaryDirectory() as tmpdir:
            temp_config["logging"]["trade_log"] = os.path.join(tmpdir, "trade_log.csv")
            temp_config["logging"]["performance_log"] = os.path.join(tmpdir, "performance.csv")
            
            monitor = PortfolioMonitor(temp_config)
            
            closed_positions = [
                {"pnl": 100.0},
                {"pnl": 50.0},
                {"pnl": -30.0},
            ]
            
            metrics = monitor.calculate_daily_metrics(10000.0, closed_positions)
            
            assert metrics["total_trades"] == 3
            assert metrics["winning_trades"] == 2
            assert metrics["losing_trades"] == 1
            assert abs(metrics["win_rate"] - 2/3) < 0.01
