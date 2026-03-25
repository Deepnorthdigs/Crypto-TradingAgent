import json
import logging
import os
import re
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import requests


logger = logging.getLogger("autonomous_trader")


class StockAnalyzer:
    def __init__(self, config: dict):
        self.config = config
        self.analysis_config = config.get("analysis", {})
        self.min_confidence = config.get("trading", {}).get("min_confidence", 0.65)
        self._prompt_template = self._load_prompt_template()
    
    def _load_prompt_template(self) -> str:
        template_path = self.analysis_config.get("prompt_template", "templates/analysis_prompt.md")
        project_root = Path(__file__).parent.parent
        full_path = project_root / template_path.lstrip("/")
        
        if full_path.exists() and full_path.is_file():
            with open(full_path, "r") as f:
                return f.read()
        
        return self._get_default_template()
    
    def _get_default_template(self) -> str:
        return """Analyze the stock {ticker} and provide a trading recommendation.

You are a professional financial analyst. Analyze the provided stock data and return a JSON object with your analysis.

Return ONLY valid JSON (no markdown, no explanation), with this exact structure:
{{
  "ticker": "{ticker}",
  "company_name": "Company Name",
  "sector": "Sector Name",
  "recommendation": "BUY|HOLD|SELL",
  "confidence": 0.75,
  "target_price": 150.00,
  "stop_loss": 130.00,
  "position_size_pct": 0.05,
  "investment_thesis": "Brief explanation",
  "key_metrics": {{"pe": 22, "roe": 0.15, "debt_equity": 0.5}},
  "strengths": ["Strength 1", "Strength 2"],
  "risks": ["Risk 1", "Risk 2"]
}}

Consider:
- Current market conditions
- Company fundamentals (P/E, ROE, revenue growth, debt)
- Technical trends
- Risk/reward ratio

Provide your analysis now."""
    
    def _build_prompt(self, ticker: str) -> str:
        return self._prompt_template.format(ticker=ticker)
    
    def _extract_json(self, output: str) -> Optional[dict]:
        json_patterns = [
            r'\{[^{}]*"ticker"\s*:\s*"[^"]+_[^"]*\}',
            r'```(?:json)?\s*(\{.*?\})\s*```',
            r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}',
        ]
        
        for pattern in json_patterns:
            matches = re.findall(pattern, output, re.DOTALL)
            for match in matches:
                try:
                    data = json.loads(match)
                    if "ticker" in data and "recommendation" in data:
                        return data
                except json.JSONDecodeError:
                    continue
        
        try:
            start_idx = output.find("{")
            end_idx = output.rfind("}") + 1
            if start_idx >= 0 and end_idx > start_idx:
                json_str = output[start_idx:end_idx]
                data = json.loads(json_str)
                if "ticker" in data:
                    return data
        except (json.JSONDecodeError, ValueError):
            pass
        
        return None
    
    def _call_tradingagents(self, ticker: str, prompt: str) -> Optional[dict]:
        try:
            from tradingagents.graph.trading_graph import TradingAgentsGraph
            from tradingagents.default_config import DEFAULT_CONFIG
            
            config = DEFAULT_CONFIG.copy()
            
            analysis_config = self.analysis_config
            model = analysis_config.get("model", "anthropic/claude-opus-4-5")
            
            if "/" in model:
                provider, model_name = model.split("/", 1)
                config["llm_provider"] = provider
                if "claude" in model.lower():
                    config["deep_think_llm"] = model
                    config["quick_think_llm"] = model
                elif "gpt" in model.lower():
                    config["deep_think_llm"] = model
                    config["quick_think_llm"] = model
                elif "gemini" in model.lower():
                    config["deep_think_llm"] = model
                    config["quick_think_llm"] = model
            
            graph = TradingAgentsGraph(debug=False, config=config)
            
            trade_date = datetime.now().strftime("%Y-%m-%d")
            _, decision = graph.propagate(ticker, trade_date)
            
            return self._parse_tradingagents_decision(ticker, decision)
            
        except ImportError:
            logger.warning("TradingAgents not available, using direct LLM call")
            return self._call_direct_llm(ticker, prompt)
        except Exception as e:
            logger.error(f"TradingAgents analysis failed for {ticker}: {e}")
            return self._call_direct_llm(ticker, prompt)
    
    def _call_direct_llm(self, ticker: str, prompt: str) -> Optional[dict]:
        try:
            import anthropic
            
            api_key = os.getenv("ANTHROPIC_API_KEY")
            if not api_key:
                logger.error("ANTHROPIC_API_KEY not set")
                return None
            
            client = anthropic.Anthropic()
            
            response = client.messages.create(
                model="claude-opus-4-5",
                max_tokens=2048,
                messages=[{"role": "user", "content": prompt}]
            )
            
            output = response.content[0].text
            return self._extract_json(output)
            
        except Exception as e:
            logger.error(f"Direct LLM call failed for {ticker}: {e}")
            return None
    
    def _parse_tradingagents_decision(self, ticker: str, decision: str) -> dict:
        output = decision if isinstance(decision, str) else str(decision)
        extracted = self._extract_json(output)
        
        if extracted:
            return extracted
        
        recommendation = "HOLD"
        confidence = 0.5
        
        decision_lower = output.lower()
        if "buy" in decision_lower and "strong" in decision_lower:
            recommendation = "BUY"
            confidence = 0.75
        elif "buy" in decision_lower:
            recommendation = "BUY"
            confidence = 0.65
        elif "sell" in decision_lower:
            recommendation = "SELL"
            confidence = 0.65
        
        return {
            "ticker": ticker,
            "company_name": "",
            "sector": "",
            "recommendation": recommendation,
            "confidence": confidence,
            "target_price": 0.0,
            "stop_loss": 0.0,
            "position_size_pct": 0.05,
            "investment_thesis": output[:500],
            "key_metrics": {},
            "strengths": [],
            "risks": [],
            "raw_decision": decision
        }
    
    def _validate_signal(self, signal: dict) -> bool:
        required_fields = ["ticker", "recommendation", "confidence"]
        
        for field in required_fields:
            if field not in signal:
                return False
        
        if signal.get("confidence", 0) < self.min_confidence:
            logger.info(f"Signal for {signal.get('ticker')} below confidence threshold")
            return False
        
        return True
    
    def _save_signal(self, signal: dict) -> None:
        from .logger import get_data_dir
        
        signals_dir = get_data_dir() / "signals"
        signals_dir.mkdir(parents=True, exist_ok=True)
        
        date_str = datetime.now().strftime("%Y-%m-%d")
        ticker = signal.get("ticker", "UNKNOWN")
        output_path = signals_dir / f"{ticker}_{date_str}.json"
        
        with open(output_path, "w") as f:
            json.dump(signal, f, indent=2)
        
        logger.info(f"Saved signal for {ticker} to {output_path}")
    
    def analyze_ticker(self, ticker: str) -> Optional[dict]:
        logger.info(f"Analyzing ticker: {ticker}")
        
        prompt = self._build_prompt(ticker)
        signal = self._call_tradingagents(ticker, prompt)
        
        if not signal:
            logger.error(f"No signal generated for {ticker}")
            return None
        
        signal["ticker"] = ticker.upper()
        signal["analyzed_at"] = datetime.now().isoformat()
        
        if not self._validate_signal(signal):
            logger.warning(f"Signal validation failed for {ticker}")
            return None
        
        self._save_signal(signal)
        logger.info(f"Signal generated for {ticker}: {signal.get('recommendation')} (confidence: {signal.get('confidence')})")
        
        return signal
    
    def analyze_batch(self, tickers: list) -> list:
        logger.info(f"Starting batch analysis for {len(tickers)} tickers")
        
        signals = []
        timeout = self.analysis_config.get("timeout_minutes", 30) * 60
        start_time = time.time()
        
        for ticker in tickers:
            if time.time() - start_time > timeout:
                logger.warning("Analysis timeout reached, stopping batch")
                break
            
            try:
                signal = self.analyze_ticker(ticker)
                if signal:
                    signals.append(signal)
                
                time.sleep(2)
                
            except Exception as e:
                logger.error(f"Failed to analyze {ticker}: {e}")
                continue
        
        logger.info(f"Batch analysis complete: {len(signals)} signals generated")
        return signals
