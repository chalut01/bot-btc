import logging
from . import config
from .http import get_session

logger = logging.getLogger("btc-bot")


class TelegramClient:
    def __init__(self):
        self.token = config.TG_BOT_TOKEN
        self.chat_id = config.TG_CHAT_ID
        self._session = get_session()

    def enabled(self) -> bool:
        return bool(self.token) and bool(self.chat_id)

    def send(self, text: str):
        if not self.enabled():
            return
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        payload = {"chat_id": self.chat_id, "text": text}
        try:
            r = self._session.post(url, json=payload, timeout=10)
            r.raise_for_status()
        except Exception as exc:
            logger.exception("Failed to send Telegram message")
