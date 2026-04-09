import json
from pathlib import Path
from typing import Optional


class TickerSectorCache:
    def __init__(self, cache_path: Optional[Path] = None):
        if cache_path is None:
            from .logger import get_data_dir
            cache_path = get_data_dir() / "ticker_sectors.json"
        self.cache_path = cache_path
        self._cache: dict = self._load_cache()
    
    def _load_cache(self) -> dict:
        if self.cache_path.exists():
            with open(self.cache_path, "r") as f:
                return json.load(f)
        return {}
    
    def _save_cache(self) -> None:
        with open(self.cache_path, "w") as f:
            json.dump(self._cache, f, indent=2)
    
    def get(self, ticker: str) -> Optional[str]:
        return self._cache.get(ticker.upper())
    
    def set(self, ticker: str, sector: str) -> None:
        self._cache[ticker.upper()] = sector
        self._save_cache()
    
    def get_batch(self, tickers: list) -> dict:
        return {t: self._cache.get(t.upper()) for t in tickers}
    
    def set_batch(self, mapping: dict) -> None:
        self._cache.update({k.upper(): v for k, v in mapping.items()})
        self._save_cache()
    
    def has(self, ticker: str) -> bool:
        return ticker.upper() in self._cache


class PositionTracker:
    def __init__(self, positions_path: Optional[Path] = None):
        if positions_path is None:
            from .logger import get_data_dir
            positions_path = get_data_dir() / "positions.json"
        self.positions_path = positions_path
        self._positions: dict = self._load_positions()
    
    def _load_positions(self) -> dict:
        if self.positions_path.exists():
            with open(self.positions_path, "r") as f:
                return json.load(f)
        return {"positions": [], "cash_reserve": 0.0, "last_updated": None}
    
    def _save_positions(self) -> None:
        from datetime import datetime
        self._positions["last_updated"] = datetime.now().isoformat()
        with open(self.positions_path, "w") as f:
            json.dump(self._positions, f, indent=2)
    
    def get_positions(self) -> list:
        return self._positions.get("positions", [])
    
    def get_position(self, ticker: str) -> Optional[dict]:
        for pos in self.get_positions():
            if pos.get("symbol", "").upper() == ticker.upper():
                return pos
        return None
    
    def is_holding(self, ticker: str) -> bool:
        return self.get_position(ticker) is not None
    
    def add_position(self, position: dict) -> None:
        positions = self._positions.get("positions", [])
        ticker = position.get("symbol", "")
        for i, pos in enumerate(positions):
            if pos.get("symbol", "").upper() == ticker.upper():
                positions[i] = position
                self._save_positions()
                return
        positions.append(position)
        self._positions["positions"] = positions
        self._save_positions()
    
    def remove_position(self, ticker: str) -> None:
        positions = [p for p in self.get_positions() if p.get("symbol", "").upper() != ticker.upper()]
        self._positions["positions"] = positions
        self._save_positions()
    
    def update_position(self, ticker: str, updates: dict) -> None:
        positions = self._positions.get("positions", [])
        for i, pos in enumerate(positions):
            if pos.get("symbol", "").upper() == ticker.upper():
                positions[i].update(updates)
                break
        self._positions["positions"] = positions
        self._save_positions()
    
    def get_sector_exposure(self) -> dict:
        exposure = {}
        total_value = 0.0
        for pos in self.get_positions():
            sector = pos.get("sector", "Unknown")
            value = pos.get("market_value", 0.0)
            exposure[sector] = exposure.get(sector, 0.0) + value
            total_value += value
        
        if total_value > 0:
            exposure = {k: v / total_value for k, v in exposure.items()}
        return exposure
    
    def get_category_exposure(self) -> dict:
        """Get exposure by crypto category (DeFi, L1, L2, memecoin, etc.)."""
        exposure = {}
        total_value = 0.0
        for pos in self.get_positions():
            category = pos.get("category", "Other")
            value = pos.get("market_value", 0.0)
            exposure[category] = exposure.get(category, 0.0) + value
            total_value += value
        
        if total_value > 0:
            exposure = {k: v / total_value for k, v in exposure.items()}
        return exposure
    
    def get_total_position_value(self) -> float:
        return sum(p.get("market_value", 0.0) for p in self.get_positions())
    
    def get_position_count(self) -> int:
        return len(self.get_positions())
