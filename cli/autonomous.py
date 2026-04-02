"""
Autonomous Trading CLI Commands
Interactive shell for managing the autonomous trading system.
"""

import os
import sys
import yaml
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Tuple
import subprocess
import shlex

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.markdown import Markdown

console = Console()


AUTONOMOUS_CONFIG = {
    "enabled": False,
    "mode": "scheduler",
    "research_time": "18:00",
    "execution_check_interval": 15,
    "market_hours_only": True,
    "max_signals_per_day": 10,
    "dry_run": True,
    "queue_file": "autonomous_trader/data/queue/pending.json",
    "log_dir": "autonomous_trader/logs",
    "notify_on_trade": True,
    "notify_on_error": True,
    "discord_webhook": "",
    "delay_after_open": 5,
    "signal_expiry_days": 2,
    "auto_queue_signals": True,
    "min_confidence": 0.65,
    "max_per_sector": 0.20,
    "model": "openrouter/stepfun/step-3.5-flash:free",
    "alpaca_key": "",
    "alpaca_secret": "",
    "alpaca_url": "https://paper-api.alpaca.markets",
}


def get_config() -> Dict:
    """Load merged config from files and environment."""
    config = AUTONOMOUS_CONFIG.copy()
    
    config_paths = [
        Path("autonomous_trader/config.yaml"),
        Path("config.yaml"),
    ]
    
    for config_path in config_paths:
        if config_path.exists():
            try:
                with open(config_path) as f:
                    file_config = yaml.safe_load(f) or {}
                    
                    at_config = file_config.get("autonomous_trader", {})
                    if at_config:
                        config.update(at_config)
                    
                    if "analysis" in file_config:
                        config["model"] = file_config["analysis"].get("model", config["model"])
                    
                    if "alpaca" in file_config:
                        config["alpaca_key"] = file_config["alpaca"].get("paper_key", "")
                        config["alpaca_secret"] = file_config["alpaca"].get("paper_secret", "")
                        config["alpaca_url"] = file_config["alpaca"].get("base_url", config["alpaca_url"])
                    
                    if "trading" in file_config:
                        config["dry_run"] = file_config["trading"].get("dry_run", config["dry_run"])
                        config["min_confidence"] = file_config["trading"].get("min_confidence", config["min_confidence"])
                    
                    if "execution" in file_config:
                        config["market_hours_only"] = file_config["execution"].get("run_during_market_hours_only", config["market_hours_only"])
                        config["signal_expiry_days"] = file_config["execution"].get("signal_expiry_days", config["signal_expiry_days"])
                    
                    if "alerts" in file_config:
                        config["discord_webhook"] = file_config["alerts"].get("discord_webhook", "")
                        config["notify_on_trade"] = "trade_executed" in file_config["alerts"].get("notify_on", [])
                    
                    break
            except Exception as e:
                print(f"Warning: Failed to load config from {config_path}: {e}")
    
    for key in list(config.keys()):
        env_key = f"HERMES_AUTO_{key.upper()}"
        if env_key in os.environ:
            value = os.environ[env_key]
            if value.lower() in ("true", "false"):
                config[key] = value.lower() == "true"
            elif value.replace(".", "").isdigit():
                config[key] = float(value) if "." in value else int(value)
            else:
                config[key] = value
    
    for key in ["ALPACA_PAPER_KEY", "ALPACA_KEY"]:
        if key in os.environ:
            config["alpaca_key"] = os.environ[key]
    
    for key in ["ALPACA_PAPER_SECRET", "ALPACA_SECRET"]:
        if key in os.environ:
            config["alpaca_secret"] = os.environ[key]
    
    for key in ["OPENROUTER_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY"]:
        if key in os.environ:
            config[f"env_{key}"] = os.environ[key]
    
    return config


def save_config(config: Dict) -> None:
    """Save config to file."""
    config_path = Path("autonomous_trader/config.yaml")
    config_path.parent.mkdir(parents=True, exist_ok=True)
    
    if config_path.exists():
        try:
            with open(config_path) as f:
                file_config = yaml.safe_load(f) or {}
        except Exception:
            file_config = {}
    else:
        file_config = {}
    
    flat_keys = {
        "enabled", "mode", "research_time", "execution_check_interval",
        "market_hours_only", "max_signals_per_day", "dry_run", "notify_on_trade",
        "notify_on_error", "discord_webhook", "delay_after_open", "signal_expiry_days",
        "auto_queue_signals", "min_confidence", "max_per_sector", "model",
        "alpaca_key", "alpaca_secret", "alpaca_url"
    }
    
    new_at_config = {k: v for k, v in config.items() if k in flat_keys}
    
    existing_keys = {
        "alpaca", "screening", "analysis", "trading", "risk", "execution",
        "research", "queue", "phases", "schedule", "logging", "alerts"
    }
    
    for key in existing_keys:
        if key in file_config and key not in ("alpaca", "analysis", "trading", "execution", "alerts"):
            new_at_config[key] = file_config[key]
    
    if "alpaca" in file_config:
        file_config["alpaca"]["paper_key"] = config.get("alpaca_key", "")
        file_config["alpaca"]["paper_secret"] = config.get("alpaca_secret", "")
        file_config["alpaca"]["base_url"] = config.get("alpaca_url", "https://paper-api.alpaca.markets")
    else:
        file_config["alpaca"] = {
            "paper_key": config.get("alpaca_key", ""),
            "paper_secret": config.get("alpaca_secret", ""),
            "base_url": config.get("alpaca_url", "https://paper-api.alpaca.markets")
        }
    
    if "analysis" in file_config:
        file_config["analysis"]["model"] = config.get("model", "openrouter/stepfun/step-3.5-flash:free")
    
    file_config["autonomous_trader"] = new_at_config
    
    with open(config_path, "w") as f:
        yaml.dump(file_config, f, default_flow_style=False, sort_keys=False)


def is_market_open() -> bool:
    """Check if market is currently open."""
    try:
        import pytz
        eastern = pytz.timezone("America/New_York")
        now = datetime.now(eastern)
        
        if now.weekday() >= 5:
            return False
        
        market_open = datetime.strptime("09:30", "%H:%M").time()
        market_close = datetime.strptime("16:00", "%H:%M").time()
        
        return market_open <= now.time() <= market_close
    except ImportError:
        return True


class AutonomousCLI:
    """Interactive CLI for autonomous trading."""
    
    def __init__(self):
        self.config = get_config()
        self.scheduler_process = None
        self.running = False
    
    def print(self, message: str, style: str = ""):
        """Print message with optional style."""
        if style:
            console.print(message, style=style)
        else:
            console.print(message)
    
    def run_command(self, cmd: str) -> bool:
        """Process a command and return whether to continue."""
        parts = cmd.strip().split()
        if not parts:
            return True
        
        command = parts[0].lower()
        args = parts[1:] if len(parts) > 1 else []
        
        handlers = {
            "help": self._cmd_help,
            "status": self._cmd_status,
            "start": self._cmd_start,
            "stop": self._cmd_stop,
            "queue": self._cmd_queue,
            "research": self._cmd_research,
            "execute": self._cmd_execute,
            "positions": self._cmd_positions,
            "config": self._cmd_config,
            "dashboard": self._cmd_dashboard,
            "quit": self._cmd_quit,
            "exit": self._cmd_quit,
        }
        
        if command in handlers:
            return handlers[command](args)
        else:
            self.print(f"Unknown command: {command}. Type 'help' for available commands.", style="red")
            return True
    
    def _cmd_help(self, args: List[str]) -> bool:
        """Show help message."""
        help_text = """
# Autonomous Trading Commands

**Control:**
- `start` - Start the autonomous trading scheduler
- `stop` - Stop the autonomous trading scheduler  
- `status` - Show current system status

**Queue Management:**
- `queue status` - Quick queue statistics
- `queue list` - List all pending signals
- `queue clear` - Clear all pending signals (confirmation required)

**Trading:**
- `research` - Manually trigger research phase
- `execute` - Manually trigger execution phase
- `positions` - Show current Alpaca positions

**Configuration:**
- `config` - Show current configuration
- `config key=value` - Update configuration
- `dashboard` - Show comprehensive dashboard

**Other:**
- `help` - Show this help
- `quit` / `exit` - Exit the CLI
"""
        console.print(Markdown(help_text))
        return True
    
    def _cmd_status(self, args: List[str]) -> bool:
        """Show system status."""
        from autonomous_trader.src.queue import TradeQueue
        
        queue = TradeQueue(self.config)
        stats = queue.get_stats()
        
        table = Table(title="Autonomous Trading Status", show_header=True, header_style="bold cyan")
        table.add_column("Setting", style="dim")
        table.add_column("Value")
        
        table.add_row("Scheduler Running", "Yes" if self.running else "No")
        table.add_row("Mode", self.config.get("mode", "scheduler"))
        table.add_row("Dry Run", "Yes" if self.config.get("dry_run") else "No")
        table.add_row("Market Hours Only", "Yes" if self.config.get("market_hours_only") else "No")
        table.add_row("Market Open", "Yes" if is_market_open() else "No")
        
        console.print(table)
        
        queue_table = Table(title="Queue Statistics", show_header=True, header_style="bold cyan")
        queue_table.add_column("Metric", style="dim")
        queue_table.add_column("Value")
        
        queue_table.add_row("Total Pending", str(stats["total_pending"]))
        queue_table.add_row("Valid", str(stats["valid"]))
        queue_table.add_row("Expired", str(stats["expired"]))
        
        console.print(queue_table)
        
        if stats["by_ticker"]:
            ticker_table = Table(title="Tickers in Queue")
            ticker_table.add_column("Ticker", style="cyan")
            ticker_table.add_column("Count", justify="right")
            
            for ticker, count in sorted(stats["by_ticker"].items(), key=lambda x: x[1], reverse=True)[:10]:
                ticker_table.add_row(ticker, str(count))
            
            console.print(ticker_table)
        
        return True
    
    def _cmd_start(self, args: List[str]) -> bool:
        """Start the scheduler."""
        if self.running:
            self.print("Scheduler already running", style="yellow")
            return True
        
        try:
            from autonomous_trader.src.scheduler import start_scheduler
            
            self.scheduler = start_scheduler(self.config)
            self.running = True
            self.config["enabled"] = True
            save_config(self.config)
            
            self.print("Autonomous trading scheduler started", style="green")
            self.print("   Use 'status' to monitor, 'stop' to halt")
        except Exception as e:
            self.print(f"Failed to start scheduler: {e}", style="red")
            import traceback
            traceback.print_exc()
        
        return True
    
    def _cmd_stop(self, args: List[str]) -> bool:
        """Stop the scheduler."""
        if not self.running:
            self.print("No scheduler running", style="yellow")
            return True
        
        try:
            if hasattr(self, "scheduler"):
                self.scheduler.stop()
            self.running = False
            self.config["enabled"] = False
            save_config(self.config)
            
            self.print("Autonomous trading scheduler stopped", style="green")
        except Exception as e:
            self.print(f"Error stopping scheduler: {e}", style="red")
        
        return True
    
    def _cmd_queue(self, args: List[str]) -> bool:
        """Queue management commands."""
        from autonomous_trader.src.queue import TradeQueue
        
        subcmd = args[0].lower() if args else "status"
        queue = TradeQueue(self.config)
        
        if subcmd == "status":
            stats = queue.get_stats()
            self.print(f"Queue: {stats['valid']} valid / {stats['total_pending']} total / {stats['expired']} expired")
            
        elif subcmd == "list":
            pending = queue.get_pending()
            if not pending:
                self.print("Queue is empty")
                return True
            
            table = Table(title=f"Pending Signals ({len(pending)})")
            table.add_column("Ticker", style="cyan")
            table.add_column("Confidence", justify="right")
            table.add_column("Target", justify="right")
            table.add_column("Stop", justify="right")
            table.add_column("Age", justify="right")
            
            for sig in pending[:20]:
                table.add_row(
                    sig.ticker,
                    f"{sig.confidence:.0%}",
                    f"${sig.target_price:.2f}",
                    f"${sig.stop_loss:.2f}",
                    f"{sig.age_hours():.1f}h"
                )
            
            console.print(table)
            
            if len(pending) > 20:
                self.print(f"... and {len(pending) - 20} more signals")
        
        elif subcmd == "clear":
            pending = queue.get_pending()
            if not pending:
                self.print("Queue already empty")
                return True
            
            self.print(f"This will clear {len(pending)} signals. Type 'yes' to confirm:")
            confirm = input("> ")
            
            if confirm.lower() == "yes":
                queue._pending = []
                queue._save_queue()
                self.print(f"Cleared {len(pending)} signals from queue", style="green")
            else:
                self.print("Cancelled")
        
        else:
            self.print(f"Unknown queue command: {subcmd}. Use: status, list, clear")
        
        return True
    
    def _cmd_research(self, args: List[str]) -> bool:
        """Trigger research phase."""
        self.print("Running research phase...", style="cyan")
        self.print("   (This may take several minutes)")
        
        try:
            from autonomous_trader.src.researcher import ResearchAgent
            
            agent = ResearchAgent(self.config)
            signals = agent.run_research()
            
            self.print(f"Research complete: {len(signals)} signals queued", style="green")
            
            if signals:
                table = Table(title="Queued Signals")
                table.add_column("Ticker", style="cyan")
                table.add_column("Confidence", justify="right")
                table.add_column("Target", justify="right")
                
                for sig in signals[:10]:
                    table.add_row(sig.ticker, f"{sig.confidence:.0%}", f"${sig.target_price:.2f}")
                
                console.print(table)
                
                if len(signals) > 10:
                    self.print(f"... and {len(signals) - 10} more")
        
        except ImportError as e:
            self.print("Autonomous trader module not found", style="red")
            self.print("   Make sure you're in the project root directory")
            self.print(f"   Error: {e}")
        except Exception as e:
            self.print(f"Research failed: {e}", style="red")
            import traceback
            traceback.print_exc()
        
        return True
    
    def _cmd_execute(self, args: List[str]) -> bool:
        """Trigger execution phase."""
        if not is_market_open() and self.config.get("market_hours_only"):
            self.print("Market is closed", style="yellow")
            self.print("   Set market_hours_only=false to execute anyway")
            return True
        
        self.print("Running execution phase...", style="cyan")
        
        try:
            from autonomous_trader.src.scheduler import MarketScheduler
            
            scheduler = MarketScheduler(self.config)
            scheduler.run_execution_job()
            
            self.print("Execution cycle complete", style="green")
            
        except ImportError as e:
            self.print("Autonomous trader module not found", style="red")
            self.print("   Make sure you're in the project root directory")
        except Exception as e:
            self.print(f"Execution failed: {e}", style="red")
            import traceback
            traceback.print_exc()
        
        return True
    
    def _cmd_positions(self, args: List[str]) -> bool:
        """Show Alpaca positions."""
        try:
            import alpaca_trade_api as tradeapi
            
            api = tradeapi.REST(
                key=self.config.get("alpaca_key", os.getenv("ALPACA_PAPER_KEY", "")),
                secret=self.config.get("alpaca_secret", os.getenv("ALPACA_PAPER_SECRET", "")),
                base_url=self.config.get("alpaca_url", "https://paper-api.alpaca.markets")
            )
            
            positions = api.list_positions()
            
            if not positions:
                self.print("No open positions")
                return True
            
            table = Table(title="Current Positions")
            table.add_column("Symbol", style="cyan")
            table.add_column("Qty", justify="right")
            table.add_column("Avg Price", justify="right")
            table.add_column("Current", justify="right")
            table.add_column("Value", justify="right")
            table.add_column("P/L", justify="right")
            
            for pos in positions:
                qty = int(float(pos.qty))
                avg = float(pos.avg_entry_price)
                current = float(pos.current_price)
                value = float(pos.market_value)
                pl = float(pos.unrealized_pl)
                pl_pct = (current - avg) / avg * 100
                
                pl_style = "green" if pl >= 0 else "red"
                table.add_row(
                    pos.symbol,
                    str(qty),
                    f"${avg:.2f}",
                    f"${current:.2f}",
                    f"${value:.2f}",
                    f"${pl:+.2f} ({pl_pct:+.1f}%)",
                    style=pl_style
                )
            
            console.print(table)
            
        except ImportError:
            self.print("alpaca-trade-api not installed", style="red")
        except Exception as e:
            self.print(f"Failed to fetch positions: {e}", style="red")
        
        return True
    
    def _cmd_config(self, args: List[str]) -> bool:
        """Show or update configuration."""
        if not args:
            table = Table(title="Autonomous Trading Configuration")
            table.add_column("Setting", style="dim")
            table.add_column("Value")
            
            for key, value in sorted(self.config.items()):
                table.add_row(key, str(value))
            
            console.print(table)
            self.print("\nUse 'config key=value' to update settings")
            return True
        
        if "=" not in args[0]:
            self.print("Usage: config [key=value ...]", style="yellow")
            return True
        
        updates = {}
        for pair in args:
            if "=" in pair:
                key, value = pair.split("=", 1)
                if value.lower() in ("true", "false"):
                    value = value.lower() == "true"
                elif value.replace(".", "").isdigit():
                    value = float(value) if "." in value else int(value)
                updates[key] = value
        
        for key, value in updates.items():
            if key in self.config:
                self.config[key] = value
                self.print(f"Set {key} = {value}")
            else:
                self.print(f"Unknown setting: {key}", style="yellow")
        
        save_config(self.config)
        return True
    
    def _cmd_dashboard(self, args: List[str]) -> bool:
        """Show comprehensive dashboard."""
        self._cmd_status([])
        self.print("")
        self._cmd_queue(["list"])
        self.print("")
        self._cmd_positions([])
        return True
    
    def _cmd_quit(self, args: List[str]) -> bool:
        """Exit the CLI."""
        if self.running:
            self.print("Stopping scheduler before exit...")
            self._cmd_stop([])
        self.print("Goodbye!")
        return False
    
    def run(self):
        """Run the interactive CLI."""
        console.print(Panel.fit(
            "[bold cyan]Autonomous Trading CLI[/bold cyan]\n"
            "Type 'help' for commands, 'quit' to exit",
            border_style="cyan"
        ))
        
        if self.config.get("enabled") and not self.running:
            self.print("\nℹ️  Autonomous trading was previously enabled.")
            self.print("   Use 'start' to restart the scheduler\n")
        
        while True:
            try:
                cmd = input("autonomous> ").strip()
                if not cmd:
                    continue
                
                if not self.run_command(cmd):
                    break
                    
            except KeyboardInterrupt:
                self.print("\nUse 'quit' to exit")
            except EOFError:
                break
        
        if self.running:
            self._cmd_stop([])


def main():
    """Entry point for autonomous trading CLI."""
    from pathlib import Path
    
    project_root = Path(__file__).parent.parent.parent
    os.chdir(project_root)
    
    cli = AutonomousCLI()
    cli.run()


if __name__ == "__main__":
    main()
