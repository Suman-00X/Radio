"""Turns a template's fields into the extraction units the extract stage asks the model about, one per report section.

Order: describe each field's answer (field_schema) -> group the fields by section into SectionSpecs
(section_specs) -> load them for every current template of a lab (load_sections).
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from radreport.core.types import AssertionStatus, Laterality
from radreport.db.models.knowledge import Template, TemplateField, TemplateVersion
from radreport.pipeline.stages.extract import SectionSpec


class FieldLike(Protocol):
    field_key: str
    section: str
    display_label: str
    data_type: str
    enum_values: list[str] | None
    unit: str | None
    seq: int


def _nullable(schema: dict[str, Any]) -> dict[str, Any]:
    return {"anyOf": [schema, {"type": "null"}]}


def field_schema(field: FieldLike) -> dict[str, Any]:
    """The answer for one field, as the extract stage parses it; every key is required and may be null, which strict decoding needs."""
    enum = _nullable({"type": "string", "enum": list(field.enum_values)}) if field.enum_values else {"type": "null"}
    properties: dict[str, Any] = {
        "value_text": _nullable({"type": "string"}),
        "value_enum": enum,
        "value_numeric": _nullable({"type": "number"}),
        "value_unit": _nullable({"type": "string"}),
        "assertion_status": {"type": "string", "enum": AssertionStatus.values()},
        "laterality": _nullable({"type": "string", "enum": Laterality.values()}),
        "quote": {"type": "string"},
        "char_start": {"type": "integer"},
        "char_end": {"type": "integer"},
    }
    return {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}


def _describe(field: FieldLike) -> str:
    kind = f"one of {', '.join(field.enum_values)}" if field.enum_values else field.data_type
    unit = f", unit {field.unit}" if field.unit else ""
    return f"- {field.field_key} ({field.display_label}): {kind}{unit}"


def section_specs(fields: Sequence[FieldLike]) -> list[SectionSpec]:
    """One SectionSpec per section, in field order; a field the dictation does not address is answered null and dropped."""
    by_section: dict[str, list[FieldLike]] = {}
    for field in sorted(fields, key=lambda f: f.seq):
        by_section.setdefault(field.section, []).append(field)

    specs = []
    for section, owned in by_section.items():
        schema = {"type": "object", "properties": {"fields": {"type": "object", "properties": {f.field_key: _nullable(field_schema(f)) for f in owned}, "required": [f.field_key for f in owned], "additionalProperties": False}}, "required": ["fields"], "additionalProperties": False}
        instruction = f"Section {section}. Fields, with the values each may take:\n" + "\n".join(_describe(f) for f in owned) + "\nAnswer null for a field the dictation does not address."
        specs.append(SectionSpec(section=section, field_keys=tuple(f.field_key for f in owned), json_schema=schema, instruction=instruction))
    return specs


def load_sections(session: Session, tenant_id: uuid.UUID) -> dict[uuid.UUID, list[SectionSpec]]:
    """template_version_id -> its sections, for every current version of an active template in this lab."""
    rows = session.execute(select(TemplateField).join(TemplateVersion, TemplateVersion.id == TemplateField.template_version_id).join(Template, Template.id == TemplateVersion.template_id).where(TemplateVersion.tenant_id == tenant_id, TemplateVersion.is_current.is_(True), Template.is_active.is_(True))).scalars().all()
    by_version: dict[uuid.UUID, list[TemplateField]] = {}
    for field in rows:
        by_version.setdefault(field.template_version_id, []).append(field)
    return {version_id: section_specs(fields) for version_id, fields in by_version.items()}
