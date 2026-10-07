"""Measures a draft's fields against the annotated ones: how many are wrong and how many were never said.

Defines: the extract stage's output for scoring (ExtractionOutput), the per-field comparison
(field_matches), errors per draft (CseDraft) and the share of returned fields that are invented or
uncited (HallucinationRate).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

EXTRACT_STAGE = "extract"

_WORD = re.compile(r"\d+(?:\.\d+)?|[a-z]+")

#: Share of the gold text's words a returned free-text value must contain to count as the same finding.
TEXT_OVERLAP = 0.6


@dataclass(slots=True)
class ExtractionOutput:
    """What the extract stage produced for one item: its field values and the transcript they quote."""

    transcript: str
    field_values: dict[str, Any] = field(default_factory=dict)


def _get(value: Any, key: str) -> Any:
    return value.get(key) if isinstance(value, dict) else getattr(value, key, None)


def _quote(value: Any) -> str:
    provenance = _get(value, "provenance") or []
    first = provenance[0] if provenance else None
    return str(_get(first, "quote") or "") if first is not None else str(_get(value, "quote") or "")


def field_matches(predicted: Any, gold: dict[str, Any]) -> bool:
    """The same finding: same presence, and the same enum, number (to 0.05) or, for free text, most of the gold words."""
    gold_status = gold.get("assertion_status")
    if gold_status and _get(predicted, "assertion_status") != gold_status:
        return False
    if gold.get("value_enum") is not None:
        return str(_get(predicted, "value_enum") or "").strip().lower() == str(gold["value_enum"]).strip().lower()
    if gold.get("value_numeric") is not None:
        number = _get(predicted, "value_numeric")
        return number is not None and abs(float(number) - float(gold["value_numeric"])) <= 0.05
    if gold.get("value_text"):
        wanted = set(_WORD.findall(str(gold["value_text"]).lower()))
        said = set(_WORD.findall(f"{_get(predicted, 'value_text') or ''} {_quote(predicted)}".lower()))
        return not wanted or len(wanted & said) / len(wanted) >= TEXT_OVERLAP
    return True


def _scored(item: Any, stage_outputs: dict[str, Any]) -> tuple[ExtractionOutput, dict[str, dict[str, Any]]] | None:
    gold = (item.gold_structured_payload or {}).get("fields")
    outputs = stage_outputs.get(EXTRACT_STAGE)
    if gold is None or outputs is None:
        return None
    output = outputs.outputs.get(item.id)
    return (output if output is not None else ExtractionOutput(transcript=item.gold_transcript_verbatim or "")), gold


class CseDraft:
    """Field errors per draft: gold fields missed or answered wrongly, plus fields returned that were never dictated. Lower is better."""

    key = "CSE_DRAFT"
    owner_stage = EXTRACT_STAGE
    task_keys: tuple[str, ...] = ("extraction",)

    def score(self, item, stage_outputs):  # noqa: ANN001, ANN201
        scored = _scored(item, stage_outputs)
        if scored is None:
            return None, None
        output, gold = scored
        missed = sorted(k for k in gold if k not in output.field_values)
        wrong = sorted(k for k in gold if k in output.field_values and not field_matches(output.field_values[k], gold[k]))
        invented = sorted(k for k in output.field_values if k not in gold)
        errors = len(missed) + len(wrong) + len(invented)
        return float(errors), ({"missed": missed, "wrong": wrong, "invented": invented} if errors else None)


class HallucinationRate:
    """Returned fields that were never dictated, or whose quote is not in the transcript, ÷ returned fields. Lower is better."""

    key = "HALLUC_RATE"
    owner_stage = EXTRACT_STAGE
    task_keys: tuple[str, ...] = ("extraction",)

    def score(self, item, stage_outputs):  # noqa: ANN001, ANN201
        scored = _scored(item, stage_outputs)
        if scored is None:
            return None, None
        output, gold = scored
        if not output.field_values:
            return 0.0, None
        bad = sorted(k for k, v in output.field_values.items() if k not in gold or not _quote(v) or _quote(v) not in output.transcript)
        return round(len(bad) / len(output.field_values), 6), ({"hallucinated": bad} if bad else None)
