"""
Market-Aware Scheduler
Decides whether to run research or execution based on time/market status.
"""

import threading
import time
from datetime import datetime, timedelta
from typing import Optional, Callable
import logging

try:
    import schedule
except ImportError:
    schedule = None

logger = logging.getLogger("autonomous_trader")


class MarketScheduler:
    def __init__(self, config: dict):
        self.config = config
        execution_cfg = config.get('execution', {})
        self.timezone_name = execution_cfg.get('timezone', 'America/New_York')
        self._timezone = self._init_timezone()
        self.running = False
        self._stop_event = threading.Event()
        self._jobs = []

    def _init_timezone(self):
        try:
            import pytz
            return pytz.timezone(self.timezone_name)
        except ImportError:
            logger.warning("pytz not available, using local time")
            return None

    def _get_now(self) -> datetime:
        if self._timezone:
            return datetime.now(self._timezone)
        return datetime.now()

    def is_market_open(self) -> bool:
        execution_cfg = self.config.get('execution', {})

        if not execution_cfg.get('run_during_market_hours_only', True):
            return True

        now = self._get_now()

        if now.weekday() >= 5:
            return False

        try:
            market_open = datetime.strptime(
                execution_cfg.get('market_open_time', '09:30'),
                "%H:%M"
            ).time()
            market_close = datetime.strptime(
                execution_cfg.get('market_close_time', '16:00'),
                "%H:%M"
            ).time()

            return market_open <= now.time() <= market_close
        except ValueError:
            return True

    def should_run_research(self) -> bool:
        research_cfg = self.config.get('research', {})

        if not research_cfg.get('enabled', True):
            return False

        if research_cfg.get('run_when_market_closed', True):
            return True

        return self.is_market_open()

    def should_run_execution(self) -> bool:
        execution_cfg = self.config.get('execution', {})

        if not execution_cfg.get('enabled', True):
            return False

        if not execution_cfg.get('run_during_market_hours_only', True):
            return True

        if not self.is_market_open():
            return False

        open_time_str = execution_cfg.get('market_open_time', '09:30')
        delay_minutes = execution_cfg.get('delay_after_open_minutes', 0)

        if delay_minutes > 0:
            try:
                market_open = datetime.strptime(open_time_str, "%H:%M").time()
                now = self._get_now().time()
                open_dt = datetime.combine(datetime.today(), market_open)
                now_dt = datetime.combine(datetime.today(), now)
                minutes_since_open = (now_dt - open_dt).total_seconds() / 60

                if 0 <= minutes_since_open < delay_minutes:
                    logger.debug(f"Waiting for post-open window ({delay_minutes - minutes_since_open:.0f}min remaining)")
                    return False
            except ValueError:
                pass

        return True

    def run_research_job(self):
        if not self.should_run_research():
            logger.debug("Research skipped - not scheduled to run now")
            return

        logger.info("=" * 60)
        logger.info("STARTING RESEARCH PHASE")
        logger.info("=" * 60)

        try:
            from .researcher import ResearchAgent

            agent = ResearchAgent(self.config)
            signals = agent.run_research()

            if signals:
                logger.info(f"Research phase generated {len(signals)} signals")
                avg_conf = sum(s.confidence for s in signals) / len(signals)
                logger.info(f"Average confidence: {avg_conf:.2f}")
            else:
                logger.info("No signals generated in this research cycle")

        except Exception as e:
            logger.exception(f"Research phase failed: {e}")

    def run_execution_job(self):
        if not self.should_run_execution():
            if not self.is_market_open():
                logger.debug("Execution skipped - market closed")
            else:
                logger.debug("Execution skipped - waiting for post-open window")
            return

        logger.info("=" * 60)
        logger.info("STARTING EXECUTION PHASE")
        logger.info("=" * 60)

        try:
            from .executor import TradingExecutor
            from .queue import TradeQueue
            from .portfolio import PositionTracker

            queue = TradeQueue(self.config)
            executor = TradingExecutor(self.config)

            signals = queue.dequeue(
                max_signals=self.config.get('trading', {}).get('max_positions', 20)
            )

            if not signals:
                logger.info("No signals in queue to execute")
                return

            executed_signals = []
            skipped_signals = []

            for signal in signals:
                ticker = signal.ticker
                target_price = signal.target_price
                stop_loss = signal.stop_loss

                position_signal = {
                    'ticker': ticker,
                    'recommendation': signal.action,
                    'confidence': signal.confidence,
                    'target_price': target_price,
                    'stop_loss': stop_loss,
                    'position_size_pct': signal.suggested_position_size_pct,
                }

                report = executor.execute_signals([position_signal])

                if report['executed']:
                    executed_signals.append(signal)
                else:
                    skipped_signals.append(signal)

            if executed_signals:
                queue.mark_executed(executed_signals, success=True)
            if skipped_signals:
                queue.mark_executed(skipped_signals, success=False)

            logger.info(f"Execution phase complete: {len(executed_signals)} executed, {len(skipped_signals)} skipped")

        except Exception as e:
            logger.exception(f"Execution phase failed: {e}")

    def cleanup_job(self):
        from .queue import TradeQueue

        queue = TradeQueue(self.config)
        expired_count = queue.clean_expired()
        logger.info(f"Cleanup: removed {expired_count} expired signals")

    def schedule_jobs(self):
        if schedule is None:
            logger.warning("schedule module not available, using basic scheduling")
            return

        research_cfg = self.config.get('research', {})
        execution_cfg = self.config.get('execution', {})

        schedule_time = research_cfg.get('schedule', {}).get('daily_time', '18:00')
        schedule.every().day.at(schedule_time).do(self.run_research_job)
        logger.info(f"Scheduled research daily at {schedule_time}")

        check_interval = execution_cfg.get('check_interval_minutes', 15)
        schedule.every(check_interval).minutes.do(self.run_execution_job)
        logger.info(f"Scheduled execution check every {check_interval} minutes")

        schedule.every().day.at("00:05").do(self.cleanup_job)
        logger.info("Scheduled daily cleanup at 00:05")

    def run_forever(self):
        if schedule is None:
            self._run_basic_loop()
            return

        logger.info("MarketScheduler starting...")
        self.schedule_jobs()
        self.running = True

        while not self._stop_event.is_set():
            schedule.run_pending()
            time.sleep(60)

    def _run_basic_loop(self):
        logger.info("MarketScheduler starting (basic mode)...")
        self.running = True

        last_research_check = datetime.min
        last_cleanup_check = datetime.min

        while not self._stop_event.is_set():
            now = datetime.now()

            research_cfg = self.config.get('research', {})
            schedule_time = research_cfg.get('schedule', {}).get('daily_time', '18:00')
            try:
                target_hour, target_min = map(int, schedule_time.split(':'))
                research_dt = now.replace(hour=target_hour, minute=target_min, second=0, microsecond=0)

                if now >= research_dt and (now - last_research_check).total_seconds() > 3600:
                    self.run_research_job()
                    last_research_check = now
            except (ValueError, TypeError):
                pass

            check_interval = self.config.get('execution', {}).get('check_interval_minutes', 15) * 60
            if (now - last_cleanup_check).total_seconds() > check_interval:
                self.run_execution_job()
                last_cleanup_check = now

            if now.hour == 0 and now.minute < 10 and (now - last_cleanup_check).total_seconds() > 3600:
                self.cleanup_job()
                last_cleanup_check = now

            time.sleep(60)

    def stop(self):
        self._stop_event.set()
        self.running = False
        logger.info("MarketScheduler stopped")


def start_scheduler(config: dict) -> MarketScheduler:
    scheduler = MarketScheduler(config)
    thread = threading.Thread(target=scheduler.run_forever, daemon=True)
    thread.start()
    return scheduler
