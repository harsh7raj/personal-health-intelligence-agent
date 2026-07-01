"""RxNorm (RxNav) drug-name normalization — live, free, NLM-maintained.
Maps a free-text medication name to its RxNorm ingredient so it can be matched
against the DDInter interaction table. Network-resilient: any failure/timeout
degrades to the lowercased raw name (the feature must never hang or 500 on this).

NOTE: this is name normalization ONLY. The discontinued RxNav *Drug Interaction*
API is NOT used — interactions come solely from the local DDInter table.
Endpoint: https://rxnav.nlm.nih.gov/REST/  (no API key required)
"""

import json
import logging
import ssl
import urllib.parse
import urllib.request
from pathlib import Path

logger = logging.getLogger(__name__)

_BASE = "https://rxnav.nlm.nih.gov/REST"
_TIMEOUT = 4.0

# Use the certifi CA bundle for TLS verification. Python's default trust store can
# fail on machines behind a TLS-intercepting proxy ("self-signed certificate in
# certificate chain"), which silently degraded EVERY name to its raw form and broke
# both same-drug detection and interaction matching. certifi gives a portable bundle.
try:
    import certifi

    _SSL_CTX: ssl.SSLContext | None = ssl.create_default_context(cafile=certifi.where())
except Exception:  # pragma: no cover - certifi should be installed
    _SSL_CTX = None
    logger.warning("certifi unavailable; falling back to default SSL trust store")

# Common brand -> RxNorm ingredient aliases, applied BEFORE any network call so the
# most common brand/generic pairs canonicalize even when RxNav is unreachable. Keeps
# the safety feature robust offline; the live RxNorm lookup still covers everything else.
_BRAND_ALIASES: dict[str, str] = {
    "xanax": "alprazolam",
    "coumadin": "warfarin",
    "advil": "ibuprofen",
    "motrin": "ibuprofen",
    "tylenol": "acetaminophen",
    "lipitor": "atorvastatin",
    "zocor": "simvastatin",
    "norvasc": "amlodipine",
    "prinivil": "lisinopril",
    "zestril": "lisinopril",
    "cozaar": "losartan",
    "glucophage": "metformin",
    "synthroid": "levothyroxine",
    "prilosec": "omeprazole",
    "lopressor": "metoprolol",
    "toprol": "metoprolol",
    "ecotrin": "aspirin",
    "bayer aspirin": "aspirin",
    "acetylsalicylic acid": "aspirin",
}

# Persistent name->ingredient cache (gitignored). Populated en masse by the DDInter
# import; warmed at process start so med-intel lookups for known drugs need no network.
_CACHE_FILE = Path(__file__).resolve().parent.parent.parent / "data" / "ddinter" / "rxnorm_cache.json"
_cache: dict[str, str] = {}


def _load_cache() -> None:
    try:
        if _CACHE_FILE.exists():
            _cache.update(json.loads(_CACHE_FILE.read_text(encoding="utf-8")))
    except Exception:
        logger.warning("could not load RxNorm cache", exc_info=True)


def save_cache() -> None:
    try:
        _CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        _CACHE_FILE.write_text(json.dumps(_cache, sort_keys=True), encoding="utf-8")
    except Exception:
        logger.warning("could not save RxNorm cache", exc_info=True)


_load_cache()


def _norm(name: str) -> str:
    return " ".join((name or "").strip().lower().split())


def _get_json(url: str) -> dict | None:
    try:
        with urllib.request.urlopen(  # noqa: S310 (fixed NLM host)
            url, timeout=_TIMEOUT, context=_SSL_CTX
        ) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        logger.warning("RxNorm request failed: %s", url, exc_info=True)
        return None


def normalize_ingredient(name: str) -> str:
    """Return the RxNorm ingredient name (lowercased) for `name`, or the lowercased
    raw name if RxNorm can't resolve it / is unreachable. Cached per process."""
    key = _norm(name)
    if not key:
        return key
    if key in _cache:
        return _cache[key]
    if key in _BRAND_ALIASES:
        result = _BRAND_ALIASES[key]
        _cache[key] = result
        return result

    result = key  # fallback
    q = urllib.parse.quote(key)
    data = _get_json(f"{_BASE}/rxcui.json?name={q}&search=2")
    rxcuis = ((data or {}).get("idGroup") or {}).get("rxnormId") or []
    if rxcuis:
        rel = _get_json(f"{_BASE}/rxcui/{rxcuis[0]}/related.json?tty=IN")
        groups = ((rel or {}).get("relatedGroup") or {}).get("conceptGroup") or []
        for g in groups:
            props = g.get("conceptProperties") or []
            if props and props[0].get("name"):
                result = _norm(props[0]["name"])
                break

    _cache[key] = result
    return result
