import logging
import sys
from typing import Callable

_subscribers: list[Callable[[str], None]] = []

def subscribe_logs(callback: Callable[[str], None]) -> Callable[[], None]:
    _subscribers.append(callback)
    def unsubscribe():
        if callback in _subscribers:
            _subscribers.remove(callback)
    return unsubscribe

class WsLogHandler(logging.Handler):
    def emit(self, record):
        try:
            msg = self.format(record)
            for sub in _subscribers:
                sub(msg)
        except Exception:
            self.handleError(record)

class WsPrintInterceptor:
    def __init__(self, original):
        self.original = original

    def write(self, message):
        self.original.write(message)
        msg = message.strip()
        if msg:
            for sub in _subscribers:
                sub(msg)

    def flush(self):
        self.original.flush()

def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    ws_handler = WsLogHandler()
    ws_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    logging.getLogger().addHandler(ws_handler)
    
    sys.stdout = WsPrintInterceptor(sys.stdout)
    sys.stderr = WsPrintInterceptor(sys.stderr)
