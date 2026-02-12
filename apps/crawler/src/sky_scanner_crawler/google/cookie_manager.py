"""Generate consent cookies for Google Flights requests."""

from __future__ import annotations

import base64
import datetime
import logging
import time

from .proto.cookies_pb2 import SOCS, Datetime, Information  # type: ignore

logger = logging.getLogger(__name__)


class CookieManager:
    """Generates CONSENT + SOCS cookies using protobuf to bypass consent gating."""

    @staticmethod
    def generate(*, locale: str = "en") -> dict[str, str]:
        """Return a dict of cookie name -> value."""
        info = Information()
        info.gws = f"gws_{datetime.datetime.now().strftime('%Y%m%d')}-0_RC2"
        info.locale = locale

        dt = Datetime()
        dt.timestamp = int(time.time())

        socs = SOCS(info=info, datetime=dt)
        socs_b64 = base64.b64encode(socs.SerializeToString()).decode("utf-8")

        return {
            "CONSENT": "PENDING+987",
            "SOCS": socs_b64,
        }
