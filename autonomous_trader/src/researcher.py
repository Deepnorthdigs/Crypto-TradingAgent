"""
Research Agent: Screening + Analysis (Market-Independent)
Runs anytime, generates signals and queues them.
"""

import logging
from datetime import datetime, timedelta
from typing import List, Dict
from .screener import StockScreener
from .analyzer import StockAnalyzer
from .queue import TradeQueue, TradeSignal
from .portfolio import TickerSectorCache

logger = logging.getLogger("autonomous_trader")


class ResearchAgent:
    def __init__(self, config: dict):
        self.config = config
        self.screener = StockScreener(config)
        self.analyzer = StockAnalyzer(config)
        self.queue = TradeQueue(config)
        self.sector_cache = TickerSectorCache()

    def run_research(self) -> List[TradeSignal]:
        logger.info("Starting research pipeline...")

        candidates = self.screener.screen()

        if not candidates:
            logger.warning("No candidates after screening")
            return []

        analyses = self.analyzer.analyze_batch(candidates)
        if not analyses:
            logger.warning("No analyses produced")
            return []

        signals = self._validate_and_create_signals(analyses)

        max_signals = self.config.get('research', {}).get('max_signals_per_day', 10)
        signals = signals[:max_signals]

        queued_signals = []
        for signal in signals:
            if self.queue.enqueue(signal):
                queued_signals.append(signal)

        logger.info(f"Research complete: {len(queued_signals)} signals queued")
        return queued_signals

    def _validate_and_create_signals(self, analyses: List[Dict]) -> List[TradeSignal]:
        signals = []
        now = datetime.now()
        expiry_days = self.config.get('execution', {}).get('signal_expiry_days', 2)
        queue_config = self.config.get('queue', {})

        for analysis in analyses:
            ticker = analysis.get('ticker')
            confidence = analysis.get('confidence', 0)
            action = analysis.get('recommendation', 'HOLD')

            if action.upper() != 'BUY':
                logger.debug(f"Skipping {ticker}: action={action}")
                continue

            required = ['target_price', 'stop_loss']
            missing = [k for k in required if k not in analysis or analysis[k] is None]
            if missing:
                logger.warning(f"Skipping {ticker}: missing {missing}")
                continue

            min_conf = self.config.get('trading', {}).get('min_confidence', 0.65)
            if confidence < min_conf:
                logger.debug(f"Skipping {ticker}: confidence {confidence} < {min_conf}")
                continue

            target = analysis['target_price']
            stop = analysis['stop_loss']

            if target <= 0 or stop <= 0:
                logger.warning(f"Skipping {ticker}: invalid prices target={target}, stop={stop}")
                continue

            if not (stop < target):
                logger.warning(f"Skipping {ticker}: stop must be less than target")
                continue

            position_size_pct = analysis.get('position_size_pct', 0.05)
            max_size = queue_config.get('max_position_size_pct', 0.05)
            if position_size_pct > max_size:
                logger.info(f"Reducing position size for {ticker} from {position_size_pct:.1%} to {max_size:.1%}")
                position_size_pct = max_size

            sector = self.sector_cache.get(ticker) or analysis.get('sector', 'Unknown')

            signal = TradeSignal(
                ticker=ticker,
                action=action,
                confidence=confidence,
                target_price=target,
                stop_loss=stop,
                suggested_position_size_pct=position_size_pct,
                analysis_timestamp=analysis.get('analyzed_at', now.isoformat()),
                queued_at=now.isoformat(),
                expires_at=(now + timedelta(days=expiry_days)).isoformat(),
                metadata={
                    'company_name': analysis.get('company_name', ''),
                    'sector': sector,
                    'investment_thesis': analysis.get('investment_thesis', ''),
                    'key_metrics': analysis.get('key_metrics', {}),
                    'strengths': analysis.get('strengths', []),
                    'risks': analysis.get('risks', []),
                }
            )
            signals.append(signal)

        logger.info(f"Validated {len(signals)}/{len(analyses)} analyses into trade signals")
        return signals
