"""
Crypto Risk Manager - Category-Based Concentration Limits
Replaces sector concentration with crypto-specific category limits.
"""

import json
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Optional, Dict, List, Tuple
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
    
    def check_daily_loss(self, current_equity: float) -> Tuple[bool, str]:
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
    
    def check_max_drawdown(self, current_equity: float) -> Tuple[bool, str]:
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
    
    def check_position_limits(self) -> Tuple[bool, str]:
        max_positions = self.trading_config.get("max_positions", 6)
        current_count = self.position_tracker.get_position_count()
        if current_count >= max_positions:
            return True, f"Position count {current_count} at max limit {max_positions}"
        return False, ""
    
    def check_category_concentration(self, category: str) -> Tuple[bool, str]:
        """
        Check crypto category concentration limits.
        
        Limits:
        - Max 30% DeFi
        - Max 30% L1s
        - Max 30% L2s
        - Max 20% memecoins (configurable)
        """
        exposure = self.position_tracker.get_category_exposure()
        max_limits = {
            "DeFi": self.risk_config.get("max_defi_exposure_pct", 0.30),
            "L1": self.risk_config.get("max_l1_exposure_pct", 0.30),
            "L2": self.risk_config.get("max_l2_exposure_pct", 0.30),
            "memecoin": self.risk_config.get("max_memecoin_exposure_pct", 0.20),
        }
        
        current_pct = exposure.get(category, 0.0)
        max_pct = max_limits.get(category, 0.30)
        
        if current_pct >= max_pct:
            return True, f"Category {category} exposure {current_pct*100:.1f}% at limit ({max_pct*100:.0f}% max)"
        return False, ""
    
    def check_holding_period(self, symbol: str) -> Tuple[bool, str]:
        """Check if position has exceeded maximum holding period."""
        max_holding_days = self.risk_config.get("max_holding_days", 60)
        
        position = self.position_tracker.get_position(symbol)
        if not position:
            return False, ""
        
        entry_time = position.get("entry_time")
        if not entry_time:
            return False, ""
        
        try:
            entry_date = datetime.fromisoformat(entry_time)
            days_held = (datetime.now() - entry_date).days
            
            if days_held >= max_holding_days:
                return True, f"Position {symbol} held {days_held} days exceeds max {max_holding_days} days"
            
            return False, ""
        except (ValueError, TypeError):
            return False, ""
    
    def get_positions_near_holding_limit(self) -> List[Dict]:
        """Get positions approaching holding period limit for alerts."""
        alert_days = self.risk_config.get("holding_alert_days", 45)
        max_days = self.risk_config.get("max_holding_days", 60)
        
        positions = self.position_tracker.get_positions()
        alert_positions = []
        
        for pos in positions:
            entry_time = pos.get("entry_time")
            if not entry_time:
                continue
            
            try:
                entry_date = datetime.fromisoformat(entry_time)
                days_held = (datetime.now() - entry_date).days
                
                if alert_days <= days_held < max_days:
                    alert_positions.append({
                        "symbol": pos.get("symbol"),
                        "days_held": days_held,
                        "alert_threshold": alert_days,
                        "max_threshold": max_days,
                    })
            except (ValueError, TypeError):
                continue
        
        return alert_positions
    
    def can_trade(self, current_equity: float, category: Optional[str] = None) -> Tuple[bool, str]:
        checks = [
            self.check_daily_loss(current_equity),
            self.check_max_drawdown(current_equity),
            self.check_position_limits(),
        ]
        
        if category:
            checks.append(self.check_category_concentration(category))
        
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
