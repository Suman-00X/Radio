"""Builds a SYNTHETIC gold set for a demo lab: dictations composed from known findings, so the right template and field values are known by construction rather than annotated by a radiologist.

Order: compose each dictation and its answer (compose) -> dictate it with the system voice and
upload it through the product's ingest API (upload) -> record the text as the verbatim transcript,
assemble the frozen eval set and write the gold template and fields onto each item (build_set).
The set is marked synthetic in its name, description and stratification_spec, and every gate run
copies that provenance into its config_snapshot; replace it with radiologist-annotated gold before
real patients. Developer machines only.

    python -m radreport.devtools.synthetic_goldset --lab sunrise --per-template 12
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import select

from radreport.core.config import get_settings
from radreport.core.types import VerbatimSource
from radreport.db.models.evaluation import EvalItem, EvalSet
from radreport.db.models.knowledge import Template, TemplateVersion
from radreport.db.models.tenancy import Tenant
from radreport.db.session import bind_tenant, system_session
from radreport.devtools.demo_lab import CREDENTIALS, Session, _credentials
from radreport.devtools.synthetic import spoken_audio
from radreport.eval.goldset import assemble, eligible_candidates, freeze
from radreport.onboarding.paired_audio import submit_verbatim

PROVENANCE = "synthetic"

#: (sentence, gold answer) choices per field. A gold answer names the enum, number or text a correct extraction returns.
Choice = tuple[str, dict[str, Any]]


def _measure(template: str, low: float, high: float, unit: str, rng: random.Random) -> tuple[str, str]:
    value = f"{rng.uniform(low, high):.1f}"
    return template.format(v=value, u=unit), f"{value} {unit}"


def _bank(code: str, rng: random.Random) -> dict[str, list[Choice]]:
    """Fresh measurements each call, so no two dictations are identical."""
    cbd, cbd_gold = _measure("CBD measures {v} {u}.", 3, 9, "mm", rng)
    spleen, spleen_gold = _measure("Spleen measures {v} {u}.", 8, 15, "cm", rng)
    rk, rk_gold = _measure("Right kidney measures {v} {u} with no hydronephrosis.", 9, 12, "cm", rng)
    lk, lk_gold = _measure("Left kidney measures {v} {u} with no hydronephrosis.", 9, 12, "cm", rng)
    node = round(rng.uniform(0.6, 2.4), 1)
    banks: dict[str, dict[str, list[Choice]]] = {
        "US_ABDOMEN": {
            "liver": [("Liver is normal in size and echotexture.", {"value_enum": "normal"}), ("Liver shows increased echogenicity, in keeping with fatty infiltration.", {"value_enum": "increased"})],
            "gallbladder": [("Gallbladder is present and normal.", {"value_enum": "present"}), ("Gallbladder is absent, post cholecystectomy.", {"value_enum": "absent"})],
            "cbd": [(cbd, {"value_text": cbd_gold})],
            "pancreas": [("Pancreas is normal.", {"value_text": "normal"}), ("Pancreas is obscured by bowel gas.", {"value_text": "obscured by bowel gas"})],
            "spleen": [(spleen, {"value_text": spleen_gold}), ("Spleen is normal in size.", {"value_text": "normal in size"})],
            "right_kidney": [(rk, {"value_text": rk_gold})],
            "left_kidney": [(lk, {"value_text": lk_gold})],
            "urinary_bladder": [("Urinary bladder is well distended with a normal wall.", {"value_text": "well distended normal wall"})],
            "impression": [("Impression: fatty liver, otherwise normal study.", {"value_text": "fatty liver otherwise normal"}), ("Impression: normal ultrasound abdomen.", {"value_text": "normal ultrasound abdomen"})],
        },
        "XR_CHEST": {
            "trachea": [("Trachea is central.", {"value_text": "central"}), ("Trachea is shifted to the right.", {"value_text": "shifted to the right"})],
            "cardiothoracic_ratio": [("Cardiothoracic ratio is normal.", {"value_enum": "normal"}), ("Cardiothoracic ratio is increased.", {"value_enum": "increased"})],
            "lung_fields": [("Both lung fields are clear.", {"value_enum": "clear"}), ("There is an opacity in the right lower zone.", {"value_enum": "opacity"})],
            "costophrenic_angles": [("Costophrenic angles are sharp.", {"value_enum": "sharp"}), ("The left costophrenic angle is blunted.", {"value_enum": "blunted"})],
            "bony_thorax": [("Bony thorax is intact.", {"value_text": "intact"}), ("There is an old healed fracture of the left seventh rib.", {"value_text": "old healed fracture left seventh rib"})],
            "impression": [("Impression: right lower zone pneumonia.", {"value_text": "right lower zone pneumonia"}), ("Impression: normal chest radiograph.", {"value_text": "normal chest radiograph"})],
        },
        "CT_CHEST": {
            "lungs": [("Both lungs are clear.", {"value_enum": "clear"}), ("There is consolidation in the right lower lobe.", {"value_enum": "consolidation"}), ("Ground glass opacities are seen in both lower lobes.", {"value_enum": "ground glass"})],
            "pleura": [("A small pleural effusion is present on the right.", {"value_enum": "present"}), ("No pleural effusion.", {"value_enum": "absent"})],
            "mediastinum": [(f"A mediastinal lymph node measures {node} centimetres.", {"value_numeric": node})],
            "heart": [("Heart is normal in size.", {"value_enum": "normal"}), ("Heart is enlarged.", {"value_enum": "enlarged"})],
            "airways": [("Central airways are patent.", {"value_text": "patent"})],
            "impression": [("Impression: likely infective consolidation.", {"value_text": "likely infective consolidation"}), ("Impression: no acute abnormality in the chest.", {"value_text": "no acute abnormality"})],
        },
        "CT_KUB": {
            "right_kidney": [("A calculus is present in the right kidney.", {"value_enum": "present"}), ("No calculus in the right kidney.", {"value_enum": "absent"})],
            "left_kidney": [("A calculus is present in the left kidney.", {"value_enum": "present"}), ("No calculus in the left kidney.", {"value_enum": "absent"})],
            "ureters": [("Both ureters are not dilated.", {"value_enum": "not dilated"}), ("The right ureter is dilated.", {"value_enum": "dilated"})],
            "urinary_bladder": [("Urinary bladder is normal.", {"value_enum": "normal"}), ("Urinary bladder shows wall thickening.", {"value_enum": "wall thickening"})],
            "impression": [("Impression: right renal calculus without obstruction.", {"value_text": "right renal calculus without obstruction"}), ("Impression: no urinary tract calculus.", {"value_text": "no urinary tract calculus"})],
        },
    }
    return banks[code]


@dataclass(slots=True)
class Dictation:
    template_code: str
    text: str
    fields: dict[str, dict[str, Any]]
    study_code_spoken: bool
    spoken_study_code: str


#: The ingest metadata each template's studies carry.
STUDY_META = {"US_ABDOMEN": ("US", "abdomen", "USG Abdomen"), "XR_CHEST": ("XR", "chest", "X-ray Chest PA"), "CT_CHEST": ("CT", "chest", "CT Chest Plain"), "CT_KUB": ("CT", "abdomen", "CT KUB")}


def compose(code: str, spoken_study_code: str, rng: random.Random) -> Dictation:
    """Three or more findings and the impression, with the spoken study code opening half the dictations, so routing is tested both ways."""
    bank = _bank(code, rng)
    findings = [k for k in bank if k != "impression"]
    chosen = sorted(rng.sample(findings, k=rng.randint(min(3, len(findings)), len(findings))), key=findings.index) + ["impression"]
    sentences, gold = [], {}
    for key in chosen:
        sentence, answer = rng.choice(bank[key])
        sentences.append(sentence)
        gold[key] = answer
    spoken = rng.random() < 0.5
    text = (f"Study type {spoken_study_code}. " if spoken else "") + " ".join(sentences)
    return Dictation(template_code=code, text=text, fields=gold, study_code_spoken=spoken, spoken_study_code=spoken_study_code)


def upload(s: Session, lab_id: str, dictations: list[Dictation]) -> list[tuple[Dictation, str]]:
    """Each dictation read aloud and uploaded as a radiologist would, through the ingest API."""
    users = s.call("admin", "GET", f"/admin/api/labs/{lab_id}/users", params={"page_size": 100}) or []
    radiologists = [u for u in users if "radiologist" in u["roles"] and u.get("radiologist_profile_id")]
    if not radiologists:
        raise SystemExit("the lab has no radiologist accounts; run `make seed-local` and the demo lab first")
    uploaded = []
    for i, dictation in enumerate(dictations):
        audio = spoken_audio(dictation.text)
        if audio is None:
            raise SystemExit("no system voice on this machine (macOS `say`); the gold set needs real speech")
        modality, part, description = STUDY_META[dictation.template_code]
        who, radiologist = ("radiologist", radiologists[0]) if i % 2 == 0 or len(radiologists) == 1 else ("radiologist:1", radiologists[1])
        study = s.call(who, "POST", "/ingest/studies", json={"mrn": f"SYNTH-GOLD-{1000 + i}", "accession_number": f"SYNTH-GOLD-ACC-{uuid.uuid4().hex[:10]}", "modality": modality, "body_part_examined": part, "study_description": description, "priority": "routine", "sex": "MF"[i % 2], "age_years": 30 + i % 50}, ok=(200, 201))
        if not study:
            continue
        recording = s.call(who, "POST", "/ingest/recordings", data={"study_id": study["study_id"], "radiologist_id": radiologist["radiologist_profile_id"], "capture_device_class": "dictation_mic_ptt", "is_push_to_talk": "true"}, files={"file": (f"gold-{i}.wav", audio, "audio/wav")}, ok=(201,))
        if recording:
            uploaded.append((dictation, recording["recording_id"]))
    return uploaded


def build_set(tenant_id: uuid.UUID, name: str, uploaded: list[tuple[Dictation, str]], versions: dict[str, uuid.UUID], seed: int) -> dict[str, Any]:
    """Verbatim transcripts, the assembled and frozen eval set, and the gold answers on each item."""
    with system_session() as session:
        bind_tenant(session, tenant_id)
        by_recording = {uuid.UUID(rid): d for d, rid in uploaded}
        for recording_id, dictation in by_recording.items():
            # `imported`, not `human_annotation`: no person transcribed this; the text is what the voice was given to say.
            submit_verbatim(session, tenant_id=tenant_id, recording_id=recording_id, text=dictation.text, annotator_id=None, includes_disfluencies=True, source=VerbatimSource.IMPORTED)
        eval_set = EvalSet(tenant_id=tenant_id, name=name, description="SYNTHETIC gold set: dictations composed from known findings and read by a system voice; the template and fields are known by construction, not annotated by a radiologist. For demos and for exercising the release gate only.", is_canonical=False, stratification_spec={"provenance": PROVENANCE, "generator": "radreport.devtools.synthetic_goldset", "seed": seed, "templates": sorted(versions)})
        session.add(eval_set)
        session.flush()
        candidates = [c for c in eligible_candidates(session, tenant_id=tenant_id) if c.recording_id in by_recording]
        result = assemble(session, eval_set=eval_set, candidates=candidates, target_current=len(candidates), target_legacy=0, seed=seed)
        items = session.execute(select(EvalItem).where(EvalItem.eval_set_id == eval_set.id)).scalars().all()
        for item in items:
            dictation = by_recording[item.recording_id]
            item.gold_template_version_id = versions[dictation.template_code]
            item.gold_structured_payload = {"provenance": PROVENANCE, "fields": dictation.fields}
            item.gold_codeword_occurrences = {"study_code_spoken": dictation.study_code_spoken, "study_code_text": dictation.spoken_study_code}
        session.flush()
        freeze(session, eval_set=eval_set)
        return {"eval_set": name, "eval_set_id": str(eval_set.id), "items": len(items), "skipped": len(result.skipped), "frozen": eval_set.is_frozen}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--lab", default="sunrise")
    parser.add_argument("--credentials", type=Path, default=CREDENTIALS)
    parser.add_argument("--per-template", type=int, default=12, help="dictations per template; the lab freeze floor is 40 in all")
    parser.add_argument("--name", help="eval set name (default <lab>-synthetic-gold-v1)")
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args(argv)
    if get_settings().environment not in ("local", "development", "test"):
        raise SystemExit("synthetic gold data is for developer machines only")
    name = args.name or f"{args.lab}-synthetic-gold-v1"

    with system_session() as session:
        tenant = session.execute(select(Tenant).where(Tenant.slug == args.lab)).scalar_one_or_none()
        if tenant is None:
            raise SystemExit(f"no lab {args.lab!r}")
        bind_tenant(session, tenant.id)
        if session.execute(select(EvalSet).where(EvalSet.tenant_id == tenant.id, EvalSet.name == name)).scalar_one_or_none():
            raise SystemExit(f"eval set {name!r} already exists; pass --name for another")
        rows = session.execute(select(Template.code, TemplateVersion.id, TemplateVersion.spoken_study_code).join(TemplateVersion, TemplateVersion.template_id == Template.id).where(Template.tenant_id == tenant.id, TemplateVersion.is_current.is_(True), Template.is_active.is_(True))).all()
        tenant_id = tenant.id
    versions = {code: version_id for code, version_id, _ in rows if code in STUDY_META}
    spoken = {code: spoken_code for code, _, spoken_code in rows}
    if not versions:
        raise SystemExit(f"{args.lab} has none of the demo templates ({', '.join(STUDY_META)}); run the demo lab first")

    rng = random.Random(args.seed)
    dictations = [compose(code, spoken[code] or code.replace("_", " ").lower(), rng) for code in sorted(versions) for _ in range(args.per_template)]
    s = Session(base_url=args.base_url.rstrip("/"), lab_slug=args.lab, creds=_credentials(args.credentials))
    labs = s.call("admin", "GET", "/admin/api/labs", params={"page_size": 100}) or []
    lab_id = next((x["id"] for x in labs if x["slug"] == args.lab), None)
    uploaded = upload(s, lab_id, dictations)
    summary = build_set(tenant_id, name, uploaded, versions, args.seed)
    print(json.dumps({**summary, "uploaded": len(uploaded), "failed_calls": s.failures}, indent=1))
    return 0 if not s.failures else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
