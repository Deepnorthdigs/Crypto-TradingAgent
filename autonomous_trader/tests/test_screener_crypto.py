import pytest
import json
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestCryptoScreener:
    @patch("requests.Session")
    def test_screener_initialization(self, mock_session):
        from src.screener import CryptoScreener
        
        config = {
            "screener": {
                "min_market_cap": 10_000_000,
                "min_age_days": 14,
                "cache_ttl_minutes": 20,
                "momentum_window_days": 7,
            },
            "analysis": {"max_tickers_per_run": 10},
            "api_keys": {},
        }
        
        screener = CryptoScreener(config)
        
        assert screener.config == config
        assert screener.screener_config == config["screener"]
    
    @patch("requests.Session")
    def test_apply_filters_removes_low_market_cap(self, mock_session):
        from src.screener import CryptoScreener
        
        config = {
            "screener": {
                "min_market_cap": 10_000_000,
                "min_age_days": 14,
                "cache_ttl_minutes": 20,
            },
            "analysis": {"max_tickers_per_run": 10},
            "api_keys": {},
        }
        
        screener = CryptoScreener(config)
        
        coins = [
            {"symbol": "BIG", "market_cap": 500_000_000, "trust_score": 8, "age_days": 30},
            {"symbol": "SMALL", "market_cap": 1_000_000, "trust_score": 8, "age_days": 30},
        ]
        
        result = screener._apply_filters(coins)
        
        assert len(result) == 1
        assert result[0]["symbol"] == "BIG"
    
    @patch("requests.Session")
    def test_apply_filters_removes_low_trust_score(self, mock_session):
        from src.screener import CryptoScreener
        
        config = {
            "screener": {
                "min_market_cap": 1_000_000,
                "min_age_days": 14,
                "cache_ttl_minutes": 20,
            },
            "analysis": {"max_tickers_per_run": 10},
            "api_keys": {},
        }
        
        screener = CryptoScreener(config)
        
        coins = [
            {"symbol": "TRUSTED", "market_cap": 100_000_000, "trust_score": 8, "age_days": 30},
            {"symbol": "UNTRUSTED", "market_cap": 100_000_000, "trust_score": 2, "age_days": 30},
        ]
        
        result = screener._apply_filters(coins)
        
        assert len(result) == 1
        assert result[0]["symbol"] == "TRUSTED"
    
    @patch("requests.Session")
    def test_apply_filters_removes_unlock_flagged(self, mock_session):
        from src.screener import CryptoScreener
        
        config = {
            "screener": {
                "min_market_cap": 1_000_000,
                "min_age_days": 14,
                "cache_ttl_minutes": 20,
            },
            "analysis": {"max_tickers_per_run": 10},
            "api_keys": {},
        }
        
        screener = CryptoScreener(config)
        
        coins = [
            {"symbol": "CLEAN", "market_cap": 100_000_000, "trust_score": 8, "age_days": 30, "upcoming_unlock_flag": False},
            {"symbol": "UNLOCK", "market_cap": 100_000_000, "trust_score": 8, "age_days": 30, "upcoming_unlock_flag": True},
        ]
        
        result = screener._apply_filters(coins)
        
        assert len(result) == 1
        assert result[0]["symbol"] == "CLEAN"
    
    @patch("requests.Session")
    def test_rank_candidates(self, mock_session):
        from src.screener import CryptoScreener
        
        config = {
            "screener": {
                "min_market_cap": 1_000_000,
                "min_age_days": 14,
                "cache_ttl_minutes": 20,
            },
            "analysis": {"max_tickers_per_run": 10},
            "api_keys": {},
        }
        
        screener = CryptoScreener(config)
        
        coins = [
            {"symbol": "A", "price_change_percentage_7d_in_currency": 20, "price_change_percentage_30d": 30, 
             "volume_ratio": 1.5, "trust_score": 8},
            {"symbol": "B", "price_change_percentage_7d_in_currency": 5, "price_change_percentage_30d": 10,
             "volume_ratio": 1.0, "trust_score": 5},
        ]
        
        result = screener._rank_candidates(coins)
        
        assert len(result) == 2
        assert result[0]["symbol"] == "A"


class TestCryptoCache:
    def test_cache_set_and_get(self):
        from src.screener import CryptoCache
        
        cache = CryptoCache(ttl_minutes=5)
        cache.set("key1", {"data": "value"})
        
        result = cache.get("key1")
        assert result is not None
        assert result["data"] == "value"
    
    def test_cache_expiry(self):
        from src.screener import CryptoCache
        from datetime import datetime, timedelta
        
        cache = CryptoCache(ttl_minutes=1)
        cache._cache["key1"] = ({"data": "value"}, datetime.now() - timedelta(minutes=5))
        
        result = cache.get("key1")
        assert result is None
