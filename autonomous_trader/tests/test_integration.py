import pytest
import json
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path
import sys
import tempfile
import os

sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture
def temp_config():
    return {
        "alpaca": {
            "paper_key": "test_key",
            "paper_secret": "test_secret",
            "base_url": "https://paper-api.alpaca.markets",
        },
        "screening": {
            "universe": "sp500",
            "min_market_cap": 1_000_000_000,
            "max_pe": 25,
            "min_volume": 1_000_000,
            "min_revenue_growth": 0.10,
            "max_debt_equity": 1.5,
            "min_roe": 0.10,
            "exclude_sectors": ["Utilities", "Real Estate"],
            "max_per_industry": 5,
        },
        "analysis": {
            "model": "test",
            "max_tickers_per_run": 5,
            "timeout_minutes": 5,
            "prompt_template": "",
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
            "max_daily_loss_pct": 0.02,
            "max_drawdown_pct": 0.10,
            "max_position_value": 50000,
        },
        "schedule": {
            "market_hours_only": False,
            "timezone": "America/New_York",
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
    @patch("src.screener.StockScreener._init_sector_cache")
    @patch("pandas.read_html")
    @patch("src.screener.yf.Tickers")
    def test_screening_to_signals_pipeline(self, mock_yf, mock_read_html, mock_cache_init, temp_config):
        from src.screener import StockScreener
        from src.portfolio import TickerSectorCache
        
        mock_cache = MagicMock(spec=TickerSectorCache)
        mock_cache.set = Mock()
        mock_cache_init.return_value = mock_cache
        
        mock_read_html.return_value = [MagicMock()]
        mock_read_html.return_value[0] = MagicMock()
        mock_read_html.return_value[0].__getitem__ = Mock(return_value=["AAPL", "MSFT", "GOOGL"])
        
        mock_ticker_aapl = MagicMock()
        mock_ticker_aapl.info = {
            "marketCap": 2_000_000_000_000,
            "trailingPE": 25.0,
            "averageVolume": 50_000_000,
            "sector": "Technology",
            "industry": "Consumer Electronics",
            "returnOnEquity": 0.30,
            "debtToEquity": 0.5,
            "revenueGrowth": 0.15,
        }
        
        mock_yf_instance = MagicMock()
        mock_yf_instance.tickers = {"AAPL": mock_ticker_aapl}
        mock_yf.return_value = mock_yf_instance
        
        screener = StockScreener(temp_config)
        
        tickers = screener.screen()
        
        assert len(tickers) <= temp_config["analysis"]["max_tickers_per_run"]


class TestIntegrationComponents:
    def test_portfolio_tracking(self, temp_config):
        from src.portfolio import PositionTracker
        
        with tempfile.TemporaryDirectory() as tmpdir:
            positions_file = Path(tmpdir) / "positions.json"
            tracker = PositionTracker(positions_file)
            
            tracker.add_position({
                "symbol": "AAPL",
                "qty": 10,
                "avg_entry_price": 150.0,
                "market_value": 1500.0,
                "sector": "Technology",
            })
            
            assert tracker.is_holding("AAPL") is True
            assert tracker.get_position_count() == 1
            
            positions = tracker.get_positions()
            assert len(positions) == 1
            assert positions[0]["symbol"] == "AAPL"
    
    def test_sector_exposure_tracking(self, temp_config):
        from src.portfolio import PositionTracker
        
        with tempfile.TemporaryDirectory() as tmpdir:
            positions_file = Path(tmpdir) / "positions.json"
            tracker = PositionTracker(positions_file)
            
            tracker.add_position({
                "symbol": "AAPL",
                "qty": 10,
                "market_value": 1000.0,
                "sector": "Technology",
            })
            tracker.add_position({
                "symbol": "MSFT",
                "qty": 10,
                "market_value": 1000.0,
                "sector": "Technology",
            })
            
            exposure = tracker.get_sector_exposure()
            
            assert "Technology" in exposure
            assert abs(exposure["Technology"] - 1.0) < 0.001


class TestRiskManagement:
    def test_risk_manager_position_limits(self, temp_config):
        from src.portfolio import PositionTracker
        from src.risk import RiskManager
        
        with tempfile.TemporaryDirectory() as tmpdir:
            positions_file = Path(tmpdir) / "positions.json"
            tracker = PositionTracker(positions_file)
            
            for i in range(20):
                tracker.add_position({
                    "symbol": f"T{i}",
                    "qty": 1,
                    "market_value": 100.0,
                    "sector": "Technology",
                })
            
            risk_manager = RiskManager(temp_config, tracker)
            
            blocked, reason = risk_manager.check_position_limits()
            
            assert blocked is True
            assert "max limit" in reason
    
    def test_risk_manager_sector_concentration(self, temp_config):
        from src.portfolio import PositionTracker
        from src.risk import RiskManager
        
        with tempfile.TemporaryDirectory() as tmpdir:
            positions_file = Path(tmpdir) / "positions.json"
            tracker = PositionTracker(positions_file)
            
            tracker.add_position({
                "symbol": "AAPL",
                "qty": 10,
                "market_value": 8000.0,
                "sector": "Technology",
            })
            tracker.add_position({
                "symbol": "MSFT",
                "qty": 10,
                "market_value": 8000.0,
                "sector": "Technology",
            })
            
            risk_manager = RiskManager(temp_config, tracker)
            
            blocked, reason = risk_manager.check_sector_concentration("Technology")
            
            assert blocked is True


class TestMonitorLogging:
    def test_log_trade_creates_csv_entry(self, temp_config):
        from src.monitor import PortfolioMonitor
        
        with tempfile.TemporaryDirectory() as tmpdir:
            temp_config["logging"]["trade_log"] = os.path.join(tmpdir, "trade_log.csv")
            temp_config["logging"]["performance_log"] = os.path.join(tmpdir, "performance.csv")
            
            monitor = PortfolioMonitor(temp_config)
            
            trade = {
                "ticker": "AAPL",
                "action": "BUY",
                "quantity": 10,
                "price": 150.0,
                "total_value": 1500.0,
                "pnl": 0.0,
                "pnl_pct": 0.0,
                "sector": "Technology",
                "order_id": "test_order_123",
                "status": "filled",
            }
            
            monitor.log_trade(trade)
            
            log_path = Path(temp_config["logging"]["trade_log"])
            assert log_path.exists()
            
            with open(log_path, "r") as f:
                lines = f.readlines()
                assert len(lines) == 2
                assert "AAPL" in lines[1]
    
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
