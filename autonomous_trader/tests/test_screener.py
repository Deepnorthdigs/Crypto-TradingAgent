import pytest
import json
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))


class MockConfig:
    def __init__(self):
        self._data = {
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
                "max_tickers_per_run": 10,
            },
        }
    
    def get(self, key, default=None):
        return self._data.get(key, default)


@pytest.fixture
def mock_config():
    return MockConfig()


@pytest.fixture
def mock_sector_cache():
    from src.portfolio import TickerSectorCache
    cache = Mock(spec=TickerSectorCache)
    cache.set = Mock()
    cache.get = Mock(return_value=None)
    return cache


class TestStockScreener:
    @patch("src.screener.StockScreener._init_sector_cache")
    def test_screener_initialization(self, mock_init_cache, mock_config):
        from src.screener import StockScreener
        
        mock_init_cache.return_value = Mock()
        
        screener = StockScreener(mock_config._data)
        
        assert screener.config == mock_config._data
        assert screener.screening_config == mock_config._data["screening"]
    
    @patch("src.screener.yf.Tickers")
    @patch("src.screener.StockScreener._init_sector_cache")
    @patch("pandas.read_html")
    def test_download_fundamentals(self, mock_read_html, mock_init_cache, mock_yf):
        from src.screener import StockScreener
        
        mock_init_cache.return_value = Mock()
        mock_config_data = {
            "screening": {
                "universe": "sp500",
                "min_market_cap": 1_000_000_000,
                "max_pe": 25,
                "min_volume": 1_000_000,
                "min_revenue_growth": 0.10,
                "max_debt_equity": 1.5,
                "min_roe": 0.10,
                "exclude_sectors": ["Utilities"],
                "max_per_industry": 5,
            },
            "analysis": {"max_tickers_per_run": 10},
        }
        
        screener = StockScreener(mock_config_data)
        
        mock_ticker = MagicMock()
        mock_ticker.info = {
            "marketCap": 1_000_000_000_000,
            "trailingPE": 22.0,
            "averageVolume": 50_000_000,
            "sector": "Technology",
            "industry": "Semiconductors",
            "returnOnEquity": 0.25,
            "debtToEquity": 0.5,
            "revenueGrowth": 0.15,
        }
        
        mock_yf_instance = MagicMock()
        mock_yf_instance.tickers = {"AAPL": mock_ticker}
        mock_yf.return_value = mock_yf_instance
        
        tickers = ["AAPL"]
        result = screener._download_fundamentals(tickers)
        
        assert len(result) == 1
        assert result.iloc[0]["ticker"] == "AAPL"
        assert result.iloc[0]["market_cap"] == 1_000_000_000_000
        assert result.iloc[0]["pe_ratio"] == 22.0


class TestFilterLogic:
    def test_apply_filters_removes_low_market_cap(self):
        import pandas as pd
        from src.screener import StockScreener
        
        config = {
            "screening": {
                "universe": "sp500",
                "min_market_cap": 1_000_000_000,
                "max_pe": 25,
                "min_volume": 1_000_000,
                "min_revenue_growth": 0.10,
                "max_debt_equity": 1.5,
                "min_roe": 0.10,
                "exclude_sectors": ["Utilities"],
                "max_per_industry": 5,
            },
            "analysis": {"max_tickers_per_run": 10},
        }
        
        screener = StockScreener(config)
        
        df = pd.DataFrame([
            {"ticker": "BIG", "market_cap": 500_000_000_000, "pe_ratio": 20, "volume": 10_000_000,
             "roe": 0.2, "debt_equity": 0.5, "revenue_growth": 0.15, "sector": "Tech", "industry": "Software"},
            {"ticker": "SMALL", "market_cap": 100_000_000, "pe_ratio": 15, "volume": 500_000,
             "roe": 0.15, "debt_equity": 0.3, "revenue_growth": 0.12, "sector": "Tech", "industry": "Software"},
        ])
        
        result = screener._apply_filters(df)
        
        assert len(result) == 1
        assert result.iloc[0]["ticker"] == "BIG"
    
    def test_apply_filters_removes_excluded_sectors(self):
        import pandas as pd
        from src.screener import StockScreener
        
        config = {
            "screening": {
                "universe": "sp500",
                "min_market_cap": 1_000_000,
                "max_pe": 50,
                "min_volume": 100,
                "min_revenue_growth": -0.1,
                "max_debt_equity": 10,
                "min_roe": 0.0,
                "exclude_sectors": ["Utilities", "Real Estate"],
                "max_per_industry": 5,
            },
            "analysis": {"max_tickers_per_run": 10},
        }
        
        screener = StockScreener(config)
        
        df = pd.DataFrame([
            {"ticker": "TECH", "market_cap": 1_000_000_000, "pe_ratio": 20, "volume": 10_000_000,
             "roe": 0.2, "debt_equity": 0.5, "revenue_growth": 0.15, "sector": "Technology", "industry": "Software"},
            {"ticker": "UTIL", "market_cap": 1_000_000_000, "pe_ratio": 15, "volume": 5_000_000,
             "roe": 0.1, "debt_equity": 0.3, "revenue_growth": 0.05, "sector": "Utilities", "industry": "Electric"},
        ])
        
        result = screener._apply_filters(df)
        
        assert len(result) == 1
        assert result.iloc[0]["ticker"] == "TECH"


class TestRanking:
    def test_rank_candidates_composite_score(self):
        import pandas as pd
        from src.screener import StockScreener
        
        config = {
            "screening": {
                "universe": "sp500",
                "min_market_cap": 1_000_000,
                "max_pe": 50,
                "min_volume": 100,
                "min_revenue_growth": -0.1,
                "max_debt_equity": 10,
                "min_roe": 0.0,
                "exclude_sectors": [],
                "max_per_industry": 5,
            },
            "analysis": {"max_tickers_per_run": 10},
        }
        
        screener = StockScreener(config)
        
        df = pd.DataFrame([
            {"ticker": "A", "market_cap": 100_000_000_000, "pe_ratio": 10, "volume": 10_000_000,
             "roe": 0.3, "debt_equity": 0.1, "revenue_growth": 0.3, "sector": "Tech", "industry": "Software"},
            {"ticker": "B", "market_cap": 50_000_000_000, "pe_ratio": 30, "volume": 5_000_000,
             "roe": 0.1, "debt_equity": 1.0, "revenue_growth": 0.05, "sector": "Tech", "industry": "Hardware"},
        ])
        
        result = screener._rank_candidates(df)
        
        assert "composite_score" in result.columns
        assert result.iloc[0]["ticker"] == "A"
