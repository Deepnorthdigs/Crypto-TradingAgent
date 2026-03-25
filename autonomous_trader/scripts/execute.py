#!/usr/bin/env python3
"""
Execution Phase Only: Process signals from queue, execute trades.
Should run only during market hours (or check internally).
"""

import sys
import os
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
os.chdir(project_root)

from src.logger import setup_logging, load_config
from src.scheduler import MarketScheduler
from src.queue import TradeQueue
from src.executor import TradingExecutor


def main():
    config = load_config()
    logger = setup_logging(config)
    
    scheduler = MarketScheduler(config)
    
    if config.get('execution', {}).get('run_during_market_hours_only', True):
        if not scheduler.is_market_open():
            logger.info("Market closed. Exiting.")
            return 0
    
    logger.info("=" * 60)
    logger.info("EXECUTION PHASE STARTING")
    logger.info("=" * 60)
    
    try:
        scheduler.run_execution_job()
        logger.info("Execution cycle complete")
        
    except Exception as e:
        logger.exception(f"Execution failed: {e}")
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
