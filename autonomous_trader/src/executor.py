import logging
import os
from datetime import datetime
from typing import Optional

logger = logging.getLogger("autonomous_trader")


def _get_alpaca_api():
    import alpaca_trade_api as tradeapi
    return tradeapi


class TradingExecutor:
    def __init__(self, config: dict):
        self.config = config
        self.trading_config = config.get("trading", {})
        self.alpaca_config = config.get("alpaca", {})
        self.dry_run = self.trading_config.get("dry_run", True)
        self._api = self._init_api()
    
    def _init_api(self):
        if self.dry_run:
            logger.info("Running in DRY RUN mode - no orders will be executed")
            return None
        
        try:
            tradeapi = _get_alpaca_api()
            api = tradeapi.REST(
                self.alpaca_config.get("paper_key"),
                self.alpaca_config.get("paper_secret"),
                self.alpaca_config.get("base_url", "https://paper-api.alpaca.markets"),
                api_version="v2"
            )
            api.get_account()
            return api
        except Exception as e:
            logger.error(f"Failed to initialize Alpaca API: {e}")
            return None
    
    def get_account_info(self) -> dict:
        if self.dry_run:
            return {
                "equity": 100000.0,
                "buying_power": 100000.0,
                "cash": 100000.0,
            }
        
        try:
            account = self._api.get_account()
            return {
                "equity": float(account.equity),
                "buying_power": float(account.buying_power),
                "cash": float(account.cash),
            }
        except Exception as e:
            logger.error(f"Failed to get account info: {e}")
            return {"equity": 0, "buying_power": 0, "cash": 0}
    
    def get_current_positions(self) -> list:
        if self.dry_run:
            return []
        
        try:
            positions = self._api.list_positions()
            return [
                {
                    "symbol": p.symbol,
                    "qty": float(p.qty),
                    "market_value": float(p.market_value),
                    "avg_entry_price": float(p.avg_entry_price),
                    "current_price": float(p.current_price),
                    "unrealized_pl": float(p.unrealized_pl),
                    "sector": getattr(p, "sector", "Unknown"),
                }
                for p in positions
            ]
        except Exception as e:
            logger.error(f"Failed to get positions: {e}")
            return []
    
    def get_current_price(self, ticker: str) -> Optional[float]:
        if self.dry_run:
            import yfinance
            try:
                data = yfinance.Ticker(ticker).info
                return data.get("currentPrice") or data.get("regularMarketPrice")
            except:
                return None
        
        try:
            bar = self._api.get_crypto_bars(ticker, "1Day").df.iloc[-1]
            return float(bar.close)
        except:
            try:
                bar = self._api.get_bars(ticker, "1Day").df.iloc[-1]
                return float(bar.close)
            except Exception as e:
                logger.error(f"Failed to get price for {ticker}: {e}")
                return None
    
    def calculate_position_size(self, signal: dict, total_capital: float) -> tuple[int, float]:
        base_size_pct = self.trading_config.get("position_size_pct", 0.05)
        confidence = signal.get("confidence", 0.65)
        max_position_value = self.config.get("risk", {}).get("max_position_value", 50000)
        
        base_size = total_capital * base_size_pct
        
        confidence_multiplier = min(1.0, max(0.5, confidence / 0.5))
        adjusted_size = base_size * confidence_multiplier
        
        position_value = min(adjusted_size, max_position_value)
        
        current_price = self.get_current_price(signal.get("ticker"))
        if not current_price or current_price <= 0:
            logger.warning(f"Cannot calculate position size for {signal.get('ticker')}: no valid price")
            return 0, 0.0
        
        quantity = int(position_value / current_price)
        quantity = max(1, quantity)
        
        return quantity, current_price
    
    def _validate_order_prices(self, ticker: str, current_price: float, 
                                target_price: float, stop_price: float) -> bool:
        if not (stop_price < current_price < target_price * 1.5):
            logger.warning(f"Invalid price setup for {ticker}: stop={stop_price}, current={current_price}, target={target_price}")
            return False
        return True
    
    def submit_bracket_order(self, ticker: str, quantity: int, side: str,
                            target_price: float, stop_price: float,
                            signal: dict) -> Optional[dict]:
        if self.dry_run:
            logger.info(f"[DRY RUN] Would submit bracket order: {side} {quantity} {ticker} @ market, "
                       f"target: ${target_price:.2f}, stop: ${stop_price:.2f}")
            return {
                "id": f"dry_run_{datetime.now().timestamp()}",
                "symbol": ticker,
                "qty": quantity,
                "side": side,
                "limit_price": target_price,
                "stop_price": stop_price,
                "status": "dry_run",
            }
        
        try:
            order = self._api.submit_order(
                symbol=ticker,
                qty=quantity,
                side=side,
                type="market",
                time_in_force="day",
                order_class="bracket",
                limit_price=round(target_price, 2),
                stop_loss={"stop_price": round(stop_price, 2)},
                take_profit={"limit_price": round(target_price * 1.02, 2)},
            )
            
            return {
                "id": order.id,
                "symbol": ticker,
                "qty": quantity,
                "side": side,
                "limit_price": target_price,
                "stop_price": stop_price,
                "status": order.status,
            }
            
        except Exception as e:
            logger.error(f"Failed to submit order for {ticker}: {e}")
            return None
    
    def execute_signals(self, signals: list, sector_mapping: dict = None) -> dict:
        logger.info(f"Executing signals for {len(signals)} candidates")
        
        account = self.get_account_info()
        total_capital = account.get("equity", 100000)
        
        existing_positions = {p["symbol"]: p for p in self.get_current_positions()}
        
        buy_signals = [s for s in signals if s.get("recommendation", "").upper() == "BUY"]
        
        report = {
            "executed": [],
            "skipped": [],
            "failed": [],
            "total_capital": total_capital,
            "timestamp": datetime.now().isoformat(),
        }
        
        for signal in buy_signals:
            ticker = signal.get("ticker", "").upper()
            
            if ticker in existing_positions:
                logger.info(f"Skipping {ticker}: already in portfolio")
                report["skipped"].append({
                    "ticker": ticker,
                    "reason": "already_holding"
                })
                continue
            
            current_price = self.get_current_price(ticker)
            if not current_price:
                logger.error(f"Cannot execute {ticker}: unable to get current price")
                report["failed"].append({
                    "ticker": ticker,
                    "reason": "price_unavailable"
                })
                continue
            
            quantity, _ = self.calculate_position_size(signal, total_capital)
            if quantity <= 0:
                logger.warning(f"Skipping {ticker}: invalid position size")
                report["skipped"].append({
                    "ticker": ticker,
                    "reason": "invalid_size"
                })
                continue
            
            target_price = signal.get("target_price", current_price * 1.1)
            stop_loss = signal.get("stop_loss", current_price * 0.95)
            
            if not self._validate_order_prices(ticker, current_price, target_price, stop_loss):
                report["skipped"].append({
                    "ticker": ticker,
                    "reason": "invalid_prices",
                    "current": current_price,
                    "target": target_price,
                    "stop": stop_loss,
                })
                continue
            
            sector = sector_mapping.get(ticker, "Unknown") if sector_mapping else "Unknown"
            
            order = self.submit_bracket_order(
                ticker=ticker,
                quantity=quantity,
                side="buy",
                target_price=target_price,
                stop_price=stop_loss,
                signal=signal
            )
            
            if order:
                report["executed"].append({
                    "order": order,
                    "signal": signal,
                    "quantity": quantity,
                    "price": current_price,
                    "sector": sector,
                })
                logger.info(f"Executed BUY for {ticker}: {quantity} shares @ ${current_price:.2f}")
            else:
                report["failed"].append({
                    "ticker": ticker,
                    "reason": "order_failed"
                })
        
        logger.info(f"Execution complete: {len(report['executed'])} executed, "
                   f"{len(report['skipped'])} skipped, {len(report['failed'])} failed")
        
        return report
    
    def close_position(self, ticker: str, qty: Optional[int] = None) -> bool:
        if self.dry_run:
            logger.info(f"[DRY RUN] Would close position: {ticker}")
            return True
        
        try:
            self._api.close_position(ticker, qty=qty)
            return True
        except Exception as e:
            logger.error(f"Failed to close position {ticker}: {e}")
            return False
