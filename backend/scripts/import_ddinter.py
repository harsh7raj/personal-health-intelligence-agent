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
import urllib.request
from pathlib import Path

from sqlalchemy import delete, insert

from app.db.session import SessionLocal
from app.models.reference import DrugInteraction
from app.services.rxnorm import normalize_ingredient, save_cache

BASE_URL = "https://ddinter2.scbdd.com/static/media/download/ddinter_downloads_code_{}.csv"
CODES = ["A", "B", "D", "H", "L", "P", "R", "V"]
CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "ddinter"

_SEVERITY = {"Major": 4, "Moderate": 3, "Minor": 2, "Unknown": 1}


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


def main() -> None:
    print("Importing DDInter 2.0 interactions...")
    pairs = load_rows()
    rows = list(pairs.values())
    print(f"  {len(rows)} unique drug pairs (deduped, most-severe kept)")

    with SessionLocal() as db:
        db.execute(delete(DrugInteraction))  # idempotent: full reload
        for i in range(0, len(rows), 5000):
            db.execute(insert(DrugInteraction), rows[i : i + 5000])
        db.commit()
        from collections import Counter

        levels = Counter(r["level"] for r in rows)
        print(f"  loaded. levels: {dict(levels)}")
    print("Done. Source: DDInter 2.0 (CC BY-NC-SA 4.0) — academic/non-commercial use.")


if __name__ == "__main__":
    main()
