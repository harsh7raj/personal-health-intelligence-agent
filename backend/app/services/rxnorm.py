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
import re
import urllib.parse
from pathlib import Path

from app.services import http

logger = logging.getLogger(__name__)

_BASE = "https://rxnav.nlm.nih.gov/REST"
_TIMEOUT = 4.0

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
        return http.get_json(url, timeout=_TIMEOUT)
    except http.NotFound:
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


# Strengths and forms written after a name ("Thyronorm 75", "Shelcal 500 tablet").
_STRENGTH = re.compile(r"\s+(\d[\d.,/]*\s*(mg|mcg|µg|g|iu|ml|%)?|tablets?|tabs?|capsules?|caps?|syrup|xr|sr|er|od)\b.*$", re.I)


def lookup(name: str) -> dict:
    """All RxNorm ingredients for a medicine name (D35).

    {"status": "found", "ingredients": [...]} | {"status": "not_found", "ingredients": []} |
    {"status": "offline", "ingredients": []}. A combination product returns every ingredient.
    Indian brands are usually not_found: the caller then asks for a confirmed AI suggestion."""
    key = _norm(name)
    if not key:
        return {"status": "not_found", "ingredients": []}
    if key in _BRAND_ALIASES:
        return {"status": "found", "ingredients": [_BRAND_ALIASES[key]]}
    cached = _cache.get(f"ing:{key}")
    if cached is not None:
        return {"status": "found" if cached else "not_found", "ingredients": [i for i in cached.split("|") if i]}
    for candidate in dict.fromkeys([key, _STRENGTH.sub("", key).strip()]):
        if not candidate:
            continue
        data = _get_json(f"{_BASE}/rxcui.json?name={urllib.parse.quote(candidate)}&search=2")
        if data is None:
            return {"status": "offline", "ingredients": []}
        rxcuis = (data.get("idGroup") or {}).get("rxnormId") or []
        if not rxcuis:
            continue
        rel = _get_json(f"{_BASE}/rxcui/{rxcuis[0]}/related.json?tty=IN")
        if rel is None:
            return {"status": "offline", "ingredients": []}
        names = [
            _norm(p["name"])
            for g in ((rel.get("relatedGroup") or {}).get("conceptGroup") or [])
            for p in (g.get("conceptProperties") or []) if p.get("name")
        ]
        if names:
            ingredients = sorted(dict.fromkeys(names))
            _cache[f"ing:{key}"] = "|".join(ingredients)
            return {"status": "found", "ingredients": ingredients}
    _cache[f"ing:{key}"] = ""
    return {"status": "not_found", "ingredients": []}
