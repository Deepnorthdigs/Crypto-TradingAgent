import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd
import yfinance as yf


logger = logging.getLogger("autonomous_trader")


class StockScreener:
    def __init__(self, config: dict):
        self.config = config
        self.screening_config = config.get("screening", {})
        self._sector_cache = self._init_sector_cache()
    
    def _init_sector_cache(self) -> dict:
        from .portfolio import TickerSectorCache
        return TickerSectorCache()
    
    def _get_sp500_tickers(self) -> list:
        try:
            tables = pd.read_html("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies")
            tickers = tables[0]["Symbol"].tolist()
            return [t.replace(".", "-") for t in tickers]
        except Exception as e:
            logger.error(f"Failed to fetch S&P 500 tickers: {e}")
            return []
    
    def _get_nasdaq100_tickers(self) -> list:
        try:
            tables = pd.read_html("https://en.wikipedia.org/wiki/NASDAQ-100")
            tickers = tables[4]["Ticker"].tolist()
            return [t.replace(".", "-") for t in tickers]
        except Exception as e:
            logger.error(f"Failed to fetch NASDAQ-100 tickers: {e}")
            return []
    
    def _load_custom_tickers(self, universe: str) -> list:
        path = Path(universe.replace("custom:", ""))
        if path.exists():
            with open(path, "r") as f:
                return [line.strip() for line in f if line.strip()]
        return []
    
    def _get_universe_tickers(self) -> list:
        universe = self.screening_config.get("universe", "sp500").lower()
        
        if universe == "sp500":
            return self._get_sp500_tickers()
        elif universe == "nasdaq100":
            return self._get_nasdaq100_tickers()
        elif universe.startswith("custom:"):
            return self._load_custom_tickers(universe)
        else:
            logger.warning(f"Unknown universe: {universe}, using S&P 500")
            return self._get_sp500_tickers()
    
    def _download_fundamentals(self, tickers: list) -> pd.DataFrame:
        logger.info(f"Downloading fundamentals for {len(tickers)} tickers...")
        
        chunks = [tickers[i:i + 50] for i in range(0, len(tickers), 50)]
        all_data = []
        
        for i, chunk in enumerate(chunks):
            logger.info(f"Processing chunk {i+1}/{len(chunks)}")
            try:
                tickers_str = " ".join(chunk)
                data = yf.Tickers(tickers_str)
                
                for ticker in chunk:
                    try:
                        info = data.tickers[ticker].info
                        
                        market_cap = info.get("marketCap", 0) or 0
                        pe_ratio = info.get("trailingPE")
                        volume = info.get("averageVolume", 0) or 0
                        sector = info.get("sector", "Unknown")
                        industry = info.get("industry", "Unknown")
                        
                        try:
                            roe = info.get("returnOnEquity", 0) or 0
                        except:
                            roe = 0
                        
                        try:
                            debt_equity = info.get("debtToEquity", 0) or 0
                        except:
                            debt_equity = float("inf")
                        
                        try:
                            revenue_growth = info.get("revenueGrowth", 0) or 0
                        except:
                            revenue_growth = 0
                        
                        self._sector_cache.set(ticker, sector)
                        
                        all_data.append({
                            "ticker": ticker,
                            "market_cap": market_cap,
                            "pe_ratio": pe_ratio,
                            "volume": volume,
                            "sector": sector,
                            "industry": industry,
                            "roe": roe,
                            "debt_equity": debt_equity,
                            "revenue_growth": revenue_growth,
                        })
                        
                    except Exception as e:
                        logger.debug(f"Failed to get info for {ticker}: {e}")
                    
                    time.sleep(0.1)
                    
            except Exception as e:
                logger.error(f"Failed to process chunk: {e}")
            
            time.sleep(1)
        
        return pd.DataFrame(all_data)
    
    def _apply_filters(self, df: pd.DataFrame) -> pd.DataFrame:
        config = self.screening_config
        
        min_market_cap = config.get("min_market_cap", 1_000_000_000)
        max_pe = config.get("max_pe", 25)
        min_volume = config.get("min_volume", 1_000_000)
        min_revenue_growth = config.get("min_revenue_growth", 0.10)
        max_debt_equity = config.get("max_debt_equity", 1.5)
        min_roe = config.get("min_roe", 0.10)
        exclude_sectors = config.get("exclude_sectors", [])
        max_per_industry = config.get("max_per_industry", 5)
        
        filtered = df[
            (df["market_cap"] >= min_market_cap) &
            (df["volume"] >= min_volume) &
            (df["revenue_growth"] >= min_revenue_growth) &
            (df["roe"] >= min_roe) &
            (df["debt_equity"] <= max_debt_equity)
        ].copy()
        
        if max_pe:
            filtered = filtered[
                (filtered["pe_ratio"].isna()) | (filtered["pe_ratio"] <= max_pe)
            ]
        
        if exclude_sectors:
            filtered = filtered[~filtered["sector"].isin(exclude_sectors)]
        
        filtered = filtered.sort_values("market_cap", ascending=False)
        
        industry_counts = filtered.groupby("industry").cumcount()
        filtered = filtered[industry_counts < max_per_industry]
        
        return filtered
    
    def _rank_candidates(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        
        df["value_score"] = (df["pe_ratio"].max() - df["pe_ratio"]) / (df["pe_ratio"].max() - df["pe_ratio"].min() + 0.001)
        df["quality_score"] = (df["roe"] - df["roe"].min()) / (df["roe"].max() - df["roe"].min() + 0.001)
        df["growth_score"] = (df["revenue_growth"] - df["revenue_growth"].min()) / (df["revenue_growth"].max() - df["revenue_growth"].min() + 0.001)
        df["safety_score"] = 1 - (df["debt_equity"] - df["debt_equity"].min()) / (df["debt_equity"].max() - df["debt_equity"].min() + 0.001)
        
        df["composite_score"] = (
            0.25 * df["value_score"] +
            0.25 * df["quality_score"] +
            0.25 * df["growth_score"] +
            0.25 * df["safety_score"]
        )
        
        return df.sort_values("composite_score", ascending=False)
    
    def screen(self) -> list:
        logger.info("Starting stock screening...")
        
        tickers = self._get_universe_tickers()
        logger.info(f"Loaded {len(tickers)} tickers from universe")
        
        if not tickers:
            logger.error("No tickers loaded from universe")
            return []
        
        fundamentals = self._download_fundamentals(tickers)
        
        if fundamentals.empty:
            logger.error("No fundamental data retrieved")
            return []
        
        logger.info(f"Retrieved fundamentals for {len(fundamentals)} tickers")
        
        filtered = self._apply_filters(fundamentals)
        logger.info(f"After filtering: {len(filtered)} tickers remain")
        
        ranked = self._rank_candidates(filtered)
        
        max_tickers = self.config.get("analysis", {}).get("max_tickers_per_run", 10)
        top_tickers = ranked.head(max_tickers)["ticker"].tolist()
        
        self._save_screened_results(ranked)
        
        logger.info(f"Screened results: {len(top_tickers)} tickers selected")
        return top_tickers
    
    def _save_screened_results(self, df: pd.DataFrame) -> None:
        from .logger import get_data_dir
        
        screened_dir = get_data_dir() / "screened"
        screened_dir.mkdir(parents=True, exist_ok=True)
        
        date_str = datetime.now().strftime("%Y-%m-%d")
        output_path = screened_dir / f"screened_{date_str}.json"
        
        df.to_json(output_path, orient="records", indent=2)
        logger.info(f"Saved screened results to {output_path}")
