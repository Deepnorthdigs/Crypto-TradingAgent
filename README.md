# Autonomous Crypto Trading System

An autonomous cryptocurrency swing/position trading system that discovers trending altcoins, performs deep multi-layer analysis, and executes trades via Bybit.

## Overview

This forked project adapts the original autonomous trading system from **stock trading** to **crypto swing trading** with the following key characteristics:

- **Trading Style**: Swing/Position trading (1 week to 2 month holding periods)
- **Target Assets**: Altcoins (not just majors) with market cap >$10M
- **Exchange**: Bybit (testnet for paper trading)
- **Market**: Spot trading only (no leverage, no futures)

## Key Features

### Discovery & Screening
- Multi-source coin discovery: CoinGecko, CoinMarketCap, CryptoPanic
- 7-day and 30-day momentum scoring
- Volume growth detection (7d MA vs 30d MA)
- Trust score filtering (skip coins with score < 3)
- Token unlock screening (>5% circulating supply = automatic skip)
- 15-30 minute API response caching

### Multi-Layer Analysis
- **Technical Analysis** (25% weight): RSI, MACD, Bollinger Bands on 4h and 1D timeframes
- **Sentiment Analysis** (25% weight): 7-14 day news and social trends
- **Fundamentals** (30% weight): Market cap, supply metrics, on-chain data
- **Project Quality** (20% weight): Team, audits, GitHub activity, competitive landscape

### BTC Regime Filter
- BUY signals automatically suppressed if BTC RSI < 35
- BUY signals suppressed during confirmed BTC weekly downtrends

### Execution & Risk Management
- Manual bracket orders (entry + 2 take-profits + stop-loss)
- Partial take-profit: 50% at TP1 (25%), 50% at TP2 (50%)
- Stop loss: 8% (wider for swing trading)
- Slippage tolerance check (skip if spread > 1% for small caps)
- Quiet hours gate (2am-5am UTC) for new entries only
- 60-minute execution check interval

### Category Concentration Limits
- Max 30% in DeFi
- Max 30% in L1s
- Max 30% in L2s
- Max 20% in memecoins (configurable)
- Max 6 open positions

### Monitoring & Alerts
- Holding period tracking (alert at 45 days, max 60 days)
- Discord webhook alerts for:
  - Take profit triggers
  - Holding period warnings
  - Trade executions
  - Stop loss hits

## Architecture

```
autonomous_trader/
├── config.yaml              # All configuration
├── src/
│   ├── screener.py         # Crypto coin discovery (CoinGecko/CoinMarketCap)
│   ├── market_data.py      # CCXT/Bybit data fetching + TA indicators
│   ├── analyzer.py         # LLM-powered crypto analysis
│   ├── executor.py         # CCXT/Bybit trade execution
│   ├── risk.py             # Category concentration, holding limits
│   ├── queue.py            # Signal queue with crypto-specific fields
│   ├── monitor.py          # Performance logging, alerts
│   ├── portfolio.py        # Position tracking
│   ├── scheduler.py        # Market-aware scheduler
│   ├── researcher.py        # Research pipeline orchestration
│   └── logger.py           # Logging setup
├── templates/
│   └── crypto_analysis_prompt.md  # LLM analysis prompt
├── scripts/
│   ├── research.py         # Research phase (screening + analysis)
│   ├── execute.py          # Execution phase
│   └── scheduler.py        # Full scheduler loop
└── tests/                  # Unit tests (42 passing)
```

## Installation

### Prerequisites
- Python 3.11+
- Bybit testnet account (free)
- LLM API key (OpenRouter recommended, free tier available)

### API Keys Required

| Service | Purpose | Required | Get Key At |
|---------|---------|----------|------------|
| **OpenRouter** | LLM analysis | Yes | [openrouter.ai](https://openrouter.ai/) |
| **CoinGecko** | Market data | Free tier | [coingecko.com](https://www.coingecko.com/) |
| **Bybit** | Trading execution | Yes (testnet) | [bybit-testnet](https://testnet.bybit.com/) |

### Setup

```bash
# Clone and enter directory
git clone https://github.com/YOUR_USERNAME/Autonomous-TradingAgents.git
cd Autonomous-TradingAgents

# Create virtual environment
conda create -n crypto-trading python=3.11
conda activate crypto-trading

# Install dependencies
pip install -r autonomous_trader/requirements.txt

# Configure API keys
cp .env.example .env
```

Edit `.env` with your API keys:
```bash
# LLM Analysis (required)
OPENROUTER_API_KEY=sk-or-v1-...

# Bybit Testnet (required for trading)
BYBIT_API_KEY=your_testnet_key
BYBIT_API_SECRET=your_testnet_secret
```

Or edit `autonomous_trader/config.yaml`:
```yaml
exchange:
  name: "bybit"
  testnet: true
  api_key: ""
  api_secret: ""

api_keys:
  coingecko: ""  # Optional for higher rate limits
```

## Configuration

Edit `autonomous_trader/config.yaml`:

```yaml
# Exchange
exchange:
  name: "bybit"
  testnet: true  # Paper trading first!

# Screening
screener:
  min_market_cap: 10_000_000   # $10M minimum
  min_age_days: 14             # At least 2 weeks old
  momentum_window_days: 7       # 7d momentum as primary filter

# Analysis weights
analysis:
  weights:
    technical: 0.25
    sentiment: 0.25
    fundamentals: 0.30
    project_quality: 0.20
  btc_rsi_filter: 35           # Suppress BUY if BTC RSI < 35

# Trading parameters
trading:
  dry_run: true                  # Start with paper trading
  max_positions: 6               # Fewer positions for swing trading
  position_size_pct: 0.05        # 5% per position
  stop_loss_pct: 0.08            # 8% stop loss
  take_profit_pct_1: 0.25       # First TP at 25%
  take_profit_pct_2: 0.50        # Second TP at 50%
  quiet_hours_start: "02:00"     # UTC
  quiet_hours_end: "05:00"

# Risk limits
risk:
  max_holding_days: 60           # Exit by day 60
  holding_alert_days: 45         # Alert at day 45
  max_defi_exposure_pct: 0.30
  max_l1_exposure_pct: 0.30
  max_l2_exposure_pct: 0.30
  max_memecoin_exposure_pct: 0.20

# Execution
execution:
  signal_expiry_days: 7          # Signals valid 1 week
  check_interval_minutes: 60      # Not high frequency

# Discord alerts
alerts:
  enabled: true
  discord_webhook: "https://discord.com/api/webhooks/..."
  notify_on: ["trade_executed", "position_closed", "stop_loss_hit", "holding_alert", "take_profit_1"]
```

## Usage

### Interactive CLI
```bash
python -m cli.autonomous
```

### Standalone Scripts

```bash
# Research phase only (screen + analyze + queue)
python autonomous_trader/scripts/research.py

# Execution phase only (execute queued signals)
python autonomous_trader/scripts/execute.py

# Full scheduler (runs research + execution on schedule)
python autonomous_trader/scripts/scheduler.py
```

### Command Examples
```
autonomous> start              # Start scheduler
autonomous> research          # Run research phase
autonomous> queue list        # View signals
autonomous> execute          # Execute trades
autonomous> positions        # View open positions
autonomous> config dry_run=false  # Enable live trading
autonomous> dashboard        # Full status view
```

## Testing

```bash
cd autonomous_trader
python -m pytest tests/ -v
```

Current test suite: **42 passing tests**

## Swing Trading Parameters

This system is designed for **swing trading**, not scalping or day trading:

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Holding Period | 1 week - 2 months | Short timeframes too expensive with trading fees |
| Stop Loss | 8% | Wider than day trading to avoid volatility shakes |
| Take Profit 1 | 25% | Partial exit for risk management |
| Take Profit 2 | 50% | Full exit target |
| Max Positions | 6 | Focus on conviction, not quantity |
| Execution Interval | 60 min | Not high frequency |
| Signal Expiry | 7 days | Longer than stocks due to holding period |

## Risk Warnings

> **IMPORTANT**: This is a high-risk experimental system.

- Cryptocurrencies are highly volatile
- Swing trading with multi-week holds exposes capital to drawdowns
- Past performance does not guarantee future results
- Always start with **paper trading** (dry_run: true)
- Never invest more than you can afford to lose
- Token unlocks can cause sudden price drops
- Rug pulls and scams are common in altcoin space

## Project Structure

This project is forked from [TradingAgents](https://github.com/TauricResearch/TradingAgents) and adapted for cryptocurrency swing trading. The original project used:
- Alpaca API for US stock trading
- yfinance for market data
- US market hours scheduling

This fork replaces these with:
- CCXT/Bybit for crypto trading
- CoinGecko/CoinMarketCap for market data
- 24/7 crypto market operation

## Technologies Used

- [CCXT](https://github.com/ccxt/ccxt) - Crypto exchange integration
- [Bybit](https://www.bybit.com/) - Spot trading exchange
- [CoinGecko](https://www.coingecko.com/) - Cryptocurrency data
- [Pandas](https://pandas.pydata.org/) - Data analysis
- [TA-Lib/TA](https://github.com/mrjbq7/ta-lib) - Technical indicators
- [LangGraph](https://langchain-ai.github.io/langgraph/) - Agent orchestration
- [Rich](https://rich.readthedocs.io/) - Terminal formatting

## Disclaimer

> This software is for educational and research purposes only. Cryptocurrency trading involves substantial risk of loss, including the potential for total loss of investment. The autonomous trading system is experimental and not intended as financial advice. Features like stopping at 45 days, max holding period of 60 days, and category concentration limits are risk management tools but do not guarantee profits or prevent losses. Always use paper trading to test strategies before using real capital. The cryptocurrency market operates 24/7 and is highly volatile compared to traditional markets.
