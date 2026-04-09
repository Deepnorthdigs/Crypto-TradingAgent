"""
Research Agent: Screening + Analysis for Crypto Swing Trading
Runs anytime, generates signals and queues them.
"""

import logging
from datetime import datetime, timedelta
from typing import List, Dict
from .screener import CryptoScreener
from .analyzer import CryptoAnalyzer
from .queue import TradeQueue, TradeSignal
from .portfolio import TickerSectorCache

logger = logging.getLogger("autonomous_trader")


class ResearchAgent:
    def __init__(self, config: dict):
        self.config = config
        self.screener = CryptoScreener(config)
        self.analyzer = CryptoAnalyzer(config)
        self.queue = TradeQueue(config)
        self.category_cache = TickerSectorCache()

    def run_research(self) -> List[TradeSignal]:
        logger.info("Starting crypto research pipeline...")

        candidates = self.screener.screen()

        if not candidates:
            logger.warning("No candidates after screening")
            return []

        analyses = self.analyzer.analyze_batch(candidates)
        if not analyses:
            logger.warning("No analyses produced")
            return []

        signals = self._validate_and_create_signals(analyses)

        max_signals = self.config.get('research', {}).get('max_signals_per_day', 5)
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
        expiry_days = self.config.get('execution', {}).get('signal_expiry_days', 7)
        queue_config = self.config.get('queue', {})
        trading_config = self.config.get('trading', {})

        for analysis in analyses:
            symbol = analysis.get('symbol')
            confidence = analysis.get('confidence', 0)
            action = analysis.get('signal', analysis.get('recommendation', 'HOLD'))

            if action.upper() != 'BUY':
                logger.debug(f"Skipping {symbol}: action={action}")
                continue

            if analysis.get('upcoming_unlock_flag'):
                logger.info(f"Skipping {symbol}: upcoming token unlock >5% of circulating supply")
                continue

            min_conf = trading_config.get('min_confidence', 0.65)
            if confidence < min_conf:
                logger.debug(f"Skipping {symbol}: confidence {confidence} < {min_conf}")
                continue

            current_price = analysis.get('current_price', 0)
            stop_loss_pct = trading_config.get('stop_loss_pct', 0.08)
            tp1_pct = trading_config.get('take_profit_pct_1', 0.25)

            if current_price <= 0:
                logger.warning(f"Skipping {symbol}: invalid price {current_price}")
                continue

            target_price = current_price * (1 + tp1_pct)
            stop_price = current_price * (1 - stop_loss_pct)

            position_size_pct = analysis.get('position_size_pct', 0.05)
            max_size = queue_config.get('max_position_size_pct', 0.05)
            if position_size_pct > max_size:
                logger.info(f"Reducing position size for {symbol} from {position_size_pct:.1%} to {max_size:.1%}")
                position_size_pct = max_size

            category = analysis.get('category', 'Unknown')
            chain = analysis.get('chain', '')
            exchange_listed = analysis.get('exchange_listed', ['bybit'])

            signal = TradeSignal(
                ticker=symbol,
                action=action,
                confidence=confidence,
                target_price=target_price,
                stop_loss=stop_price,
                suggested_position_size_pct=position_size_pct,
                analysis_timestamp=analysis.get('analyzed_at', now.isoformat()),
                queued_at=now.isoformat(),
                expires_at=(now + timedelta(days=expiry_days)).isoformat(),
                chain=chain,
                category=category,
                exchange_listed=exchange_listed,
                suggested_holding_period=analysis.get('suggested_holding_period', '2-4 weeks'),
                catalyst_within_window=analysis.get('upcoming_catalysts', ''),
                upcoming_unlock_flag=analysis.get('upcoming_unlock_flag', False),
                metadata={
                    'entry_rationale': analysis.get('entry_rationale', ''),
                    'exit_conditions': analysis.get('exit_conditions', ''),
                    'bull_case': analysis.get('bull_case', ''),
                    'bear_case': analysis.get('bear_case', ''),
                    'key_risks': analysis.get('key_risks', ''),
                    'technical_score': analysis.get('technical_score', 0),
                    'sentiment_score': analysis.get('sentiment_score', 0),
                    'fundamentals_score': analysis.get('fundamentals_score', 0),
                    'project_quality_score': analysis.get('project_quality_score', 0),
                }
            )
            signals.append(signal)

        logger.info(f"Validated {len(signals)}/{len(analyses)} analyses into trade signals")
        return signals
