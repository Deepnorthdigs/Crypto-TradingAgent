# Autonomous Trading CLI

Interactive CLI for managing the autonomous trading system.

## Usage

### From TradingAgents CLI

```bash
# Start the autonomous trading CLI
tradingagents autonomous

# Or via Python
python -m cli.autonomous
```

### Commands

| Command | Description |
|---------|-------------|
| `start` | Start the autonomous trading scheduler |
| `stop` | Stop the autonomous trading scheduler |
| `status` | Show system status and queue statistics |
| `queue status` | Quick queue statistics |
| `queue list` | List all pending signals |
| `queue clear` | Clear all pending signals (confirmation required) |
| `research` | Manually trigger research phase |
| `execute` | Manually trigger execution phase |
| `positions` | Show current Alpaca positions |
| `config` | Show current configuration |
| `config key=value` | Update configuration |
| `dashboard` | Show comprehensive dashboard |
| `help` | Show help message |
| `quit` / `exit` | Exit the CLI |

## Examples

```bash
# Start the scheduler
autonomous> start

# Check status
autonomous> status

# Trigger research
autonomous> research

# View queued signals
autonomous> queue list

# Execute trades
autonomous> execute

# View positions
autonomous> positions

# Update config
autonomous> config dry_run=false
autonomous> config min_confidence=0.70

# Show dashboard
autonomous> dashboard

# Stop and exit
autonomous> stop
autonomous> quit
```

## Configuration

Configuration is loaded from `config.yaml` in the project root under the `autonomous_trader` section:

```yaml
autonomous_trader:
  enabled: false
  mode: scheduler
  research_time: "18:00"
  execution_check_interval: 15
  market_hours_only: true
  max_signals_per_day: 10
  dry_run: true
  signal_expiry_days: 2
  auto_queue_signals: true
  min_confidence: 0.65
  max_per_sector: 0.20
```

## Environment Variables

Override config with environment variables:

```bash
export HERMES_AUTO_DRY_RUN=false
export HERMES_AUTO_RESEARCH_TIME="17:00"
export HERMES_AUTO_MARKET_HOURS_ONLY=true
```

## Architecture

The CLI integrates with:

- `autonomous_trader/src/queue.py` - Trade signal queue management
- `autonomous_trader/src/scheduler.py` - Market-aware scheduler
- `autonomous_trader/src/researcher.py` - Research agent (screen + analyze + queue)
- `autonomous_trader/src/executor.py` - Alpaca trade execution

## Auto-Start

To auto-start the scheduler when the CLI launches, set in config:

```yaml
autonomous_trader:
  enabled: true
```

## Testing

```bash
# Test the CLI loads correctly
python -c "from cli.autonomous import AutonomousCLI; cli = AutonomousCLI(); print('OK')"
```
