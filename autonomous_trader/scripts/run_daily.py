#!/usr/bin/env python3
import logging
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.logger import setup_logging, load_config, get_data_dir
from src.screener import StockScreener
from src.analyzer import StockAnalyzer
from src.executor import TradingExecutor
from src.risk import RiskManager
from src.portfolio import PositionTracker, TickerSectorCache
from src.monitor import PortfolioMonitor


def is_market_open(config: dict) -> bool:
    schedule_config = config.get("schedule", {})
    
    if not schedule_config.get("market_hours_only", True):
        return True
    
    try:
        import pytz
        from datetime import time
        
        eastern = pytz.timezone(schedule_config.get("timezone", "America/New_York"))
        now = datetime.now(eastern)
        
        market_open = time(9, 30)
        market_close = time(16, 0)
        current_time = now.time()
        
        is_weekday = now.weekday() < 5
        
        return is_weekday and market_open <= current_time <= market_close
        
    except Exception as e:
        logger = logging.getLogger("autonomous_trader")
        logger.warning(f"Could not verify market hours: {e}")
        return True


def run_daily_trading_cycle():
    logger = logging.getLogger("autonomous_trader")
    
    try:
        config = load_config()
        logger.info("=" * 60)
        logger.info(f"Starting daily trading cycle: {datetime.now().isoformat()}")
        logger.info("=" * 60)
        
        if not is_market_open(config):
            logger.info("Market is closed or outside trading hours, exiting")
            return 0
        
        position_tracker = PositionTracker()
        sector_cache = TickerSectorCache()
        risk_manager = RiskManager(config, position_tracker)
        monitor = PortfolioMonitor(config)
        
        account_info = {
            "equity": 100000.0,
        }
        
        can_trade, reason = risk_manager.can_trade(account_info["equity"])
        if not can_trade:
            logger.warning(f"Risk check failed: {reason}")
            monitor.send_alert(f"Trading halted: {reason}", level="WARNING")
            return 1
        
        logger.info("Step 1: Screening stocks...")
        screener = StockScreener(config)
        tickers = screener.screen()
        
        if not tickers:
            logger.warning("No tickers passed screening")
            monitor.send_alert("Screening complete: No qualifying tickers found", level="INFO")
            return 0
        
        logger.info(f"Screened {len(tickers)} candidates: {tickers}")
        
        logger.info("Step 2: Analyzing candidates...")
        analyzer = StockAnalyzer(config)
        signals = analyzer.analyze_batch(tickers)
        
        if not signals:
            logger.warning("No trading signals generated")
            monitor.send_alert("Analysis complete: No trading signals generated", level="INFO")
            return 0
        
        buy_signals = [s for s in signals if s.get("recommendation", "").upper() == "BUY"]
        logger.info(f"Generated {len(buy_signals)} BUY signals out of {len(signals)} total")
        
        logger.info("Step 3: Executing trades...")
        executor = TradingExecutor(config)
        
        sector_mapping = sector_cache.get_batch(tickers)
        
        execution_report = executor.execute_signals(buy_signals, sector_mapping)
        
        logger.info(f"Execution report: {len(execution_report.get('executed', []))} executed, "
                   f"{len(execution_report.get('skipped', []))} skipped, "
                   f"{len(execution_report.get('failed', []))} failed")
        
        monitor.log_execution_report(execution_report)
        
        for executed in execution_report.get("executed", []):
            order = executed.get("order", {})
            position_tracker.add_position({
                "symbol": order.get("symbol"),
                "qty": executed.get("quantity"),
                "avg_entry_price": executed.get("price"),
                "market_value": executed.get("quantity", 0) * executed.get("price", 0),
                "sector": executed.get("sector", "Unknown"),
                "entry_date": datetime.now().isoformat(),
                "target_price": executed.get("signal", {}).get("target_price"),
                "stop_loss": executed.get("signal", {}).get("stop_loss"),
            })
        
        metrics = monitor.calculate_daily_metrics(
            account_info["equity"],
            closed_positions=[]
        )
        monitor.log_daily_metrics(metrics)
        
        summary = monitor.get_trade_summary()
        monitor.send_alert(
            f"Daily cycle complete: {summary['total_trades']} total trades, "
            f"${summary['total_pnl']:.2f} total P&L",
            level="INFO"
        )
        
        logger.info("=" * 60)
        logger.info(f"Daily trading cycle complete: {datetime.now().isoformat()}")
        logger.info("=" * 60)
        
        return 0
        
    except Exception as e:
        logger = logging.getLogger("autonomous_trader")
        logger.exception(f"Error in daily trading cycle: {e}")
        
        try:
            config = load_config()
            monitor = PortfolioMonitor(config)
            monitor.send_alert(f"Trading cycle failed with error: {str(e)}", level="ERROR")
        except:
            pass
        
        return 1


if __name__ == "__main__":
    config = load_config()
    logger = setup_logging(config)
    
    exit_code = run_daily_trading_cycle()
    sys.exit(exit_code)
