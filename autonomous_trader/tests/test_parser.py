import pytest
import json
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestJsonExtraction:
    def test_extract_json_from_plain_json(self):
        from src.analyzer import StockAnalyzer
        
        config = {
            "analysis": {"model": "test", "prompt_template": ""},
            "trading": {"min_confidence": 0.65},
        }
        analyzer = StockAnalyzer(config)
        
        output = '{"ticker": "AAPL", "recommendation": "BUY", "confidence": 0.75}'
        result = analyzer._extract_json(output)
        
        assert result is not None
        assert result["ticker"] == "AAPL"
        assert result["recommendation"] == "BUY"
    
    def test_extract_json_from_markdown(self):
        from src.analyzer import StockAnalyzer
        
        config = {
            "analysis": {"model": "test", "prompt_template": ""},
            "trading": {"min_confidence": 0.65},
        }
        analyzer = StockAnalyzer(config)
        
        output = '''
        ```json
        {"ticker": "MSFT", "recommendation": "HOLD", "confidence": 0.70}
        ```
        '''
        result = analyzer._extract_json(output)
        
        assert result is not None
        assert result["ticker"] == "MSFT"
    
    def test_extract_json_with_nested_objects(self):
        from src.analyzer import StockAnalyzer
        
        config = {
            "analysis": {"model": "test", "prompt_template": ""},
            "trading": {"min_confidence": 0.65},
        }
        analyzer = StockAnalyzer(config)
        
        output = '''
        {
          "ticker": "GOOGL",
          "recommendation": "BUY",
          "confidence": 0.80,
          "key_metrics": {"pe": 25, "roe": 0.20}
        }
        '''
        result = analyzer._extract_json(output)
        
        assert result is not None
        assert result["ticker"] == "GOOGL"
        assert result["key_metrics"]["pe"] == 25


class TestSignalValidation:
    def test_validate_signal_passes(self):
        from src.analyzer import StockAnalyzer
        
        config = {
            "analysis": {"model": "test", "prompt_template": ""},
            "trading": {"min_confidence": 0.65},
        }
        analyzer = StockAnalyzer(config)
        
        signal = {
            "ticker": "AAPL",
            "recommendation": "BUY",
            "confidence": 0.75,
        }
        
        assert analyzer._validate_signal(signal) is True
    
    def test_validate_signal_below_confidence(self):
        from src.analyzer import StockAnalyzer
        
        config = {
            "analysis": {"model": "test", "prompt_template": ""},
            "trading": {"min_confidence": 0.65},
        }
        analyzer = StockAnalyzer(config)
        
        signal = {
            "ticker": "AAPL",
            "recommendation": "BUY",
            "confidence": 0.50,
        }
        
        assert analyzer._validate_signal(signal) is False
    
    def test_validate_signal_missing_fields(self):
        from src.analyzer import StockAnalyzer
        
        config = {
            "analysis": {"model": "test", "prompt_template": ""},
            "trading": {"min_confidence": 0.65},
        }
        analyzer = StockAnalyzer(config)
        
        signal = {
            "ticker": "AAPL",
            "confidence": 0.75,
        }
        
        assert analyzer._validate_signal(signal) is False


class TestPromptBuilding:
    def test_build_prompt_with_template(self):
        from src.analyzer import StockAnalyzer
        
        config = {
            "analysis": {
                "model": "test",
                "prompt_template": "Analyze {ticker} stock."
            },
            "trading": {"min_confidence": 0.65},
        }
        analyzer = StockAnalyzer(config)
        
        prompt = analyzer._build_prompt("AAPL")
        
        assert "AAPL" in prompt
        assert "Analyze" in prompt


class TestDirectLLMCall:
    @patch("os.getenv")
    def test_call_direct_llm_no_api_key(self, mock_getenv):
        from src.analyzer import StockAnalyzer
        
        mock_getenv.return_value = None
        
        config = {
            "analysis": {"model": "test", "prompt_template": ""},
            "trading": {"min_confidence": 0.65},
        }
        analyzer = StockAnalyzer(config)
        
        result = analyzer._call_direct_llm("AAPL", "Analyze this stock")
        
        assert result is None
