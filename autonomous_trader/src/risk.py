import json
from datetime import datetime, date
from pathlib import Path
from typing import Optional
from .portfolio import PositionTracker


class RiskManager:
    def __init__(self, config: dict, position_tracker: PositionTracker):
        self.config = config
        self.position_tracker = position_tracker
        self.risk_config = config.get("risk", {})
        self.trading_config = config.get("trading", {})
        self._peak_equity = self._load_peak_equity()
        self._daily_pnl_path = self._get_daily_pnl_path()
    
    def _get_daily_pnl_path(self) -> Path:
        from .logger import get_data_dir
        return get_data_dir() / "daily_pnl.json"
    
    def _load_peak_equity(self) -> float:
        from .logger import get_data_dir
        peak_path = get_data_dir() / "peak_equity.json"
        if peak_path.exists():
            with open(peak_path, "r") as f:
                data = json.load(f)
                return data.get("peak_equity", 0.0)
        return 0.0
    
    def _save_peak_equity(self, peak: float) -> None:
        from .logger import get_data_dir
        peak_path = get_data_dir() / "peak_equity.json"
        with open(peak_path, "w") as f:
            json.dump({"peak_equity": peak, "date": datetime.now().isoformat()}, f, indent=2)
    
    def check_daily_loss(self, current_equity: float) -> tuple[bool, str]:
        if self._daily_pnl_path.exists():
            with open(self._daily_pnl_path, "r") as f:
                data = json.load(f)
                today = date.today().isoformat()
                if data.get("date") == today:
                    daily_pnl_pct = data.get("daily_pnl_pct", 0.0)
                    max_daily_loss = self.risk_config.get("max_daily_loss_pct", 0.02)
                    if daily_pnl_pct < -max_daily_loss:
                        return True, f"Daily loss {abs(daily_pnl_pct)*100:.2f}% exceeds limit {max_daily_loss*100:.2f}%"
        return False, ""
    
    def check_max_drawdown(self, current_equity: float) -> tuple[bool, str]:
        if self._peak_equity > 0:
            drawdown = (self._peak_equity - current_equity) / self._peak_equity
            max_drawdown = self.risk_config.get("max_drawdown_pct", 0.10)
            if drawdown > max_drawdown:
                return True, f"Drawdown {drawdown*100:.2f}% exceeds limit {max_drawdown*100:.2f}%"
            
            if current_equity > self._peak_equity:
                self._peak_equity = current_equity
                self._save_peak_equity(current_equity)
        elif current_equity > 0:
            self._peak_equity = current_equity
            self._save_peak_equity(current_equity)
        
        return False, ""
    
    def check_position_limits(self) -> tuple[bool, str]:
        max_positions = self.trading_config.get("max_positions", 20)
        current_count = self.position_tracker.get_position_count()
        if current_count >= max_positions:
            return True, f"Position count {current_count} at max limit {max_positions}"
        return False, ""
    
    def check_sector_concentration(self, sector: str) -> tuple[bool, str]:
        max_sector_pct = self.trading_config.get("max_sector_exposure_pct", 0.20)
        exposure = self.position_tracker.get_sector_exposure()
        current_sector_pct = exposure.get(sector, 0.0)
        if current_sector_pct >= max_sector_pct:
            return True, f"Sector {sector} exposure {current_sector_pct*100:.1f}% at limit"
        return False, ""
    
    def can_trade(self, current_equity: float, sector: Optional[str] = None) -> tuple[bool, str]:
        checks = [
            self.check_daily_loss(current_equity),
            self.check_max_drawdown(current_equity),
            self.check_position_limits(),
        ]
        
        if sector:
            checks.append(self.check_sector_concentration(sector))
        
        for blocked, reason in checks:
            if blocked:
                return False, reason
        
        return True, "All checks passed"
    
    def update_daily_pnl(self, pnl: float, equity: float) -> None:
        today = date.today().isoformat()
        if self._peak_equity > 0:
            daily_pnl_pct = pnl / self._peak_equity
        else:
            daily_pnl_pct = 0.0
        
        with open(self._daily_pnl_path, "w") as f:
            json.dump({
                "date": today,
                "pnl": pnl,
                "equity": equity,
                "daily_pnl_pct": daily_pnl_pct
            }, f, indent=2)
