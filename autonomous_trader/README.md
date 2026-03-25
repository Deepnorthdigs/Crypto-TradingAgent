# Autonomous Trading System

A fully autonomous stock trading system that screens stocks, analyzes them with TradingAgents, queues trade signals, and executes trades via Alpaca paper trading API.

## Features

### Core Components

| Module | Description |
|--------|-------------|
| **Screener** | Stock screening using yfinance with customizable filters (market cap, volume, sector, price range) |
| **Analyzer** | Integration with TradingAgents for deep stock analysis |
| **Queue** | Signal queue with persistence, deduplication, and expiry management |
| **Executor** | Alpaca API integration with bracket orders (entry, take-profit, stop-loss) |
| **Risk Manager** | Position sizing, sector concentration, and max position limits |
| **Portfolio Tracker** | Real-time position tracking with sector exposure monitoring |
| **Monitor** | Performance logging, metrics calculation, and alerts |
| **Scheduler** | Market-hours-aware scheduler for research and execution phases |

### Key Capabilities

- **Automated Research Phase**: Screens stocks, runs TradingAgents analysis, queues actionable signals
- **Queue-Based Execution**: Signals persist across sessions, expire after configurable days, deduplicate by ticker
- **Bracket Orders**: Each signal executes with take-profit and stop-loss automatically
- **Risk Management**: Per-position limits, sector concentration checks, max daily signals
- **Market Hours Only**: Respects trading hours (9:30 AM - 4:00 PM ET, weekdays)
- **Dry Run Mode**: Test without real trades
- **Discord Alerts**: Optional webhook notifications for trades and errors
- **Configurable**: YAML config, environment variable overrides

### CLI Commands

```
start/stop         Control the scheduler
status             Show system status
queue status/list  Queue management
research           Trigger research phase
execute            Trigger execution phase
positions          View Alpaca positions
config             Show/update configuration
dashboard          Comprehensive status view
```

## Installation

1. Install TradingAgents dependencies:
```bash
pip install .
```

2. Install autonomous_trader dependencies:
```bash
pip install -r autonomous_trader/requirements.txt
```

3. Configure API keys in `config.yaml`:
```yaml
alpaca:
  key: "your-paper-api-key"
  secret: "your-paper-api-secret"
  url: "https://paper-api.alpaca.markets"
```

4. Set environment variables (optional):
```bash
export OPENAI_API_KEY=...
export ALPACA_PAPER_KEY=...
export ALPACA_PAPER_SECRET=...
```

## Usage

### Interactive CLI

```bash
python -m cli.autonomous
```

Or from the TradingAgents CLI:
```bash
tradingagents autonomous
```

### Command Examples

```bash
autonomous> start              # Start scheduler
autonomous> research            # Run research phase
autonomous> queue list          # View signals
autonomous> execute             # Execute trades
autonomous> config dry_run=false  # Enable live trading
autonomous> dashboard           # Full status view
```

### Standalone Scripts

```bash
# Research phase only
python autonomous_trader/scripts/research.py

# Execution phase only
python autonomous_trader/scripts/execute.py

# Full scheduler (research + execution loop)
python autonomous_trader/scripts/scheduler.py
```

## Configuration

Edit `autonomous_trader/config.yaml`:

```yaml
alpaca:
  key: "..."
  secret: "..."
  url: "https://paper-api.alpaca.markets"

screener:
  min_market_cap: 500_000_000
  min_volume: 500_000
  excluded_sectors: ["Financial Services", "Real Estate"]
  max_results: 10
  top_n: 5

trading:
  dry_run: true
  max_position_value: 1000
  max_position_pct: 0.02
  max_per_sector: 0.20
  stop_loss_pct: 0.05
  take_profit_pct: 0.15
  max_signals_per_day: 10
  signal_expiry_days: 2

research:
  research_time: "18:00"
  min_confidence: 0.65
  auto_queue_signals: true

execution:
  market_hours_only: true
  execution_check_interval: 15
  delay_after_open: 5
  notify_on_trade: true
  notify_on_error: true
  discord_webhook: ""

logging:
  level: "INFO"
  log_dir: "autonomous_trader/logs"
```

Environment variable overrides:
```bash
export HERMES_AUTO_DRY_RUN=false
export HERMES_AUTO_RESEARCH_TIME="17:00"
export HERMES_AUTO_MIN_CONFIDENCE=0.70
```

## Architecture

```
autonomous_trader/
├── config.yaml              # Configuration
├── src/
│   ├── logger.py           # Logging setup
│   ├── screener.py         # Stock screening (yfinance)
│   ├── analyzer.py         # TradingAgents integration
│   ├── queue.py            # Signal queue with persistence
│   ├── executor.py          # Alpaca trade execution
│   ├── risk.py             # Risk management checks
│   ├── portfolio.py        # Position tracking
│   ├── monitor.py          # Performance logging
│   ├── scheduler.py        # Market-aware scheduler
│   └── researcher.py       # Research agent
├── scripts/
│   ├── research.py         # Research phase script
│   ├── execute.py          # Execution phase script
│   ├── scheduler.py        # Master orchestrator
│   └── run_daily.py        # Daily workflow
├── templates/
│   └── analysis_prompt.md  # Prompt template
├── data/
│   └── queue/             # Signal persistence
└── tests/                  # Unit tests (39 passing)
```

## Testing

```bash
cd autonomous_trader
python -m pytest tests/ -v
```

## Disclaimer

> This software is for educational and research purposes. Trading involves substantial risk of loss. Past performance does not guarantee future results. The autonomous trading system is experimental and not intended as financial advice.
