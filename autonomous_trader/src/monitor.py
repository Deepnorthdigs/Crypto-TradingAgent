"""
Crypto Portfolio Monitor - Holding Period Tracking and Alerts
Adapted for swing/position trading with longer holding periods.
"""

import csv
import json
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict

import requests


logger = logging.getLogger("autonomous_trader")


class PortfolioMonitor:
    def __init__(self, config: dict):
        self.config = config
        self.alerts_config = config.get("alerts", {})
        self.logging_config = config.get("logging", {})
        self.trading_config = config.get("trading", {})
        self.risk_config = config.get("risk", {})
        self._trade_log_path = self._get_trade_log_path()
        self._performance_path = self._get_performance_path()
        self._positions_path = self._get_positions_path()
        self._init_csv_files()
    
    def _get_trade_log_path(self) -> Path:
        log_file = self.logging_config.get("trade_log", "data/trade_log.csv")
        return Path(__file__).parent.parent / log_file
    
    def _get_performance_path(self) -> Path:
        perf_file = self.logging_config.get("performance_log", "data/performance.csv")
        return Path(__file__).parent.parent / perf_file
    
    def _get_positions_path(self) -> Path:
        return Path(__file__).parent.parent / "data" / "positions.json"
    
    def _init_csv_files(self) -> None:
        self._trade_log_path.parent.mkdir(parents=True, exist_ok=True)
        
        if not self._trade_log_path.exists():
            with open(self._trade_log_path, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "timestamp", "symbol", "action", "quantity", "price",
                    "total_value", "pnl", "pnl_pct", "category", "order_id", 
                    "status", "holding_period_days"
                ])
        
        if not self._performance_path.exists():
            with open(self._performance_path, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "date", "equity", "daily_pnl", "daily_pnl_pct",
                    "total_trades", "winning_trades", "losing_trades",
                    "win_rate", "profit_factor", "max_drawdown",
                    "avg_holding_period"
                ])
    
    def _load_positions(self) -> List[Dict]:
        if self._positions_path.exists():
            try:
                with open(self._positions_path, "r") as f:
                    data = json.load(f)
                    return data.get("positions", [])
            except (json.JSONDecodeError, KeyError):
                return []
        return []
    
    def _save_positions(self, positions: List[Dict]) -> None:
        with open(self._positions_path, "w") as f:
            json.dump({
                "positions": positions,
                "last_updated": datetime.now().isoformat()
            }, f, indent=2)
    
    def log_trade(self, trade: dict) -> None:
        positions = self._load_positions()
        entry_time = None
        
        for pos in positions:
            if pos.get("symbol") == trade.get("symbol"):
                entry_time = pos.get("entry_time")
                break
        
        holding_days = 0
        if entry_time:
            try:
                entry_date = datetime.fromisoformat(entry_time)
                holding_days = (datetime.now() - entry_date).days
            except (ValueError, TypeError):
                pass
        
        with open(self._trade_log_path, "a", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                trade.get("timestamp", datetime.now().isoformat()),
                trade.get("symbol", ""),
                trade.get("action", ""),
                trade.get("quantity", 0),
                trade.get("price", 0.0),
                trade.get("total_value", 0.0),
                trade.get("pnl", 0.0),
                trade.get("pnl_pct", 0.0),
                trade.get("category", "Unknown"),
                trade.get("order_id", ""),
                trade.get("status", "unknown"),
                holding_days,
            ])
        
        logger.info(f"Logged trade: {trade.get('action')} {trade.get('quantity')} {trade.get('symbol')} @ ${trade.get('price', 0):.4f}")
    
    def log_execution_report(self, report: dict) -> None:
        for executed in report.get("executed", []):
            order = executed.get("order", {})
            signal = executed.get("signal", {})
            self.log_trade({
                "timestamp": report.get("timestamp", datetime.now().isoformat()),
                "symbol": order.get("symbol", ""),
                "action": "BUY",
                "quantity": executed.get("quantity", 0),
                "price": executed.get("price", 0.0),
                "total_value": executed.get("quantity", 0) * executed.get("price", 0.0),
                "pnl": 0.0,
                "pnl_pct": 0.0,
                "category": executed.get("category", "Unknown"),
                "order_id": order.get("id", ""),
                "status": order.get("status", "executed"),
            })
        
        self.send_alert(
            f"Execution complete: {len(report.get('executed', []))} trades executed, "
            f"{len(report.get('skipped', []))} skipped, {len(report.get('failed', []))} failed",
            level="INFO"
        )
    
    def check_holding_period_alerts(self) -> List[Dict]:
        """Check for positions approaching or exceeding holding period limits."""
        positions = self._load_positions()
        alert_days = self.risk_config.get("holding_alert_days", 45)
        max_days = self.risk_config.get("max_holding_days", 60)
        
        alerts = []
        for pos in positions:
            entry_time = pos.get("entry_time")
            if not entry_time:
                continue
            
            try:
                entry_date = datetime.fromisoformat(entry_time)
                days_held = (datetime.now() - entry_date).days
                
                if days_held >= max_days:
                    alerts.append({
                        "type": "holding_limit",
                        "symbol": pos.get("symbol"),
                        "days_held": days_held,
                        "message": f"Position {pos.get('symbol')} has been held {days_held} days - EXCEEDS maximum {max_days} days",
                    })
                elif days_held >= alert_days:
                    alerts.append({
                        "type": "holding_alert",
                        "symbol": pos.get("symbol"),
                        "days_held": days_held,
                        "message": f"Position {pos.get('symbol')} has been held {days_held} days - approaching {max_days} day limit",
                    })
            except (ValueError, TypeError):
                continue
        
        return alerts
    
    def check_take_profit_alerts(self, positions: List[Dict], prices: Dict[str, float]) -> List[Dict]:
        """Alert when positions hit take profit levels."""
        tp1_pct = self.trading_config.get("take_profit_pct_1", 0.25)
        
        alerts = []
        for pos in positions:
            symbol = pos.get("symbol", "")
            entry_price = pos.get("avg_entry_price", 0)
            current_price = prices.get(symbol, 0)
            
            if not entry_price or not current_price:
                continue
            
            pnl_pct = (current_price - entry_price) / entry_price
            
            if pnl_pct >= tp1_pct:
                alerts.append({
                    "type": "take_profit_1",
                    "symbol": symbol,
                    "pnl_pct": pnl_pct * 100,
                    "message": f"Position {symbol} hit TP1 ({pnl_pct*100:.1f}% gain) - partial exit triggered",
                })
        
        return alerts
    
    def calculate_daily_metrics(self, equity: float, closed_positions: list = None) -> dict:
        if closed_positions is None:
            closed_positions = []
        
        winning_trades = sum(1 for p in closed_positions if p.get("pnl", 0) > 0)
        losing_trades = sum(1 for p in closed_positions if p.get("pnl", 0) < 0)
        total_trades = winning_trades + losing_trades
        
        win_rate = winning_trades / total_trades if total_trades > 0 else 0.0
        
        total_wins = sum(p.get("pnl", 0) for p in closed_positions if p.get("pnl", 0) > 0)
        total_losses = abs(sum(p.get("pnl", 0) for p in closed_positions if p.get("pnl", 0) < 0))
        profit_factor = total_wins / total_losses if total_losses > 0 else 0.0
        
        daily_pnl = sum(p.get("pnl", 0) for p in closed_positions)
        daily_pnl_pct = daily_pnl / equity if equity > 0 else 0.0
        
        avg_holding = 0
        if closed_positions:
            holdings = [p.get("holding_days", 0) for p in closed_positions]
            avg_holding = sum(holdings) / len(holdings) if holdings else 0
        
        return {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "equity": equity,
            "daily_pnl": daily_pnl,
            "daily_pnl_pct": daily_pnl_pct,
            "total_trades": total_trades,
            "winning_trades": winning_trades,
            "losing_trades": losing_trades,
            "win_rate": win_rate,
            "profit_factor": profit_factor,
            "avg_holding_period": avg_holding,
        }
    
    def log_daily_metrics(self, metrics: dict) -> None:
        with open(self._performance_path, "a", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                metrics.get("date", ""),
                metrics.get("equity", 0),
                metrics.get("daily_pnl", 0),
                metrics.get("daily_pnl_pct", 0),
                metrics.get("total_trades", 0),
                metrics.get("winning_trades", 0),
                metrics.get("losing_trades", 0),
                metrics.get("win_rate", 0),
                metrics.get("profit_factor", 0),
                metrics.get("max_drawdown", 0),
                metrics.get("avg_holding_period", 0),
            ])
        
        logger.info(f"Daily metrics logged: P&L ${metrics.get('daily_pnl', 0):.2f}, "
                   f"Win rate: {metrics.get('win_rate', 0)*100:.1f}%, "
                   f"Avg holding: {metrics.get('avg_holding_period', 0):.1f} days")
    
    def send_alert(self, message: str, level: str = "INFO", alert_type: str = None) -> None:
        if not self.alerts_config.get("enabled", False):
            return
        
        notify_on = self.alerts_config.get("notify_on", [])
        
        if alert_type is None:
            event_type = "info"
            if "error" in message.lower():
                event_type = "error"
            elif "stop_loss" in message.lower():
                event_type = "stop_loss"
            elif "take_profit" in message.lower() or "tp1" in message.lower():
                event_type = "take_profit_1"
            elif "holding" in message.lower() or "days" in message.lower():
                event_type = "holding_alert"
            elif "trade_executed" in message.lower() or "executed" in message.lower():
                event_type = "trade_executed"
            elif "position_closed" in message.lower() or "closed" in message.lower():
                event_type = "position_closed"
        else:
            event_type = alert_type
        
        if event_type not in notify_on:
            return
        
        webhook_url = self.alerts_config.get("discord_webhook")
        if not webhook_url:
            logger.debug("Discord webhook not configured")
            return
        
        try:
            embed = {
                "title": f"Crypto Trading - {level}",
                "description": message,
                "color": self._get_embed_color(level),
                "timestamp": datetime.now().isoformat(),
            }
            
            payload = {"embeds": [embed]}
            response = requests.post(webhook_url, json=payload, timeout=10)
            
            if response.status_code == 204:
                logger.debug(f"Alert sent to Discord: {message}")
            else:
                logger.warning(f"Failed to send Discord alert: {response.status_code}")
                
        except Exception as e:
            logger.error(f"Failed to send alert: {e}")
    
    def _get_embed_color(self, level: str) -> int:
        colors = {
            "INFO": 3447003,
            "WARNING": 16776960,
            "ERROR": 15158332,
            "SUCCESS": 3066993,
            "HOLDING_ALERT": 16744448,
            "TAKE_PROFIT_1": 3066993,
        }
        return colors.get(level.upper(), 3447003)
    
    def check_exit_signals(self, positions: list, prices: dict) -> list:
        exit_signals = []
        stop_loss_pct = self.trading_config.get("stop_loss_pct", 0.08)
        tp1_pct = self.trading_config.get("take_profit_pct_1", 0.25)
        tp2_pct = self.trading_config.get("take_profit_pct_2", 0.50)
        
        for position in positions:
            symbol = position.get("symbol", "")
            current_price = prices.get(symbol)
            entry_price = position.get("avg_entry_price", 0)
            
            if not current_price or not entry_price:
                continue
            
            pnl_pct = (current_price - entry_price) / entry_price
            
            if pnl_pct <= -stop_loss_pct:
                exit_signals.append({
                    "symbol": symbol,
                    "reason": "stop_loss",
                    "pnl_pct": pnl_pct,
                    "current_price": current_price,
                })
            elif pnl_pct >= tp2_pct:
                exit_signals.append({
                    "symbol": symbol,
                    "reason": "take_profit_full",
                    "pnl_pct": pnl_pct,
                    "current_price": current_price,
                })
        
        return exit_signals
    
    def get_trade_summary(self) -> dict:
        trades = []
        
        if self._trade_log_path.exists():
            with open(self._trade_log_path, "r") as f:
                reader = csv.DictReader(f)
                trades = list(reader)
        
        avg_holding = 0
        if trades:
            holdings = [int(float(t.get("holding_period_days", 0))) for t in trades if t.get("holding_period_days")]
            avg_holding = sum(holdings) / len(holdings) if holdings else 0
        
        return {
            "total_trades": len(trades),
            "completed_trades": len([t for t in trades if t.get("status") == "filled"]),
            "total_pnl": sum(float(t.get("pnl", 0)) for t in trades),
            "avg_holding_period_days": avg_holding,
        }
