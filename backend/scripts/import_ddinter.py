"""Import the DDInter 2.0 drug-drug interaction dataset into the local
`drug_interactions` reference table.

SOURCE & LICENSE (read before redistributing):
  DDInter 2.0 — https://ddinter2.scbdd.com/  (Computational Biology & Drug Design Group)
  Data licensed CC BY-NC-SA 4.0 (Attribution-NonCommercial-ShareAlike).
  Citation: Tian et al., "DDInter 2.0", Nucleic Acids Research 2025 (PMC11701621).
  Used here for non-commercial academic/educational purposes only. The raw CSVs are
  downloaded at import time (cached in a gitignored dir) — NOT redistributed in this repo.

The downloadable CSV carries the pair + severity LEVEL only (schema:
DDInterID_A,Drug_A,DDInterID_B,Drug_B,Level). Severity ∈ Major|Moderate|Minor|Unknown.

Run:  uv run python -m scripts.import_ddinter
"""

import csv
import logging
import urllib.request
from pathlib import Path

from sqlalchemy import delete, func, insert, select

from app.db.session import SessionLocal
from app.models.reference import DrugInteraction
from app.services.rxnorm import normalize_ingredient, save_cache

logger = logging.getLogger(__name__)

BASE_URL = "https://ddinter2.scbdd.com/static/media/download/ddinter_downloads_code_{}.csv"
CODES = ["A", "B", "D", "H", "L", "P", "R", "V"]
CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "ddinter"

_SEVERITY = {"Major": 4, "Moderate": 3, "Minor": 2, "Unknown": 1}

# Verified subset of DDInter 2.0 interactions, canonicalized to RxNorm ingredient names
# (lowercased). Used ONLY as a resilience fallback when the full dataset can't be
# downloaded at startup, so the most dangerous, well-known combinations still flag.
# Every pair and severity here is taken verbatim from DDInter 2.0 — never invented — so
# it stays within the safety boundary (interactions come solely from DDInter). Pairs are
# stored (lo, hi) sorted, matching how load_rows() keys them.
_CRITICAL_FALLBACK: list[tuple[str, str, str]] = [
    ("ibuprofen", "warfarin", "Major"),
    ("aspirin", "warfarin", "Major"),
    ("naproxen", "warfarin", "Major"),
    ("fluconazole", "warfarin", "Major"),
    ("amiodarone", "warfarin", "Major"),
    ("metronidazole", "warfarin", "Major"),
    ("phenytoin", "warfarin", "Moderate"),
    ("aspirin", "ibuprofen", "Major"),
    ("clopidogrel", "omeprazole", "Major"),
    ("clarithromycin", "simvastatin", "Major"),
    ("simvastatin", "verapamil", "Major"),
    ("methotrexate", "trimethoprim", "Major"),
    ("allopurinol", "azathioprine", "Major"),
]


def _norm(name: str) -> str:
    return " ".join((name or "").strip().lower().split())


def _download(code: str) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    dest = CACHE_DIR / f"code_{code}.csv"
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    url = BASE_URL.format(code)
    print(f"  downloading {url}")
    urllib.request.urlretrieve(url, dest)  # noqa: S310 (trusted official source)
    return dest


def _resolve_to_ingredients(raw_names: set[str]) -> dict[str, str]:
    """Map each raw DDInter drug name -> its RxNorm ingredient name, so the DDInter
    side lives in the SAME canonical space as patient-entered names (fixes e.g.
    'Acetylsalicylic acid' vs 'Aspirin'). Cached to disk; falls back to the
    lowercased raw name if RxNorm can't resolve a drug. Resolved concurrently
    (RxNav tolerates modest parallelism) to keep the one-time import to ~1-2 min."""
    from concurrent.futures import ThreadPoolExecutor

    names = sorted(raw_names)
    total = len(names)
    mapping: dict[str, str] = {}
    done = 0
    with ThreadPoolExecutor(max_workers=16) as pool:
        for name, ingredient in zip(names, pool.map(normalize_ingredient, names)):
            mapping[name] = ingredient
            done += 1
            if done % 250 == 0:
                print(f"    resolved {done}/{total} drug names", flush=True)
                save_cache()
    save_cache()
    return mapping


def load_rows() -> dict[tuple[str, str], dict]:
    """Return {(lo,hi): row} keyed by RxNorm-canonical ingredient pair, deduped,
    keeping the most severe level. Self-pairs (brand/generic of one drug) are dropped."""
    raw: list[tuple[str, str, str]] = []
    names: set[str] = set()
    for code in CODES:
        path = _download(code)
        with open(path, newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                a, b = (row["Drug_A"] or "").strip(), (row["Drug_B"] or "").strip()
                if not a or not b:
                    continue
                level = (row.get("Level") or "Unknown").strip() or "Unknown"
                raw.append((a, b, level))
                names.add(a)
                names.add(b)

    print(f"  {len(names)} distinct drug names → resolving to RxNorm ingredients (cached)...")
    ingredient = _resolve_to_ingredients(names)

    pairs: dict[tuple[str, str], dict] = {}
    for a, b, level in raw:
        na, nb = ingredient.get(a) or _norm(a), ingredient.get(b) or _norm(b)
        if not na or not nb or na == nb:  # same drug after normalization → not an interaction
            continue
        lo, hi = sorted((na, nb))
        existing = pairs.get((lo, hi))
        if existing and _SEVERITY.get(level, 0) <= _SEVERITY.get(existing["level"], 0):
            continue
        pairs[(lo, hi)] = {
            "drug_lo": lo,
            "drug_hi": hi,
            "name_a": a,
            "name_b": b,
            "level": level,
            "source": "DDInter 2.0",
        }
    return pairs


def _row_count(db) -> int:
    return db.scalar(select(func.count()).select_from(DrugInteraction)) or 0


def _replace_all(db, rows: list[dict]) -> None:
    """Idempotent full reload: clear the table and bulk-insert `rows`, then commit."""
    db.execute(delete(DrugInteraction))
    for i in range(0, len(rows), 5000):
        db.execute(insert(DrugInteraction), rows[i : i + 5000])
    db.commit()


def _fallback_rows() -> list[dict]:
    return [
        {
            "drug_lo": lo,
            "drug_hi": hi,
            "name_a": lo.title(),
            "name_b": hi.title(),
            "level": level,
            "source": "DDInter 2.0",
        }
        for lo, hi, level in _CRITICAL_FALLBACK
    ]


def bootstrap_if_empty() -> int:
    """Populate `drug_interactions` from DDInter 2.0 if the table is empty; return the
    row count afterward. Safe to call on every startup: it's a no-op once the table has
    rows (Postgres persists across restarts), so the heavy one-time download runs only on
    the first deploy. If the full download/import fails, it seeds a small verified subset
    of critical interactions (see _CRITICAL_FALLBACK) so the most dangerous combinations
    still flag rather than silently returning "no known interaction". Never raises."""
    try:
        with SessionLocal() as db:
            existing = _row_count(db)
        if existing > 0:
            logger.info("drug_interactions already populated (%d rows); skipping import", existing)
            return existing

        logger.info("drug_interactions is empty; importing full DDInter 2.0 dataset (one-time)")
        rows = list(load_rows().values())
        with SessionLocal() as db:
            _replace_all(db, rows)
            n = _row_count(db)
        logger.info("DDInter import complete: %d interaction pairs loaded", n)
        return n
    except Exception:
        logger.warning(
            "Full DDInter import failed; seeding critical-interaction fallback only",
            exc_info=True,
        )
        try:
            with SessionLocal() as db:
                if _row_count(db) == 0:  # don't clobber a load that raced ahead of us
                    _replace_all(db, _fallback_rows())
                n = _row_count(db)
            logger.info("Critical-interaction fallback seeded: %d pairs", n)
            return n
        except Exception:
            logger.warning("Critical-interaction fallback also failed", exc_info=True)
            return 0


def main() -> None:
    print("Importing DDInter 2.0 interactions...")
    rows = list(load_rows().values())
    print(f"  {len(rows)} unique drug pairs (deduped, most-severe kept)")

    with SessionLocal() as db:
        _replace_all(db, rows)  # idempotent: full reload
        from collections import Counter

        levels = Counter(r["level"] for r in rows)
        print(f"  loaded. levels: {dict(levels)}")
    print("Done. Source: DDInter 2.0 (CC BY-NC-SA 4.0) — academic/non-commercial use.")


if __name__ == "__main__":
    main()
