CLI_CONFIG = {
    # Announcements
    "announcements_url": "https://api.tauric.ai/v1/announcements",
    "announcements_timeout": 1.0,
    "announcements_fallback": "[cyan]For more information, please visit[/cyan] [link=https://github.com/TauricResearch]https://github.com/TauricResearch[/link]",

    # Autonomous Trading
    "autonomous_trader": {
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
        "alpaca_key_env": "ALPACA_PAPER_KEY",
        "alpaca_secret_env": "ALPACA_PAPER_SECRET",
    },
}
