from __future__ import annotations

import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("MARKET_ECHO_DATA_DIR", BASE_DIR / ".data"))
DB_PATH = Path(os.getenv("MARKET_ECHO_DB_PATH", DATA_DIR / "market_echo_v1.db"))
DEFAULT_TIMEZONE = os.getenv("MARKET_ECHO_TZ", "Asia/Shanghai")

# V1 默认走 mock 联调，后续按数据源逐步替换。
DEFAULT_USE_MOCK = os.getenv("MARKET_ECHO_USE_MOCK", "true").lower() in {
    "1",
    "true",
    "yes",
}
