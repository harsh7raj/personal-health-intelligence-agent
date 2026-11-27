"""The one place the backend calls public reference APIs (RxNav, RxClass, openFDA).
Tests stub `get_json`, so nothing in the suite can reach the network."""

import json
import logging
import ssl
import urllib.request

logger = logging.getLogger(__name__)

# certifi's CA bundle: the default trust store fails behind TLS-intercepting proxies.
try:
    import certifi

    _SSL_CTX: ssl.SSLContext | None = ssl.create_default_context(cafile=certifi.where())
except Exception:  # pragma: no cover - certifi should be installed
    _SSL_CTX = None
    logger.warning("certifi unavailable; falling back to default SSL trust store")


class NotFound(Exception):
    """The API answered 404: the thing doesn't exist (as opposed to being unreachable)."""


def get_json(url: str, timeout: float = 6.0) -> dict | None:
    """GET a JSON document. None if unreachable or invalid; raises NotFound on a 404."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "phia-local/2"})
        with urllib.request.urlopen(req, timeout=timeout, context=_SSL_CTX) as resp:  # noqa: S310
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise NotFound(url) from exc
        logger.warning("request failed (%s): %s", exc.code, url)
    except Exception:
        logger.warning("request failed: %s", url, exc_info=True)
    return None
