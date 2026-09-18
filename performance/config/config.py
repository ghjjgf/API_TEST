"""系统级配置。"""

from __future__ import annotations

DEFAULT_HOST = "175.168.12.43"
# DEFAULT_HOST = "127.0.0.1"
DETECT_HOST = "175.168.13.72"
PORT_COMP = 3154   # 比对 (Search / Compare / Repo / Entity)
PORT_PARSE = 3156  # 解析 (Detect / Rec)
DEFAULT_BASE_URL = f"http://{DEFAULT_HOST}:{PORT_COMP}/x-api/v1"
DEFAULT_DETECT_URL = f"http://{DETECT_HOST}:{PORT_PARSE}/x-api/v1"
