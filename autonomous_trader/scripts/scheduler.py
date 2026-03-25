#!/usr/bin/env python3
"""
Master Scheduler: Runs continuously, triggers research/execution at appropriate times.
This is what you run as a daemon/cron @reboot.
"""

import sys
import os
import signal
import time
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
os.chdir(project_root)

from src.logger import setup_logging, load_config
from src.scheduler import start_scheduler, MarketScheduler

scheduler = None


def signal_handler(signum, frame):
    global scheduler
    logger = setup_logging(load_config())
    logger.info("Shutdown signal received, stopping scheduler...")
    if scheduler:
        scheduler.stop()
    sys.exit(0)


def main():
    global scheduler
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    config = load_config()
    logger = setup_logging(config)
    
    logger.info("=" * 60)
    logger.info("MASTER SCHEDULER STARTING")
    logger.info("=" * 60)
    
    try:
        scheduler = start_scheduler(config)
        
        while scheduler.running:
            time.sleep(1)
            
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
        if scheduler:
            scheduler.stop()
    except Exception as e:
        logger.exception(f"Scheduler crashed: {e}")
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
