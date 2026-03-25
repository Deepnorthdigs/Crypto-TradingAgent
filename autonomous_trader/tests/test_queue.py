import pytest
import json
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestTradeSignal:
    def test_trade_signal_creation(self):
        from src.queue import TradeSignal
        
        now = datetime.now()
        signal = TradeSignal(
            ticker="AAPL",
            action="BUY",
            confidence=0.75,
            target_price=180.0,
            stop_loss=150.0,
            suggested_position_size_pct=0.05,
            analysis_timestamp=now.isoformat(),
            queued_at=now.isoformat(),
            expires_at=(now + timedelta(days=2)).isoformat(),
        )
        
        assert signal.ticker == "AAPL"
        assert signal.action == "BUY"
        assert signal.confidence == 0.75
        assert signal.is_expired() is False
    
    def test_trade_signal_expiry(self):
        from src.queue import TradeSignal
        
        now = datetime.now()
        signal = TradeSignal(
            ticker="AAPL",
            action="BUY",
            confidence=0.75,
            target_price=180.0,
            stop_loss=150.0,
            suggested_position_size_pct=0.05,
            analysis_timestamp=now.isoformat(),
            queued_at=now.isoformat(),
            expires_at=(now - timedelta(hours=1)).isoformat(),
        )
        
        assert signal.is_expired() is True
    
    def test_trade_signal_age(self):
        from src.queue import TradeSignal
        
        now = datetime.now()
        signal = TradeSignal(
            ticker="AAPL",
            action="BUY",
            confidence=0.75,
            target_price=180.0,
            stop_loss=150.0,
            suggested_position_size_pct=0.05,
            analysis_timestamp=now.isoformat(),
            queued_at=(now - timedelta(hours=5)).isoformat(),
            expires_at=(now + timedelta(days=2)).isoformat(),
        )
        
        assert 4.5 < signal.age_hours() < 5.5
    
    def test_trade_signal_serialization(self):
        from src.queue import TradeSignal
        
        now = datetime.now()
        signal = TradeSignal(
            ticker="AAPL",
            action="BUY",
            confidence=0.75,
            target_price=180.0,
            stop_loss=150.0,
            suggested_position_size_pct=0.05,
            analysis_timestamp=now.isoformat(),
            queued_at=now.isoformat(),
            expires_at=(now + timedelta(days=2)).isoformat(),
            metadata={"sector": "Technology"},
        )
        
        data = signal.to_dict()
        restored = TradeSignal.from_dict(data)
        
        assert restored.ticker == signal.ticker
        assert restored.confidence == signal.confidence
        assert restored.metadata["sector"] == "Technology"


class TestTradeQueue:
    def get_config(self):
        return {
            "execution": {"signal_expiry_days": 2},
            "queue": {
                "deduplicate": True,
                "requeue_failed": True,
                "max_queue_size": 50,
                "max_position_size_pct": 0.05,
            },
        }
    
    def test_queue_initialization(self, tmp_path):
        from src.queue import TradeQueue
        
        config = self.get_config()
        queue = TradeQueue(config, data_dir=tmp_path)
        
        assert queue._pending == []
        assert queue.queue_dir.exists()
    
    def test_enqueue_signal(self, tmp_path):
        from src.queue import TradeQueue, TradeSignal
        
        config = self.get_config()
        queue = TradeQueue(config, data_dir=tmp_path)
        
        now = datetime.now()
        signal = TradeSignal(
            ticker="AAPL",
            action="BUY",
            confidence=0.75,
            target_price=180.0,
            stop_loss=150.0,
            suggested_position_size_pct=0.05,
            analysis_timestamp=now.isoformat(),
            queued_at=now.isoformat(),
            expires_at=(now + timedelta(days=2)).isoformat(),
        )
        
        result = queue.enqueue(signal)
        
        assert result is True
        assert len(queue._pending) == 1
    
    def test_deduplicate_same_ticker(self, tmp_path):
        from src.queue import TradeQueue, TradeSignal
        
        config = self.get_config()
        queue = TradeQueue(config, data_dir=tmp_path)
        
        now = datetime.now()
        for _ in range(3):
            signal = TradeSignal(
                ticker="AAPL",
                action="BUY",
                confidence=0.75,
                target_price=180.0,
                stop_loss=150.0,
                suggested_position_size_pct=0.05,
                analysis_timestamp=now.isoformat(),
                queued_at=now.isoformat(),
                expires_at=(now + timedelta(days=2)).isoformat(),
            )
            queue.enqueue(signal)
        
        assert len(queue._pending) == 1
    
    def test_dequeue_orders_by_confidence(self, tmp_path):
        from src.queue import TradeQueue, TradeSignal
        
        config = self.get_config()
        queue = TradeQueue(config, data_dir=tmp_path)
        
        now = datetime.now()
        for conf in [0.6, 0.9, 0.75]:
            signal = TradeSignal(
                ticker=f"T{conf}",
                action="BUY",
                confidence=conf,
                target_price=180.0,
                stop_loss=150.0,
                suggested_position_size_pct=0.05,
                analysis_timestamp=now.isoformat(),
                queued_at=now.isoformat(),
                expires_at=(now + timedelta(days=2)).isoformat(),
            )
            queue.enqueue(signal)
        
        dequeued = queue.dequeue(max_signals=2)
        
        assert len(dequeued) == 2
        assert dequeued[0].confidence >= dequeued[1].confidence
    
    def test_clean_expired(self, tmp_path):
        from src.queue import TradeQueue, TradeSignal
        
        config = self.get_config()
        queue = TradeQueue(config, data_dir=tmp_path)
        
        now = datetime.now()
        
        valid_signal = TradeSignal(
            ticker="VALID",
            action="BUY",
            confidence=0.75,
            target_price=180.0,
            stop_loss=150.0,
            suggested_position_size_pct=0.05,
            analysis_timestamp=now.isoformat(),
            queued_at=now.isoformat(),
            expires_at=(now + timedelta(days=2)).isoformat(),
        )
        
        expired_signal = TradeSignal(
            ticker="EXPIRED",
            action="BUY",
            confidence=0.75,
            target_price=180.0,
            stop_loss=150.0,
            suggested_position_size_pct=0.05,
            analysis_timestamp=now.isoformat(),
            queued_at=(now - timedelta(days=3)).isoformat(),
            expires_at=(now - timedelta(days=1)).isoformat(),
        )
        
        queue.enqueue(valid_signal)
        queue._pending.append(expired_signal)
        queue._save_queue()
        
        assert len(queue._pending) == 2
        
        cleaned = queue.clean_expired()
        
        assert cleaned == 1
        assert len(queue._pending) == 1
        assert queue._pending[0].ticker == "VALID"
    
    def test_get_stats(self, tmp_path):
        from src.queue import TradeQueue, TradeSignal
        
        config = self.get_config()
        queue = TradeQueue(config, data_dir=tmp_path)
        
        now = datetime.now()
        for ticker in ["AAPL", "MSFT", "GOOGL"]:
            signal = TradeSignal(
                ticker=ticker,
                action="BUY",
                confidence=0.75,
                target_price=180.0,
                stop_loss=150.0,
                suggested_position_size_pct=0.05,
                analysis_timestamp=now.isoformat(),
                queued_at=now.isoformat(),
                expires_at=(now + timedelta(days=2)).isoformat(),
            )
            queue.enqueue(signal)
        
        stats = queue.get_stats()
        
        assert stats["total_pending"] == 3
        assert stats["valid"] == 3
        assert stats["expired"] == 0
