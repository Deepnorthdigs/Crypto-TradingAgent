"""
Trade Queue Management for Crypto
Stores validated signals for later execution during market hours.
"""

import json
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from dataclasses import dataclass, asdict, field
from pathlib import Path
import logging

logger = logging.getLogger("autonomous_trader")


@dataclass
class TradeSignal:
    """Represents a validated trade signal ready for execution (crypto-adapted)"""
    ticker: str
    action: str
    confidence: float
    target_price: float
    stop_loss: float
    suggested_position_size_pct: float
    analysis_timestamp: str
    queued_at: str
    expires_at: str
    metadata: Dict = field(default_factory=dict)
    
    chain: str = ""
    category: str = ""
    exchange_listed: List[str] = field(default_factory=list)
    suggested_holding_period: str = ""
    catalyst_within_window: str = ""
    upcoming_unlock_flag: bool = False

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict) -> 'TradeSignal':
        return cls(**data)

    def is_expired(self) -> bool:
        expiry = datetime.fromisoformat(self.expires_at)
        return datetime.now() >= expiry

    def age_hours(self) -> float:
        queued = datetime.fromisoformat(self.queued_at)
        return (datetime.now() - queued).total_seconds() / 3600


class TradeQueue:
    def __init__(self, config: Dict, data_dir: Optional[Path] = None):
        self.config = config
        if data_dir is None:
            from .logger import get_data_dir
            data_dir = get_data_dir()
        self.queue_dir = data_dir / "queue"
        self.queue_dir.mkdir(parents=True, exist_ok=True)
        self.pending_file = self.queue_dir / "pending.json"
        self.expired_file = self.queue_dir / "expired.json"
        self._pending: List[TradeSignal] = []
        self._load_queue()

    def _load_queue(self):
        if self.pending_file.exists():
            try:
                with open(self.pending_file, 'r') as f:
                    data = json.load(f)
                self._pending = [TradeSignal.from_dict(sig) for sig in data]
                logger.info(f"Loaded {len(self._pending)} pending signals")
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning(f"Failed to load queue, starting fresh: {e}")
                self._pending = []
        else:
            self._pending = []

    def _save_queue(self):
        with open(self.pending_file, 'w') as f:
            json.dump([sig.to_dict() for sig in self._pending], f, indent=2)

    def enqueue(self, signal: TradeSignal) -> bool:
        queue_config = self.config.get('queue', {})

        if queue_config.get('deduplicate', True):
            recent_tickers = [
                sig.ticker for sig in self._pending
                if sig.age_hours() < 24
            ]
            if signal.ticker in recent_tickers:
                logger.warning(f"Queue: Skipping {signal.ticker} - already queued recently")
                return False

        max_size = queue_config.get('max_queue_size', 30)
        if len(self._pending) >= max_size:
            logger.warning(f"Queue full ({len(self._pending)} signals). Rejecting {signal.ticker}")
            return False

        if signal.is_expired():
            logger.warning(f"Queue: Signal for {signal.ticker} already expired")
            return False

        self._pending.append(signal)
        self._save_queue()
        logger.info(f"Queued {signal.ticker} (expires: {signal.expires_at}, category: {signal.category})")
        return True

    def dequeue(self, max_signals: Optional[int] = None) -> List[TradeSignal]:
        valid = [sig for sig in self._pending if not sig.is_expired()]
        valid.sort(key=lambda x: x.confidence, reverse=True)

        if max_signals:
            valid = valid[:max_signals]

        self._pending = [sig for sig in self._pending if sig not in valid]
        self._save_queue()

        logger.info(f"Dequeued {len(valid)} signals for execution")
        return valid

    def mark_executed(self, signals: List[TradeSignal], success: bool = True):
        date_str = datetime.now().strftime('%Y-%m-%d')
        executed_file = self.queue_dir / f"executed_{date_str}.json"

        if success:
            if executed_file.exists():
                with open(executed_file, 'r') as f:
                    existing = json.load(f)
            else:
                existing = []

            existing.extend([sig.to_dict() for sig in signals])
            with open(executed_file, 'w') as f:
                json.dump(existing, f, indent=2)

            logger.info(f"Marked {len(signals)} signals as executed")
        else:
            queue_config = self.config.get('queue', {})
            requeue = queue_config.get('requeue_failed', True)

            if requeue:
                expiry_days = self.config.get('execution', {}).get('signal_expiry_days', 7)
                for sig in signals:
                    sig.queued_at = datetime.now().isoformat()
                    sig.expires_at = (datetime.now() + timedelta(days=expiry_days)).isoformat()
                    self._pending.append(sig)
                self._save_queue()
                logger.warning(f"Re-queued {len(signals)} failed signals")

    def clean_expired(self) -> int:
        expired = [sig for sig in self._pending if sig.is_expired()]

        if expired:
            if self.expired_file.exists():
                with open(self.expired_file, 'r') as f:
                    existing = json.load(f)
            else:
                existing = []

            existing.extend([sig.to_dict() for sig in expired])
            with open(self.expired_file, 'w') as f:
                json.dump(existing, f, indent=2)

            self._pending = [sig for sig in self._pending if sig not in expired]
            self._save_queue()

            logger.info(f"Cleaned {len(expired)} expired signals")

        return len(expired)

    def get_stats(self) -> Dict:
        total = len(self._pending)
        expired = sum(1 for sig in self._pending if sig.is_expired())
        valid = total - expired

        by_ticker: Dict[str, int] = {}
        for sig in self._pending:
            by_ticker[sig.ticker] = by_ticker.get(sig.ticker, 0) + 1

        return {
            'total_pending': total,
            'valid': valid,
            'expired': expired,
            'by_ticker': by_ticker,
            'queue_file': str(self.pending_file)
        }

    def get_pending(self) -> List[TradeSignal]:
        return [sig for sig in self._pending if not sig.is_expired()]
