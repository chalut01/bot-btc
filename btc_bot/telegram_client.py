import requests
from . import config

class TelegramClient:
    def __init__(self):
        self.token = config.TG_BOT_TOKEN
        self.chat_id = config.TG_CHAT_ID

    def enabled(self) -> bool:
        return bool(self.token) and bool(self.chat_id)

    def send(self, text: str):
        if not self.enabled():
            return
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        payload = {"chat_id": self.chat_id, "text": text}
        r = requests.post(url, json=payload, timeout=10)
        r.raise_for_status()
