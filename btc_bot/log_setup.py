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
        os.makedirs(os.path.dirname(config.LOG_FILE), exist_ok=True)
        fh = RotatingFileHandler(
            config.LOG_FILE,
            maxBytes=config.LOG_MAX_MB * 1024 * 1024,
            backupCount=config.LOG_BACKUP_COUNT,
            encoding="utf-8",
        )
        fh.setFormatter(formatter)
        logger.addHandler(fh)

    logger.info("Logger initialized")
    return logger
