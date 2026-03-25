# Autonomous Trading System

A fully autonomous stock trading system that screens stocks, analyzes them with TradingAgents, queues trade signals, and executes trades via Alpaca paper trading API.

This project extends [TradingAgents](https://github.com/TauricResearch/TradingAgents) with automation capabilities for fully autonomous operation.

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

### Prerequisites

- Python 3.13+
- [Alpaca paper trading account](https://alpaca.markets/) (free)
- API keys for at least one LLM provider

### Setup

1. **Clone the repository:**
```bash
git clone https://github.com/Deepnorthdigs/Autonomous-TradingAgents.git
cd Autonomous-TradingAgents
```

2. **Create and activate a virtual environment:**
```bash
conda create -n autonomous-trading python=3.13
conda activate autonomous-trading
```

3. **Install base dependencies:**
```bash
pip install .
```

4. **Install autonomous trading dependencies:**
```bash
pip install -r autonomous_trader/requirements.txt
```

5. **Configure API keys:**

Create a `.env` file or set environment variables:
```bash
# LLM Provider (required) - Default uses OpenRouter with free model
export OPENROUTER_API_KEY=sk-or-v1-...

# Alternative providers
export OPENAI_API_KEY=sk-...
export GOOGLE_API_KEY=...
export ANTHROPIC_API_KEY=...

# Alpaca Paper Trading (required for live execution)
export ALPACA_PAPER_KEY=your-paper-api-key
export ALPACA_PAPER_SECRET=your-paper-api-secret
```

Or edit `autonomous_trader/config.yaml` directly:
```yaml
alpaca:
  key: "your-paper-api-key"
  secret: "your-paper-api-secret"
  url: "https://paper-api.alpaca.markets"

analysis:
  model: "openrouter/stepfun/step-3.5-flash:free"  # Default: free OpenRouter model
```

## Usage

### Interactive CLI

```bash
python -m cli.autonomous
```

### Command Examples

```bash
autonomous> start              # Start scheduler
autonomous> research          # Run research phase
autonomous> queue list        # View signals
autonomous> execute           # Execute trades
autonomous> config dry_run=false  # Enable live trading
autonomous> dashboard        # Full status view
```

### Standalone Scripts

```bash
# Research phase only (screens stocks, analyzes, queues signals)
python autonomous_trader/scripts/research.py

# Execution phase only (executes queued signals)
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

Environment variable overrides (prefix with `HERMES_AUTO_`):
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
│   ├── executor.py         # Alpaca trade execution
│   ├── risk.py             # Risk management checks
│   ├── portfolio.py        # Position tracking
│   ├── monitor.py          # Performance logging
│   ├── scheduler.py         # Market-aware scheduler
│   └── researcher.py        # Research agent
├── scripts/
│   ├── research.py          # Research phase script
│   ├── execute.py           # Execution phase script
│   ├── scheduler.py         # Master orchestrator
│   └── run_daily.py         # Daily workflow
├── templates/
│   └── analysis_prompt.md   # Prompt template
├── data/                    # Signal persistence (created at runtime)
├── logs/                    # Log files (created at runtime)
└── tests/                   # Unit tests (39 passing)
```

## Testing

```bash
cd autonomous_trader
python -m pytest tests/ -v
```

## Credits and Acknowledgments

This project is built upon and extends [TradingAgents](https://github.com/TauricResearch/TradingAgents) by [Tauric Research](https://tauric.ai/).

### TradingAgents Citation

If you use TradingAgents in your research, please cite:

```
@misc{xiao2025tradingagentsmultiagentsllmfinancial,
      title={TradingAgents: Multi-Agents LLM Financial Trading Framework}, 
      author={Yijia Xiao and Edward Sun and Di Luo and Wei Wang},
      year={2025},
      eprint={2412.20138},
      archivePrefix={arXiv},
      primaryClass={q-fin.TR},
      url={https://arxiv.org/abs/2412.20138}, 
}
```

### Technologies Used

- [TradingAgents](https://github.com/TauricResearch/TradingAgents) - Multi-agent LLM trading framework
- [yfinance](https://github.com/ranaroussi/yfinance) - Yahoo Finance data
- [Alpaca](https://alpaca.markets/) - Commission-free stock trading API
- [LangGraph](https://langchain-ai.github.io/langgraph/) - Agent orchestration
- [Typer](https://typer.tiangolo.com/) - CLI framework
- [Rich](https://rich.readthedocs.io/) - Terminal formatting

## Disclaimer

> This software is for educational and research purposes. Trading involves substantial risk of loss. Past performance does not guarantee future results. The autonomous trading system is experimental and not intended as financial advice. Always use paper trading to test strategies before using real capital.
