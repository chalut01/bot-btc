import os
import logging
from logging.handlers import RotatingFileHandler
from . import config

def setup_logger():
    logger = logging.getLogger("btc-bot")
    logger.setLevel(getattr(logging, config.LOG_LEVEL, logging.INFO))

    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")

    # Avoid duplicate handlers on reload
    if logger.handlers:
        return logger

    ch = logging.StreamHandler()
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    if config.LOG_TO_FILE:
        log_dir = os.path.dirname(config.LOG_FILE) or "."
        try:
            os.makedirs(log_dir, exist_ok=True)
            fh = RotatingFileHandler(
                config.LOG_FILE,
                maxBytes=config.LOG_MAX_MB * 1024 * 1024,
                backupCount=config.LOG_BACKUP_COUNT,
                encoding="utf-8",
            )
            fh.setFormatter(formatter)
            logger.addHandler(fh)
        except PermissionError:
            # Fallback to a local ./data directory if the configured path is not writable (e.g. running locally
            # without /app mounted). Update config.LOG_FILE so other parts of the app use the same fallback.
            fallback_dir = os.path.join(os.getcwd(), "data")
            try:
                os.makedirs(fallback_dir, exist_ok=True)
                fallback_file = os.path.join(fallback_dir, os.path.basename(config.LOG_FILE))
                config.LOG_FILE = fallback_file
                fh = RotatingFileHandler(
                    config.LOG_FILE,
                    maxBytes=config.LOG_MAX_MB * 1024 * 1024,
                    backupCount=config.LOG_BACKUP_COUNT,
                    encoding="utf-8",
                )
                fh.setFormatter(formatter)
                logger.addHandler(fh)
                logger.warning(f"Log directory not writable, falling back to {config.LOG_FILE}")
            except Exception:
                # If even the fallback fails, continue without file logging but keep console logging.
                logger.exception("Failed to initialize file logger; continuing with console logger only")

    logger.info("Logger initialized")
    return logger
