import csv
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

import requests


logger = logging.getLogger("autonomous_trader")


class PortfolioMonitor:
    def __init__(self, config: dict):
        self.config = config
        self.alerts_config = config.get("alerts", {})
        self.logging_config = config.get("logging", {})
        self._trade_log_path = self._get_trade_log_path()
        self._performance_path = self._get_performance_path()
        self._init_csv_files()
    
    def _get_trade_log_path(self) -> Path:
        log_file = self.logging_config.get("trade_log", "data/trade_log.csv")
        return Path(__file__).parent.parent / log_file
    
    def _get_performance_path(self) -> Path:
        perf_file = self.logging_config.get("performance_log", "data/performance.csv")
        return Path(__file__).parent.parent / perf_file
    
    def _init_csv_files(self) -> None:
        self._trade_log_path.parent.mkdir(parents=True, exist_ok=True)
        
        if not self._trade_log_path.exists():
            with open(self._trade_log_path, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "timestamp", "ticker", "action", "quantity", "price",
                    "total_value", "pnl", "pnl_pct", "sector", "order_id", "status"
                ])
        
        if not self._performance_path.exists():
            with open(self._performance_path, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "date", "equity", "daily_pnl", "daily_pnl_pct",
                    "total_trades", "winning_trades", "losing_trades",
                    "win_rate", "profit_factor", "max_drawdown"
                ])
    
    def log_trade(self, trade: dict) -> None:
        with open(self._trade_log_path, "a", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                trade.get("timestamp", datetime.now().isoformat()),
                trade.get("ticker", ""),
                trade.get("action", ""),
                trade.get("quantity", 0),
                trade.get("price", 0.0),
                trade.get("total_value", 0.0),
                trade.get("pnl", 0.0),
                trade.get("pnl_pct", 0.0),
                trade.get("sector", "Unknown"),
                trade.get("order_id", ""),
                trade.get("status", "unknown"),
            ])
        
        logger.info(f"Logged trade: {trade.get('action')} {trade.get('quantity')} {trade.get('ticker')} @ ${trade.get('price', 0):.2f}")
    
    def log_execution_report(self, report: dict) -> None:
        for executed in report.get("executed", []):
            order = executed.get("order", {})
            signal = executed.get("signal", {})
            self.log_trade({
                "timestamp": report.get("timestamp", datetime.now().isoformat()),
                "ticker": order.get("symbol", ""),
                "action": "BUY",
                "quantity": executed.get("quantity", 0),
                "price": executed.get("price", 0.0),
                "total_value": executed.get("quantity", 0) * executed.get("price", 0.0),
                "pnl": 0.0,
                "pnl_pct": 0.0,
                "sector": executed.get("sector", "Unknown"),
                "order_id": order.get("id", ""),
                "status": order.get("status", "executed"),
                "confidence": signal.get("confidence", 0),
                "target_price": signal.get("target_price", 0),
                "stop_loss": signal.get("stop_loss", 0),
            })
        
        self.send_alert(f"Execution complete: {len(report.get('executed', []))} trades executed, "
                       f"{len(report.get('skipped', []))} skipped, {len(report.get('failed', []))} failed",
                       level="INFO")
    
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
            ])
        
        logger.info(f"Daily metrics logged: P&L ${metrics.get('daily_pnl', 0):.2f}, "
                   f"Win rate: {metrics.get('win_rate', 0)*100:.1f}%")
    
    def send_alert(self, message: str, level: str = "INFO") -> None:
        if not self.alerts_config.get("enabled", False):
            return
        
        notify_on = self.alerts_config.get("notify_on", [])
        
        event_type = "info"
        if "error" in message.lower():
            event_type = "error"
        elif "stop_loss" in message.lower():
            event_type = "stop_loss"
        elif "trade_executed" in message.lower() or "executed" in message.lower():
            event_type = "trade_executed"
        elif "position_closed" in message.lower() or "closed" in message.lower():
            event_type = "position_closed"
        
        if event_type not in notify_on:
            return
        
        webhook_url = self.alerts_config.get("discord_webhook")
        if not webhook_url:
            logger.debug("Discord webhook not configured")
            return
        
        try:
            embed = {
                "title": f"Trading Agent - {level}",
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
        }
        return colors.get(level.upper(), 3447003)
    
    def check_exit_signals(self, positions: list, prices: dict) -> list:
        exit_signals = []
        
        for position in positions:
            ticker = position.get("symbol", "")
            current_price = prices.get(ticker)
            entry_price = position.get("avg_entry_price", 0)
            
            if not current_price or not entry_price:
                continue
            
            pnl_pct = (current_price - entry_price) / entry_price
            stop_loss_pct = self.config.get("trading", {}).get("stop_loss_pct", 0.10)
            take_profit_pct = self.config.get("trading", {}).get("take_profit_pct", 0.20)
            
            if pnl_pct <= -stop_loss_pct:
                exit_signals.append({
                    "ticker": ticker,
                    "reason": "stop_loss",
                    "pnl_pct": pnl_pct,
                    "current_price": current_price,
                })
            elif pnl_pct >= take_profit_pct:
                exit_signals.append({
                    "ticker": ticker,
                    "reason": "take_profit",
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
        
        return {
            "total_trades": len(trades),
            "completed_trades": len([t for t in trades if t.get("status") == "filled"]),
            "total_pnl": sum(float(t.get("pnl", 0)) for t in trades),
        }
