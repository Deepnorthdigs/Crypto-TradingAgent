import logging
import logging.handlers
import os
import yaml
from datetime import datetime
from pathlib import Path
from typing import Optional


def setup_logging(config: dict) -> logging.Logger:
    log_config = config.get("logging", {})
    level = getattr(logging, log_config.get("level", "INFO").upper())
    
    logger = logging.getLogger("autonomous_trader")
    logger.setLevel(level)
    
    if logger.handlers:
        logger.handlers.clear()
    
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    log_file = log_config.get("log_file", "logs/trading_agent.log")
    log_dir = Path(log_file).parent
    log_dir.mkdir(parents=True, exist_ok=True)
    
    file_handler = logging.handlers.TimedRotatingFileHandler(
        log_file,
        when="midnight",
        interval=1,
        backupCount=30
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    
    return logger


def load_config(config_path: str = "config.yaml") -> dict:
    project_root = Path(__file__).parent.parent
    config_file = project_root / config_path
    
    if not config_file.exists():
        raise FileNotFoundError(f"Config file not found: {config_file}")
    
    with open(config_file, "r") as f:
        config = yaml.safe_load(f)
    
    env_file = project_root / ".env"
    if env_file.exists():
        from dotenv import load_dotenv
        load_dotenv(env_file)
    
    if config.get("alpaca"):
        config["alpaca"]["paper_key"] = os.getenv("ALPACA_PAPER_KEY", config["alpaca"].get("paper_key", ""))
        config["alpaca"]["paper_secret"] = os.getenv("ALPACA_PAPER_SECRET", config["alpaca"].get("paper_secret", ""))
    
    if config.get("alerts"):
        config["alerts"]["discord_webhook"] = os.getenv("DISCORD_WEBHOOK", config["alerts"].get("discord_webhook", ""))
    
    return config


def get_data_dir() -> Path:
    project_root = Path(__file__).parent.parent
    data_dir = project_root / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def get_log_dir() -> Path:
    project_root = Path(__file__).parent.parent
    log_dir = project_root / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir
