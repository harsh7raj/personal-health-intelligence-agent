"""Medication intelligence — per-drug reference info + drug-drug interaction flags.

SAFETY BOUNDARY (do not weaken):
  - Interactions are surfaced ONLY from the local DDInter 2.0 table. No LLM, no
    model reasoning about pharmacology, ever.
  - A pair with no row is reported as "No known interaction found in DDInter 2.0" —
    explicitly NOT "safe to take together."
  - Every flag is framed as "discuss with your doctor or pharmacist," never as the
    system's own medical conclusion. A disclaimer accompanies all output.
"""

from itertools import combinations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.data.drug_reference import SOURCE_URL, get_reference
from app.models.clinical import Medication
from app.models.reference import DrugInteraction
from app.services.drug_reference_ai import ai_reference
from app.services.rxnorm import normalize_ingredient

DISCLAIMER = (
    "General reference information from public sources — not medical advice, and not "
    "specific to you. Interaction flags come only from the DDInter 2.0 database, not from "
    "the system's own judgement. Always discuss your medications and any possible "
    "interactions with your doctor or pharmacist before making any changes."
)

_INTERACTION_SOURCE = "DDInter 2.0 (https://ddinter2.scbdd.com/, CC BY-NC-SA 4.0)"
_REFERENCE_SOURCE_URL = SOURCE_URL
_SEVERITY_ORDER = {"Major": 0, "Moderate": 1, "Minor": 2, "Unknown": 3}


def build_medication_intelligence(db: Session, patient_id: int) -> dict:
    meds = list(
        db.scalars(
            select(Medication)
            .where(Medication.patient_id == patient_id, Medication.active.is_(True))
            .order_by(Medication.name)
        ).all()
    )

    med_items: list[dict] = []
    norm: dict[int, str] = {}
    for m in meds:
        ingredient = normalize_ingredient(m.name)
        norm[m.id] = ingredient
        # Curated MedlinePlus entry first; fall back to a labelled Groq reference
        # (Part 2) only for drugs not in the curated table. Never for interactions.
        reference = get_reference(ingredient) or ai_reference(ingredient)
        med_items.append(
            {
                "id": m.id,
                "name": m.name,
                "dose": m.dose,
                "normalized": ingredient,
                "reference": reference,
            }
        )

    interactions: list[dict] = []
    for a, b in combinations(meds, 2):
        na, nb = norm[a.id], norm[b.id]
        if na == nb:
            # Both resolve to the same RxNorm ingredient (e.g. Xanax + Alprazolam):
            # the same drug, not a flaggable interaction.
            interactions.append(
                {
                    "drug_a": a.name,
                    "drug_b": b.name,
                    "status": "same_drug",
                    "level": None,
                    "source": "RxNorm",
                    "note": "These resolve to the same medication (brand/generic) — not a separate interaction.",
                }
            )
            continue
        lo, hi = sorted((na, nb))
        row = db.scalar(
            select(DrugInteraction).where(
                DrugInteraction.drug_lo == lo, DrugInteraction.drug_hi == hi
            )
        )
        if row is not None:
            interactions.append(
                {
                    "drug_a": a.name,
                    "drug_b": b.name,
                    "status": "known",
                    "level": row.level,
                    "source": row.source,
                    "advice": "Discuss this combination with your doctor or pharmacist.",
                }
            )
        else:
            interactions.append(
                {
                    "drug_a": a.name,
                    "drug_b": b.name,
                    "status": "none_known",
                    "level": None,
                    "source": "DDInter 2.0",
                    "note": "No known interaction found in DDInter 2.0.",
                }
            )

    _status_rank = {"known": 0, "same_drug": 1, "none_known": 2}
    interactions.sort(
        key=lambda i: (_status_rank.get(i["status"], 3), _SEVERITY_ORDER.get(i.get("level"), 9))
    )
    known = [i for i in interactions if i["status"] == "known"]

    return {
        "medications": med_items,
        "interactions": interactions,
        "known_interaction_count": len(known),
        "pairs_checked": len(interactions),
        "disclaimer": DISCLAIMER,
        "interaction_source": _INTERACTION_SOURCE,
        "reference_source_url": _REFERENCE_SOURCE_URL,
    }
