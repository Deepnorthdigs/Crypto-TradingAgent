"""
Crypto Analyzer - Deep Multi-Layer Analysis for Swing Trading
Adapts the stock analyzer for crypto with focus on swing/position trading timeframes.
"""

import json
import logging
import os
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List, Any

import requests

from .market_data import CryptoMarketData


logger = logging.getLogger("autonomous_trader")


class CryptoAnalyzer:
    def __init__(self, config: dict):
        self.config = config
        self.analysis_config = config.get("analysis", {})
        self.trading_config = config.get("trading", {})
        self.api_keys = config.get("api_keys", {})
        self.min_confidence = self.trading_config.get("min_confidence", 0.65)
        self.weights = self.analysis_config.get("weights", {
            "technical": 0.25,
            "sentiment": 0.25,
            "fundamentals": 0.30,
            "project_quality": 0.20,
        })
        self._prompt_template = self._load_prompt_template()
        self._market_data = CryptoMarketData(config)
    
    def _load_prompt_template(self) -> str:
        template_path = self.analysis_config.get("prompt_template", "templates/crypto_analysis_prompt.md")
        project_root = Path(__file__).parent.parent
        full_path = project_root / template_path.lstrip("/")
        
        if full_path.exists() and full_path.is_file():
            with open(full_path, "r") as f:
                return f.read()
        
        return self._get_default_template()
    
    def _get_default_template(self) -> str:
        return """Analyze the cryptocurrency {symbol} and provide a swing trading recommendation.

Return ONLY valid JSON with this structure:
{{
  "symbol": "{symbol}",
  "signal": "BUY|SELL|HOLD",
  "confidence": 0.0-1.0,
  "suggested_holding_period": "2-4 weeks",
  "entry_rationale": "Explanation",
  "exit_conditions": "What invalidates thesis",
  "bull_case": "Best case",
  "bear_case": "Worst case",
  "key_risks": "Holding period risks",
  "upcoming_catalysts": "Known catalysts",
  "technical_score": 0.0-1.0,
  "sentiment_score": 0.0-1.0,
  "fundamentals_score": 0.0-1.0,
  "project_quality_score": 0.0-1.0
}}

Provide your analysis now."""
    
    def _check_btc_regime(self) -> tuple[bool, str]:
        """Check BTC regime filter - suppress BUY if BTC RSI < threshold or in downtrend."""
        btc_filter = self.analysis_config.get("btc_rsi_filter", 35)
        
        try:
            btc_tech = self._market_data.get_technical_summary("BTC/USDT")
            if btc_tech:
                btc_rsi = btc_tech.get("rsi_14d", 50)
                btc_momentum = btc_tech.get("price_momentum", {}).get("7d", 0)
                
                if btc_rsi < btc_filter:
                    return True, f"BTC RSI {btc_rsi:.1f} below filter threshold {btc_filter}"
                
                if btc_momentum < -5:
                    return True, f"BTC in confirmed weekly downtrend ({btc_momentum:.1f}% 7d)"
        except Exception as e:
            logger.warning(f"BTC regime check failed: {e}")
        
        return False, ""
    
    def _get_technical_data(self, symbol: str) -> Dict[str, Any]:
        """Gather technical analysis data via CCXT."""
        tech = self._market_data.get_technical_summary(symbol)
        
        if not tech:
            return {}
        
        return {
            "current_price": tech.get("current_price", 0),
            "rsi_14d": tech.get("rsi_14d", 50),
            "rsi_4h": tech.get("rsi_4h", 50),
            "rsi_30d": tech.get("rsi_30d", 50),
            "momentum_7d": tech.get("price_momentum", {}).get("7d", 0),
            "momentum_30d": tech.get("price_momentum", {}).get("30d", 0),
            "volume_ratio": tech.get("volume_ma_ratio", 1.0),
            "macd_value": tech.get("macd", {}).get("value", 0),
            "macd_signal": tech.get("macd", {}).get("signal", 0),
            "macd_histogram": tech.get("macd", {}).get("histogram", 0),
            "bb_upper": tech.get("bollinger", {}).get("upper", 0),
            "bb_middle": tech.get("bollinger", {}).get("middle", 0),
            "bb_lower": tech.get("bollinger", {}).get("lower", 0),
            "bb_position": tech.get("bollinger", {}).get("position", 0.5) * 100,
            "patterns": tech.get("patterns", {}),
        }
    
    def _get_fundamentals_data(self, symbol: str) -> Dict[str, Any]:
        """Gather on-chain and fundamental data."""
        try:
            url = f"https://api.coingecko.com/api/v3/coins/{symbol.lower()}"
            api_key = self.api_keys.get("coingecko")
            headers = {}
            if api_key:
                headers["x-cg-demo-api-key"] = api_key
            
            response = requests.get(url, headers=headers, timeout=15)
            if response.status_code == 200:
                data = response.json()
                return {
                    "market_cap": data.get("market_data", {}).get("market_cap", {}).get("usd", 0),
                    "circulating_supply": data.get("market_data", {}).get("circulating_supply", 0),
                    "max_supply": data.get("market_data", {}).get("max_supply", 0),
                    "fdv_mc_ratio": data.get("market_data", {}).get("fdv_to_market_cap", 1.0),
                    "team": data.get("links", {}).get("team", []),
                    "country": data.get("links", {}).get("country_origin", "Unknown"),
                    "github_commits": self._get_github_activity(symbol),
                    "audit_info": data.get("security", {}),
                }
        except Exception as e:
            logger.warning(f"Fundamentals fetch failed for {symbol}: {e}")
        
        return {}
    
    def _get_github_activity(self, symbol: str) -> int:
        """Get GitHub commit activity."""
        return 0
    
    def _get_sentiment_data(self, symbol: str) -> Dict[str, Any]:
        """Gather sentiment data from news and social sources."""
        return {
            "news_mentions": 0,
            "social_trend": "neutral",
            "reddit_trend": 1.0,
        }
    
    def _build_prompt(self, symbol: str) -> str:
        """Build analysis prompt with gathered data."""
        tech_data = self._get_technical_data(symbol)
        fund_data = self._get_fundamentals_data(symbol)
        sent_data = self._get_sentiment_data(symbol)
        
        format_data = {
            "symbol": symbol,
            "current_price": f"{tech_data.get('current_price', 0):.4f}",
            "rsi_14d": f"{tech_data.get('rsi_14d', 50):.1f}",
            "rsi_30d": f"{tech_data.get('rsi_30d', 50):.1f}",
            "macd_value": f"{tech_data.get('macd_value', 0):.6f}",
            "macd_signal": f"{tech_data.get('macd_signal', 0):.6f}",
            "macd_histogram": f"{tech_data.get('macd_histogram', 0):.6f}",
            "bb_upper": f"{tech_data.get('bb_upper', 0):.4f}",
            "bb_middle": f"{tech_data.get('bb_middle', 0):.4f}",
            "bb_lower": f"{tech_data.get('bb_lower', 0):.4f}",
            "bb_position": f"{tech_data.get('bb_position', 50):.1f}",
            "momentum_7d": f"{tech_data.get('momentum_7d', 0):.1f}",
            "momentum_30d": f"{tech_data.get('momentum_30d', 0):.1f}",
            "volume_ratio": f"{tech_data.get('volume_ratio', 1.0):.2f}",
            "patterns": str(tech_data.get("patterns", {})),
            "news_mentions": sent_data.get("news_mentions", 0),
            "social_trend": sent_data.get("social_trend", "neutral"),
            "reddit_trend": f"{sent_data.get('reddit_trend', 1.0):.2f}",
            "market_cap": fund_data.get("market_cap", 0),
            "circulating_supply": fund_data.get("circulating_supply", 0),
            "max_supply": fund_data.get("max_supply", 0),
            "fdv_mc_ratio": f"{fund_data.get('fdv_mc_ratio', 1.0):.2f}",
            "team_status": "Known" if fund_data.get("team") else "Anonymous",
            "audit_status": "Audited" if fund_data.get("audit_info") else "Not Audited",
            "github_commits": fund_data.get("github_commits", 0),
            "top_wallets_pct": 0,
            "unlock_schedule": "Unknown",
            "competitive_landscape": "Unknown",
            "funding_rate": "N/A",
            "active_addresses_trend": "Unknown",
            "netflow_trend": "Unknown",
            "tvl": "N/A",
        }
        
        try:
            return self._prompt_template.format(**format_data)
        except KeyError as e:
            logger.warning(f"Template formatting error: {e}, using default")
            return self._get_default_template().format(symbol=symbol)
    
    def _extract_json(self, output: str) -> Optional[dict]:
        json_patterns = [
            r'\{[^{}]*"symbol"\s*:\s*"[^"]+_[^"]*\}',
            r'```(?:json)?\s*(\{.*?\})\s*```',
            r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}',
        ]
        
        for pattern in json_patterns:
            matches = re.findall(pattern, output, re.DOTALL)
            for match in matches:
                try:
                    data = json.loads(match)
                    if "symbol" in data and "signal" in data:
                        return data
                except json.JSONDecodeError:
                    continue
        
        try:
            start_idx = output.find("{")
            end_idx = output.rfind("}") + 1
            if start_idx >= 0 and end_idx > start_idx:
                json_str = output[start_idx:end_idx]
                data = json.loads(json_str)
                if "symbol" in data:
                    return data
        except (json.JSONDecodeError, ValueError):
            pass
        
        return None
    
    def _call_direct_llm(self, symbol: str, prompt: str) -> Optional[dict]:
        model = self.analysis_config.get("model", "openrouter/stepfun/step-3.5-flash:free")
        
        if "openrouter" in model.lower():
            return self._call_openrouter(symbol, prompt, model)
        elif "anthropic" in model.lower() or "claude" in model.lower():
            return self._call_anthropic(symbol, prompt, model)
        elif "openai" in model.lower() or "gpt" in model.lower():
            return self._call_openai(symbol, prompt, model)
        else:
            return self._call_openrouter(symbol, prompt, model)
    
    def _call_openrouter(self, symbol: str, prompt: str, model: str) -> Optional[dict]:
        try:
            api_key = os.getenv("OPENROUTER_API_KEY")
            if not api_key:
                logger.error("OPENROUTER_API_KEY not set")
                return None
            
            model_name = model.split("/")[-1] if "/" in model else model
            
            response = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model_name,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 2048,
                },
                timeout=120,
            )
            
            if response.status_code != 200:
                logger.error(f"OpenRouter API error: {response.status_code} - {response.text}")
                return None
            
            data = response.json()
            output = data["choices"][0]["message"]["content"]
            return self._extract_json(output)
            
        except Exception as e:
            logger.error(f"OpenRouter call failed for {symbol}: {e}")
            return None
    
    def _call_anthropic(self, symbol: str, prompt: str, model: str) -> Optional[dict]:
        try:
            import anthropic
            
            api_key = os.getenv("ANTHROPIC_API_KEY")
            if not api_key:
                logger.error("ANTHROPIC_API_KEY not set")
                return None
            
            model_name = model.split("/")[-1] if "/" in model else "claude-opus-4-5"
            
            client = anthropic.Anthropic()
            
            response = client.messages.create(
                model=model_name,
                max_tokens=2048,
                messages=[{"role": "user", "content": prompt}]
            )
            
            output = response.content[0].text
            return self._extract_json(output)
            
        except Exception as e:
            logger.error(f"Anthropic call failed for {symbol}: {e}")
            return None
    
    def _call_openai(self, symbol: str, prompt: str, model: str) -> Optional[dict]:
        try:
            import openai
            
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                logger.error("OPENAI_API_KEY not set")
                return None
            
            model_name = model.split("/")[-1] if "/" in model else "gpt-4o"
            
            client = openai.OpenAI(api_key=api_key)
            
            response = client.chat.completions.create(
                model=model_name,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=2048,
            )
            
            output = response.choices[0].message.content
            return self._extract_json(output)
            
        except Exception as e:
            logger.error(f"OpenAI call failed for {symbol}: {e}")
            return None
    
    def _validate_signal(self, signal: dict) -> bool:
        required_fields = ["symbol", "signal", "confidence"]
        
        for field in required_fields:
            if field not in signal:
                return False
        
        if signal.get("confidence", 0) < self.min_confidence:
            logger.info(f"Signal for {signal.get('symbol')} below confidence threshold")
            return False
        
        return True
    
    def _calculate_composite_confidence(self, signal: dict) -> float:
        """Calculate composite confidence from component scores."""
        tech_score = signal.get("technical_score", 0.5)
        sent_score = signal.get("sentiment_score", 0.5)
        fund_score = signal.get("fundamentals_score", 0.5)
        proj_score = signal.get("project_quality_score", 0.5)
        
        composite = (
            tech_score * self.weights.get("technical", 0.25) +
            sent_score * self.weights.get("sentiment", 0.25) +
            fund_score * self.weights.get("fundamentals", 0.30) +
            proj_score * self.weights.get("project_quality", 0.20)
        )
        
        return composite
    
    def _save_signal(self, signal: dict) -> None:
        from .logger import get_data_dir
        
        signals_dir = get_data_dir() / "signals"
        signals_dir.mkdir(parents=True, exist_ok=True)
        
        date_str = datetime.now().strftime("%Y-%m-%d")
        symbol = signal.get("symbol", "UNKNOWN")
        output_path = signals_dir / f"{symbol}_{date_str}.json"
        
        with open(output_path, "w") as f:
            json.dump(signal, f, indent=2)
        
        logger.info(f"Saved signal for {symbol} to {output_path}")
    
    def analyze_ticker(self, symbol: str) -> Optional[dict]:
        logger.info(f"Analyzing crypto: {symbol}")
        
        btc_blocked, btc_reason = self._check_btc_regime()
        if btc_blocked:
            logger.info(f"BTC regime filter active: {btc_reason} - analysis suppressed")
        
        prompt = self._build_prompt(symbol)
        signal = self._call_direct_llm(symbol, prompt)
        
        if not signal:
            logger.error(f"No signal generated for {symbol}")
            return None
        
        signal["symbol"] = symbol.upper()
        signal["analyzed_at"] = datetime.now().isoformat()
        
        if "confidence" not in signal:
            signal["confidence"] = self._calculate_composite_confidence(signal)
        
        if btc_blocked and signal.get("signal", "").upper() == "BUY":
            logger.info(f"Suppressing BUY for {symbol} due to BTC regime filter")
            signal["signal"] = "HOLD"
            signal["suppression_reason"] = btc_reason
        
        if not self._validate_signal(signal):
            logger.warning(f"Signal validation failed for {symbol}")
            return None
        
        self._save_signal(signal)
        logger.info(f"Signal generated for {symbol}: {signal.get('signal')} "
                   f"(confidence: {signal.get('confidence'):.2f}, "
                   f"holding: {signal.get('suggested_holding_period', 'N/A')})")
        
        return signal
    
    def analyze_batch(self, symbols: List[str]) -> List[dict]:
        logger.info(f"Starting batch analysis for {len(symbols)} crypto symbols")
        
        signals = []
        timeout = self.analysis_config.get("timeout_minutes", 30) * 60
        start_time = time.time()
        
        for symbol in symbols:
            if time.time() - start_time > timeout:
                logger.warning("Analysis timeout reached, stopping batch")
                break
            
            try:
                signal = self.analyze_ticker(symbol)
                if signal:
                    signals.append(signal)
                
                time.sleep(2)
                
            except Exception as e:
                logger.error(f"Failed to analyze {symbol}: {e}")
                continue
        
        logger.info(f"Batch analysis complete: {len(signals)} signals generated")
        return signals


StockAnalyzer = CryptoAnalyzer
