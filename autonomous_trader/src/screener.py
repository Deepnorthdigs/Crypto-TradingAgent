"""
Crypto Screener - Multi-Source Discovery Pipeline
Replaces stock screening with crypto-focused discovery from multiple sources.
"""

import json
import logging
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, List, Any

import pandas as pd
import requests

try:
    import requests_cache
    CACHE_AVAILABLE = True
except ImportError:
    CACHE_AVAILABLE = False


logger = logging.getLogger("autonomous_trader")


class CryptoCache:
    """Simple TTL cache for API responses."""
    
    def __init__(self, ttl_minutes: int = 20):
        self.ttl_minutes = ttl_minutes
        self._cache: Dict[str, tuple[Any, datetime]] = {}
    
    def get(self, key: str) -> Optional[Any]:
        if key in self._cache:
            data, timestamp = self._cache[key]
            age_minutes = (datetime.now() - timestamp).total_seconds() / 60
            if age_minutes < self.ttl_minutes:
                return data
            del self._cache[key]
        return None
    
    def set(self, key: str, data: Any) -> None:
        self._cache[key] = (data, datetime.now())
    
    def clear(self) -> None:
        self._cache.clear()


class CryptoScreener:
    def __init__(self, config: dict):
        self.config = config
        self.screener_config = config.get("screener", {})
        self.api_keys = config.get("api_keys", {})
        self._cache = CryptoCache(
            ttl_minutes=self.screener_config.get("cache_ttl_minutes", 20)
        )
        self._init_session()
    
    def _init_session(self):
        self._session = requests.Session()
        if CACHE_AVAILABLE:
            try:
                self._session = requests_cache.CachedSession(
                    cache_name="crypto_cache",
                    expire_after=self.screener_config.get("cache_ttl_minutes", 20) * 60
                )
            except Exception as e:
                logger.warning(f"requests_cache init failed: {e}")
    
    def _get_coingecko_trending(self) -> List[Dict]:
        """Fetch trending coins from CoinGecko."""
        cache_key = "coingecko_trending"
        cached = self._cache.get(cache_key)
        if cached:
            return cached
        
        try:
            url = "https://api.coingecko.com/api/v3/search/trending"
            response = self._session.get(url, timeout=15)
            
            if response.status_code == 200:
                data = response.json()
                coins = []
                for item in data.get("coins", []):
                    coin = item.get("item", {})
                    coins.append({
                        "id": coin.get("id"),
                        "symbol": coin.get("symbol", "").upper(),
                        "name": coin.get("name"),
                        "market_cap_rank": coin.get("market_cap_rank"),
                        "score": item.get("score"),
                    })
                
                self._cache.set(cache_key, coins)
                logger.info(f"CoinGecko trending: {len(coins)} coins")
                return coins
            else:
                logger.warning(f"CoinGecko trending API error: {response.status_code}")
        except Exception as e:
            logger.warning(f"CoinGecko trending fetch failed: {e}")
        
        return []
    
    def _get_coingecko_market_data(self, coin_ids: List[str]) -> List[Dict]:
        """Fetch market data for multiple coins from CoinGecko."""
        if not coin_ids:
            return []
        
        cache_key = f"coingecko_market_{','.join(coin_ids[:50])}"
        cached = self._cache.get(cache_key)
        if cached:
            return cached
        
        try:
            api_key = self.api_keys.get("coingecko")
            headers = {}
            if api_key:
                headers["x-cg-demo-api-key"] = api_key
            
            ids_param = ",".join(coin_ids[:100])
            url = f"https://api.coingecko.com/api/v3/coins/markets"
            params = {
                "vs_currency": "usd",
                "ids": ids_param,
                "order": "market_cap_desc",
                "per_page": 100,
                "page": 1,
                "sparkline": "false",
                "price_change_percentage": "7d,30d",
            }
            
            response = self._session.get(url, headers=headers, params=params, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                self._cache.set(cache_key, data)
                return data
            else:
                logger.warning(f"CoinGecko markets API error: {response.status_code}")
        except Exception as e:
            logger.warning(f"CoinGecko market data fetch failed: {e}")
        
        return []
    
    def _get_coingecko_coin_details(self, coin_id: str) -> Optional[Dict]:
        """Fetch detailed info for a single coin from CoinGecko."""
        cache_key = f"coingecko_detail_{coin_id}"
        cached = self._cache.get(cache_key)
        if cached:
            return cached
        
        try:
            api_key = self.api_keys.get("coingecko")
            headers = {}
            if api_key:
                headers["x-cg-demo-api-key"] = api_key
            
            url = f"https://api.coingecko.com/api/v3/coins/{coin_id}"
            params = {
                "localization": "false",
                "tickers": "false",
                "community_data": "false",
                "developer_data": "true",
            }
            
            response = self._session.get(url, headers=headers, params=params, timeout=15)
            
            if response.status_code == 200:
                data = response.json()
                self._cache.set(cache_key, data)
                return data
        except Exception as e:
            logger.debug(f"CoinGecko detail fetch failed for {coin_id}: {e}")
        
        return None
    
    def _get_cryptopanic_news(self, filter_currency: str = "BTC,ETH") -> List[Dict]:
        """Fetch trending news from CryptoPanic."""
        cache_key = "cryptopanic_news"
        cached = self._cache.get(cache_key)
        if cached:
            return cached
        
        try:
            api_key = self.api_keys.get("cryptopanic")
            if not api_key:
                logger.debug("CryptoPanic API key not configured")
                return []
            
            url = "https://cryptopanic.com/api/v1/posts/"
            params = {
                "auth_token": api_key,
                "kind": "news",
                "currencies": filter_currency,
                "filter": "hot",
            }
            
            response = self._session.get(url, params=params, timeout=15)
            
            if response.status_code == 200:
                data = response.json()
                posts = []
                for item in data.get("results", []):
                    posts.append({
                        "title": item.get("title"),
                        "published_at": item.get("published_at"),
                        "votes": item.get("votes", {}).get("positive", 0),
                        "currencies": [c.get("code") for c in item.get("currencies", [])],
                    })
                
                self._cache.set(cache_key, posts)
                return posts
        except Exception as e:
            logger.debug(f"CryptoPanic fetch failed: {e}")
        
        return []
    
    def _get_coinmarketcap_trending(self) -> List[Dict]:
        """Fetch trending coins from CoinMarketCap."""
        cache_key = "coinmarketcap_trending"
        cached = self._cache.get(cache_key)
        if cached:
            return cached
        
        try:
            api_key = self.api_keys.get("coinmarketcap")
            if not api_key:
                logger.debug("CoinMarketCap API key not configured")
                return []
            
            url = "https://pro-api.coinmarketcap.com/v1/cryptocurrency/trending/most-visited"
            headers = {
                "X-CMC_PRO_API_KEY": api_key,
            }
            
            response = self._session.get(url, headers=headers, timeout=15)
            
            if response.status_code == 200:
                data = response.json()
                coins = []
                for item in data.get("data", []):
                    coins.append({
                        "id": item.get("id"),
                        "symbol": item.get("symbol", "").upper(),
                        "name": item.get("name"),
                        "rank": item.get("cmc_rank"),
                    })
                
                self._cache.set(cache_key, coins)
                return coins
        except Exception as e:
            logger.debug(f"CoinMarketCap trending fetch failed: {e}")
        
        return []
    
    def _apply_filters(self, coins: List[Dict]) -> List[Dict]:
        """Apply quality filters before returning candidates."""
        config = self.screener_config
        
        min_market_cap = config.get("min_market_cap", 10_000_000)
        min_age_days = config.get("min_age_days", 14)
        
        filtered = []
        
        for coin in coins:
            market_cap = coin.get("market_cap", 0) or 0
            
            if market_cap < min_market_cap:
                logger.debug(f"Filtered {coin.get('symbol')}: market cap ${market_cap:,.0f} below minimum")
                continue
            
            if coin.get("trust_score", 10) < 3:
                logger.debug(f"Filtered {coin.get('symbol')}: trust score {coin.get('trust_score')} below 3")
                continue
            
            if coin.get("upcoming_unlock_flag"):
                logger.debug(f"Filtered {coin.get('symbol')}: upcoming unlock >5% circulating supply")
                continue
            
            if coin.get("age_days", 999) < min_age_days:
                logger.debug(f"Filtered {coin.get('symbol')}: age {coin.get('age_days')} days below minimum {min_age_days}")
                continue
            
            filtered.append(coin)
        
        return filtered
    
    def _rank_candidates(self, coins: List[Dict]) -> List[Dict]:
        """Score and rank candidates based on swing trading metrics."""
        if not coins:
            return []
        
        df = pd.DataFrame(coins)
        
        df["momentum_7d"] = pd.to_numeric(df.get("price_change_percentage_7d_in_currency", 0), errors="coerce").fillna(0)
        df["momentum_30d"] = pd.to_numeric(df.get("price_change_percentage_30d", 0), errors="coerce").fillna(0)
        df["volume_ratio"] = pd.to_numeric(df.get("volume_ratio", 1.0), errors="coerce").fillna(1.0)
        df["trust_score"] = pd.to_numeric(df.get("trust_score", 10), errors="coerce").fillna(10)
        
        df["momentum_score"] = (df["momentum_7d"] * 2 + df["momentum_30d"]) / 3
        df["momentum_score"] = (df["momentum_score"] - df["momentum_score"].min()) / (df["momentum_score"].max() - df["momentum_score"].min() + 0.001)
        
        df["volume_score"] = (df["volume_ratio"] - df["volume_ratio"].min()) / (df["volume_ratio"].max() - df["volume_ratio"].min() + 0.001)
        
        df["trust_score_norm"] = df["trust_score"] / 10
        
        df["composite_score"] = (
            0.40 * df["momentum_score"] +
            0.30 * df["volume_score"] +
            0.30 * df["trust_score_norm"]
        )
        
        df = df.sort_values("composite_score", ascending=False)
        
        return df.to_dict("records")
    
    def screen(self) -> List[str]:
        """Main screening entry point. Returns list of coin symbols."""
        logger.info("Starting crypto screening...")
        
        all_candidates = []
        
        try:
            trending_coingecko = self._get_coingecko_trending()
            if trending_coingecko:
                coin_ids = [c["id"] for c in trending_coingecko]
                market_data = self._get_coingecko_market_data(coin_ids)
                
                for item in market_data:
                    all_candidates.append({
                        "id": item.get("id"),
                        "symbol": item.get("symbol", "").upper(),
                        "name": item.get("name"),
                        "market_cap": item.get("market_cap"),
                        "market_cap_rank": item.get("market_cap_rank"),
                        "price": item.get("current_price"),
                        "price_change_percentage_7d_in_currency": item.get("price_change_percentage_7d_in_currency"),
                        "price_change_percentage_30d": item.get("price_change_percentage_30d"),
                        "volume_24h": item.get("total_volume"),
                        "trust_score": item.get("coingecko_trust_score") or item.get("trust_score", 10),
                        "image": item.get("image"),
                        "circulating_supply": item.get("circulating_supply"),
                        "max_supply": item.get("max_supply"),
                    })
        except Exception as e:
            logger.error(f"CoinGecko screening failed: {e}")
        
        try:
            trending_cmc = self._get_coinmarketcap_trending()
            if trending_cmc:
                coin_ids = [c["id"] for c in trending_cmc if c.get("id")]
                if coin_ids:
                    market_data = self._get_coingecko_market_data(coin_ids)
                    for item in market_data:
                        if not any(c.get("id") == item.get("id") for c in all_candidates):
                            all_candidates.append({
                                "id": item.get("id"),
                                "symbol": item.get("symbol", "").upper(),
                                "name": item.get("name"),
                                "market_cap": item.get("market_cap"),
                                "market_cap_rank": item.get("market_cap_rank"),
                                "price": item.get("current_price"),
                                "price_change_percentage_7d_in_currency": item.get("price_change_percentage_7d_in_currency"),
                                "price_change_percentage_30d": item.get("price_change_percentage_30d"),
                                "volume_24h": item.get("total_volume"),
                                "trust_score": item.get("coingecko_trust_score") or 5,
                                "image": item.get("image"),
                            })
        except Exception as e:
            logger.warning(f"CoinMarketCap screening failed: {e}")
        
        logger.info(f"Discovered {len(all_candidates)} candidates from API sources")
        
        filtered = self._apply_filters(all_candidates)
        logger.info(f"After filtering: {len(filtered)} candidates remain")
        
        ranked = self._rank_candidates(filtered)
        
        max_tickers = self.config.get("analysis", {}).get("max_tickers_per_run", 10)
        top_coins = ranked[:max_tickers]
        
        symbols = [c["symbol"] for c in top_coins]
        
        self._save_screened_results(ranked)
        
        logger.info(f"Screened results: {len(symbols)} coins selected: {symbols}")
        return symbols
    
    def get_candidate_details(self, symbol: str) -> Optional[Dict]:
        """Get full details for a candidate coin."""
        trending = self._get_coingecko_trending()
        coin_ids = [c["id"] for c in trending]
        
        if not coin_ids:
            return None
        
        market_data = self._get_coingecko_market_data(coin_ids)
        
        for coin in market_data:
            if coin.get("symbol", "").upper() == symbol.upper():
                return coin
        
        return None
    
    def _save_screened_results(self, coins: List[Dict]) -> None:
        """Save screening results to file."""
        from .logger import get_data_dir
        
        screened_dir = get_data_dir() / "screened"
        screened_dir.mkdir(parents=True, exist_ok=True)
        
        date_str = datetime.now().strftime("%Y-%m-%d")
        output_path = screened_dir / f"crypto_screened_{date_str}.json"
        
        with open(output_path, "w") as f:
            json.dump(coins, f, indent=2)
        
        logger.info(f"Saved screened results to {output_path}")


StockScreener = CryptoScreener
