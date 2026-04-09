"""
Crypto Trading Executor - CCXT/Bybit Implementation
Replaces Alpaca API with CCXT for crypto spot trading on Bybit.
"""

import logging
import os
from datetime import datetime, time
from typing import Optional, Dict, List, Any

try:
    import ccxt
except ImportError:
    ccxt = None

from .market_data import CryptoMarketData, format_symbol_for_exchange


logger = logging.getLogger("autonomous_trader")


class TradingExecutor:
    def __init__(self, config: dict):
        self.config = config
        self.trading_config = config.get("trading", {})
        self.exchange_config = config.get("exchange", {})
        self.dry_run = self.trading_config.get("dry_run", True)
        self._exchange = None
        self._market_data = CryptoMarketData(config)
        self._init_api()
    
    def _init_api(self):
        if self.dry_run:
            logger.info("Running in DRY RUN mode - no orders will be executed")
            return
        
        if ccxt is None:
            logger.error("CCXT not installed. Run: pip install ccxt")
            return
        
        try:
            exchange_name = self.exchange_config.get("name", "bybit")
            testnet = self.exchange_config.get("testnet", True)
            
            if exchange_name == "bybit":
                if testnet:
                    self._exchange = ccxt.bybit({
                        "enableRateLimit": True,
                        "options": {"defaultType": "spot"},
                    })
                    self._exchange.set_sandbox_mode(True)
                    logger.info("Bybit testnet mode enabled")
                else:
                    self._exchange = ccxt.bybit({
                        "enableRateLimit": True,
                        "apiKey": self.exchange_config.get("api_key"),
                        "secret": self.exchange_config.get("api_secret"),
                        "options": {"defaultType": "spot"},
                    })
            else:
                self._exchange = getattr(ccxt, exchange_name)({
                    "enableRateLimit": True,
                    "apiKey": self.exchange_config.get("api_key"),
                    "secret": self.exchange_config.get("api_secret"),
                })
            
            self._exchange.load_markets()
            logger.info(f"Initialized {exchange_name} exchange")
        except Exception as e:
            logger.error(f"Failed to initialize exchange: {e}")
            self._exchange = None
    
    @property
    def exchange(self):
        return self._exchange
    
    def _is_quiet_hours(self) -> bool:
        """Check if currently in quiet hours (for new entries only)."""
        quiet_start = self.trading_config.get("quiet_hours_start", "02:00")
        quiet_end = self.trading_config.get("quiet_hours_end", "05:00")
        
        try:
            start_time = time.fromisoformat(quiet_start)
            end_time = time.fromisoformat(quiet_end)
        except ValueError:
            return False
        
        current_time = datetime.utcnow().time()
        
        if start_time <= end_time:
            return start_time <= current_time <= end_time
        else:
            return current_time >= start_time or current_time <= end_time
    
    def _check_slippage(self, symbol: str, slippage_tolerance: float = 0.01) -> bool:
        """Check if spread is acceptable before executing."""
        if self.dry_run:
            return True
        
        try:
            orderbook = self._exchange.fetch_order_book(symbol, limit=5)
            best_bid = orderbook["bids"][0][0] if orderbook["bids"] else 0
            best_ask = orderbook["asks"][0][0] if orderbook["asks"] else 0
            
            if best_ask > 0:
                spread_pct = (best_ask - best_bid) / best_ask
                if spread_pct > slippage_tolerance:
                    logger.warning(f"High spread for {symbol}: {spread_pct*100:.2f}% exceeds tolerance")
                    return False
        except Exception as e:
            logger.warning(f"Could not check slippage for {symbol}: {e}")
        
        return True
    
    def get_account_info(self) -> dict:
        if self.dry_run:
            return {
                "equity": 100000.0,
                "buying_power": 100000.0,
                "cash": 100000.0,
            }
        
        try:
            balance = self._exchange.fetch_balance()
            total_usd = balance.get("total", {}).get("USDT", 0) or 0
            return {
                "equity": total_usd,
                "buying_power": total_usd,
                "cash": total_usd,
            }
        except Exception as e:
            logger.error(f"Failed to get account info: {e}")
            return {"equity": 0, "buying_power": 0, "cash": 0}
    
    def get_current_positions(self) -> list:
        if self.dry_run:
            return []
        
        try:
            balance = self._exchange.fetch_balance()
            positions = []
            
            for currency, balance_info in balance.get("total", {}).items():
                if balance_info and balance_info > 0 and currency not in ["USDT", "USD", "BTC"]:
                    symbol = f"{currency}/USDT"
                    if symbol in self._exchange.markets:
                        try:
                            ticker = self._exchange.fetch_ticker(symbol)
                            price = ticker.get("last", 0)
                            value = balance_info * price
                            
                            positions.append({
                                "symbol": symbol,
                                "qty": balance_info,
                                "market_value": value,
                                "avg_entry_price": price,
                                "current_price": price,
                                "unrealized_pl": 0,
                                "category": balance_info.get("category", "Unknown"),
                            })
                        except Exception:
                            continue
            
            return positions
        except Exception as e:
            logger.error(f"Failed to get positions: {e}")
            return []
    
    def get_current_price(self, symbol: str) -> Optional[float]:
        if self.dry_run:
            return self._market_data.get_current_price(symbol)
        
        try:
            ticker = self._exchange.fetch_ticker(symbol)
            return ticker.get("last")
        except Exception as e:
            logger.error(f"Failed to get price for {symbol}: {e}")
            return None
    
    def calculate_position_size(self, signal: dict, total_capital: float) -> tuple[float, float]:
        base_size_pct = self.trading_config.get("position_size_pct", 0.05)
        confidence = signal.get("confidence", 0.65)
        max_position_value = self.config.get("risk", {}).get("max_position_value", 50000)
        
        base_size = total_capital * base_size_pct
        
        confidence_multiplier = min(1.0, max(0.5, confidence / 0.5))
        adjusted_size = base_size * confidence_multiplier
        
        position_value = min(adjusted_size, max_position_value)
        
        current_price = self.get_current_price(signal.get("symbol"))
        if not current_price or current_price <= 0:
            logger.warning(f"Cannot calculate position size for {signal.get('symbol')}: no valid price")
            return 0.0, 0.0
        
        quantity = position_value / current_price
        
        return quantity, current_price
    
    def _validate_order_prices(self, symbol: str, current_price: float,
                               target_price: float, stop_price: float) -> bool:
        if not (stop_price < current_price < target_price * 1.5):
            logger.warning(f"Invalid price setup for {symbol}: stop={stop_price}, current={current_price}, target={target_price}")
            return False
        return True
    
    def submit_bracket_order(self, symbol: str, quantity: float, side: str,
                            target_price: float, stop_price: float,
                            signal: dict) -> Optional[dict]:
        stop_loss_pct = self.trading_config.get("stop_loss_pct", 0.08)
        tp1_pct = self.trading_config.get("take_profit_pct_1", 0.25)
        tp2_pct = self.trading_config.get("take_profit_pct_2", 0.50)
        partial_tp = self.trading_config.get("partial_take_profit", True)
        
        if self.dry_run:
            logger.info(f"[DRY RUN] Would submit bracket order: {side} {quantity} {symbol} @ market, "
                       f"TP1: ${target_price * (1 + tp1_pct):.4f}, TP2: ${target_price * (1 + tp2_pct):.4f}, "
                       f"SL: ${stop_price:.4f}")
            
            entry_order_id = f"dry_run_entry_{datetime.now().timestamp()}"
            tp1_order_id = f"dry_run_tp1_{datetime.now().timestamp()}"
            tp2_order_id = f"dry_run_tp2_{datetime.now().timestamp()}"
            sl_order_id = f"dry_run_sl_{datetime.now().timestamp()}"
            
            return {
                "id": entry_order_id,
                "symbol": symbol,
                "qty": quantity,
                "side": side,
                "limit_price": target_price,
                "stop_price": stop_price,
                "status": "dry_run",
                "child_orders": {
                    "tp1": tp1_order_id,
                    "tp2": tp2_order_id,
                    "sl": sl_order_id,
                },
            }
        
        try:
            entry_order = self._exchange.create_market_buy_order(symbol, quantity)
            entry_order_id = entry_order.get("id")
            
            tp1_qty = quantity * 0.5 if partial_tp else quantity
            tp1_price = target_price * (1 + tp1_pct)
            tp1_order = self._exchange.create_limit_sell_order(
                symbol, tp1_qty, tp1_price
            )
            tp1_order_id = tp1_order.get("id")
            
            tp2_qty = quantity * 0.5 if partial_tp else 0
            tp2_order_id = None
            if tp2_qty > 0:
                tp2_price = target_price * (1 + tp2_pct)
                tp2_order = self._exchange.create_limit_sell_order(
                    symbol, tp2_qty, tp2_price
                )
                tp2_order_id = tp2_order.get("id")
            
            sl_order = self._exchange.create_stop_loss_limit_order(
                symbol, quantity, stop_price, stop_price
            )
            sl_order_id = sl_order.get("id")
            
            return {
                "id": entry_order_id,
                "symbol": symbol,
                "qty": quantity,
                "side": side,
                "limit_price": target_price,
                "stop_price": stop_price,
                "status": entry_order.get("status", "filled"),
                "child_orders": {
                    "tp1": tp1_order_id,
                    "tp2": tp2_order_id,
                    "sl": sl_order_id,
                },
            }
            
        except Exception as e:
            logger.error(f"Failed to submit order for {symbol}: {e}")
            return None
    
    def cancel_order(self, order_id: str, symbol: str) -> bool:
        if self.dry_run:
            logger.info(f"[DRY RUN] Would cancel order {order_id}")
            return True
        
        try:
            self._exchange.cancel_order(order_id, symbol)
            return True
        except Exception as e:
            logger.warning(f"Failed to cancel order {order_id}: {e}")
            return False
    
    def cancel_all_child_orders(self, symbol: str, child_orders: Dict) -> None:
        """Cancel remaining TP/SL orders when position is fully closed."""
        if self.dry_run:
            logger.info(f"[DRY RUN] Would cancel all child orders for {symbol}")
            return
        
        for order_type, order_id in child_orders.items():
            if order_id:
                self.cancel_order(order_id, symbol)
    
    def execute_signals(self, signals: list, category_mapping: dict = None) -> dict:
        logger.info(f"Executing signals for {len(signals)} candidates")
        
        if self._is_quiet_hours():
            logger.info("Currently in quiet hours - skipping new entries")
        
        account = self.get_account_info()
        total_capital = account.get("equity", 100000)
        
        existing_positions = {p["symbol"]: p for p in self.get_current_positions()}
        
        buy_signals = [s for s in signals if s.get("signal", s.get("recommendation", "")).upper() == "BUY"]
        
        report = {
            "executed": [],
            "skipped": [],
            "failed": [],
            "total_capital": total_capital,
            "timestamp": datetime.now().isoformat(),
        }
        
        for signal in buy_signals:
            symbol = signal.get("symbol", "").upper()
            
            if not symbol.endswith("/USDT"):
                symbol = f"{symbol}/USDT"
            
            if self._is_quiet_hours():
                logger.info(f"Skipping {symbol}: quiet hours")
                report["skipped"].append({
                    "symbol": symbol,
                    "reason": "quiet_hours"
                })
                continue
            
            if symbol in existing_positions:
                logger.info(f"Skipping {symbol}: already in portfolio")
                report["skipped"].append({
                    "symbol": symbol,
                    "reason": "already_holding"
                })
                continue
            
            if not self._check_slippage(symbol):
                report["skipped"].append({
                    "symbol": symbol,
                    "reason": "high_spread"
                })
                continue
            
            current_price = self.get_current_price(symbol)
            if not current_price:
                logger.error(f"Cannot execute {symbol}: unable to get current price")
                report["failed"].append({
                    "symbol": symbol,
                    "reason": "price_unavailable"
                })
                continue
            
            quantity, _ = self.calculate_position_size(signal, total_capital)
            if quantity <= 0:
                logger.warning(f"Skipping {symbol}: invalid position size")
                report["skipped"].append({
                    "symbol": symbol,
                    "reason": "invalid_size"
                })
                continue
            
            tp1_pct = self.trading_config.get("take_profit_pct_1", 0.25)
            tp2_pct = self.trading_config.get("take_profit_pct_2", 0.50)
            stop_loss_pct = self.trading_config.get("stop_loss_pct", 0.08)
            
            target_price = signal.get("target_price") or current_price * (1 + tp1_pct)
            stop_price = signal.get("stop_loss") or current_price * (1 - stop_loss_pct)
            
            category = category_mapping.get(symbol, "Unknown") if category_mapping else "Unknown"
            
            order = self.submit_bracket_order(
                symbol=symbol,
                quantity=quantity,
                side="buy",
                target_price=target_price,
                stop_price=stop_price,
                signal=signal
            )
            
            if order:
                report["executed"].append({
                    "order": order,
                    "signal": signal,
                    "quantity": quantity,
                    "price": current_price,
                    "category": category,
                })
                logger.info(f"Executed BUY for {symbol}: {quantity} units @ ${current_price:.4f}")
            else:
                report["failed"].append({
                    "symbol": symbol,
                    "reason": "order_failed"
                })
        
        logger.info(f"Execution complete: {len(report['executed'])} executed, "
                   f"{len(report['skipped'])} skipped, {len(report['failed'])} failed")
        
        return report
    
    def close_position(self, symbol: str, qty: Optional[float] = None) -> bool:
        if self.dry_run:
            logger.info(f"[DRY RUN] Would close position: {symbol}")
            return True
        
        try:
            balance = self._exchange.fetch_balance()
            if symbol in balance.get("total", {}):
                holdings = balance["total"][symbol]
                if holdings and holdings > 0:
                    sell_qty = qty if qty else holdings
                    self._exchange.create_market_sell_order(symbol, sell_qty)
                    return True
        except Exception as e:
            logger.error(f"Failed to close position {symbol}: {e}")
            return False
        
        return False
