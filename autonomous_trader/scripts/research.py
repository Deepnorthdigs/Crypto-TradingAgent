#!/usr/bin/env python3
"""
Research Phase Only: Screen and analyze stocks, queue signals.
Can run 24/7, even when market closed.
"""

import sys
import os
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
os.chdir(project_root)

from src.logger import setup_logging, load_config
from src.researcher import ResearchAgent


def main():
    config = load_config()
    logger = setup_logging(config)
    
    logger.info("=" * 60)
    logger.info("RESEARCH PHASE STARTING")
    logger.info("=" * 60)
    
    try:
        agent = ResearchAgent(config)
        signals = agent.run_research()
        
        if signals:
            logger.info(f"Research complete: {len(signals)} signals queued")
            for sig in signals:
                logger.info(f"  - {sig.ticker}: {sig.confidence:.1%} confidence, ${sig.target_price:.2f} target")
        else:
            logger.info("Research complete: no signals to queue")
            
    except Exception as e:
        logger.exception(f"Research failed: {e}")
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
