"""Putting live models into the pipeline: per-model client routing, template sections, quote anchoring, the routing picker, and the extraction metrics the release gate reads."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from radreport.adapters.llm.base import LLMRequest, LLMResponse, Usage
from radreport.adapters.llm.prompt import PromptBundle, VolatileBlock
from radreport.adapters.llm.routed import ModelRoutedClient
from radreport.core.errors import ModelResolutionError
from radreport.eval.harness import StageOutputs
from radreport.eval.metrics.extraction_metrics import CseDraft, ExtractionOutput, HallucinationRate, field_matches
from radreport.pipeline.sections import section_specs
from radreport.pipeline.stages.extract import ExtractStage, SectionSpec, anchor_quote
from radreport.pipeline.stages.routing import ScoredCandidate, TemplateCandidate
from radreport.pipeline.stages.routing_picker import NO_PICK, parse_pick
from radreport.pipeline.state import PipelineState, RoutingState


class _Echo:
    def __init__(self, name: str) -> None:
        self.provider_name = name

    async def complete(self, request: LLMRequest, *, model_id: str) -> LLMResponse:
        return LLMResponse(text=self.provider_name, usage=Usage(), model_id=model_id)


def _request() -> LLMRequest:
    return LLMRequest(prompt=PromptBundle(volatile=[VolatileBlock(text="x")]))


async def test_each_call_reaches_the_client_of_the_model_it_names() -> None:
    client = ModelRoutedClient({"gemini-3.5-flash-lite": _Echo("gemini"), "claude-sonnet-5": _Echo("anthropic")})
    assert (await client.complete(_request(), model_id="claude-sonnet-5")).text == "anthropic"
    assert (await client.complete(_request(), model_id="gemini-3.5-flash-lite")).text == "gemini"
    with pytest.raises(ModelResolutionError, match="not live"):
        await client.complete(_request(), model_id="gpt-5")


def _field(key: str, section: str, seq: int, enum: list[str] | None = None) -> SimpleNamespace:
    return SimpleNamespace(field_key=key, section=section, display_label=key.title(), data_type="enum" if enum else "text", enum_values=enum, unit=None, seq=seq)


def test_sections_follow_the_template_and_answer_in_the_parsers_shape() -> None:
    specs = section_specs([_field("impression", "IMPRESSION", 9), _field("liver", "FINDINGS", 1, ["normal", "increased"]), _field("spleen", "FINDINGS", 2)])
    assert [(s.section, s.field_keys) for s in specs] == [("FINDINGS", ("liver", "spleen")), ("IMPRESSION", ("impression",))]
    fields = specs[0].json_schema["properties"]["fields"]
    assert fields["required"] == ["liver", "spleen"] and fields["additionalProperties"] is False
    liver = fields["properties"]["liver"]["anyOf"][0]
    assert liver["properties"]["value_enum"]["anyOf"][0]["enum"] == ["normal", "increased"]
    assert set(liver["required"]) >= {"quote", "char_start", "char_end", "assertion_status"}


def test_a_quote_is_moved_to_where_it_occurs_and_a_paraphrase_is_left_to_fail_grounding() -> None:
    transcript = "Liver is normal. Spleen measures 9 cm. Spleen measures 9 cm."
    assert anchor_quote(transcript, "Liver is normal.", 0, 16) == (0, 16)
    assert anchor_quote(transcript, "Spleen measures 9 cm.", 20, 40) == (17, 38)
    assert anchor_quote(transcript, "Spleen measures 9 cm.", 37, 50) == (39, 60)
    assert anchor_quote(transcript, "spleen is 9 cm", 3, 9) == (3, 9)


def test_extraction_uses_the_routed_templates_sections() -> None:
    a, b = uuid.uuid4(), uuid.uuid4()
    spec = SectionSpec(section="FINDINGS", field_keys=("liver",), json_schema={})
    stage = ExtractStage(client=_Echo("x"), sections=[], sections_by_template={a: [spec]})
    state = PipelineState(tenant_id=uuid.uuid4(), recording_id=uuid.uuid4(), pipeline_run_id=uuid.uuid4())
    assert stage.sections_for(state) == []
    state.routing = RoutingState(chosen_template_version_id=a)
    assert stage.sections_for(state) == [spec]
    state.routing = RoutingState(chosen_template_version_id=b)
    assert stage.sections_for(state) == []


def _shortlist() -> list[ScoredCandidate]:
    def candidate(code: str) -> TemplateCandidate:
        return TemplateCandidate(template_version_id=uuid.uuid4(), template_code=code, display_name=code, modality="CT", body_region="chest", routing_card="", spoken_study_code="")

    return [ScoredCandidate(candidate("CT_CHEST"), 0.4, "lexical"), ScoredCandidate(candidate("XR_CHEST"), 0.3, "lexical")]


def test_the_pick_names_a_shortlisted_template_or_nothing() -> None:
    shortlist = _shortlist()
    assert parse_pick('{"choice": 2, "confidence": 0.9, "reason": "x ray"}', shortlist) == (shortlist[1].candidate.template_version_id, 0.9, "x ray")
    assert parse_pick('{"choice": 3, "confidence": 0.9, "reason": ""}', shortlist)[0] == NO_PICK
    assert parse_pick("not json", shortlist)[0] == NO_PICK
    assert parse_pick('{"choice": 1, "confidence": 7, "reason": ""}', shortlist)[1] == 1.0


def _value(**kwargs: object) -> SimpleNamespace:
    quote = kwargs.pop("quote")
    return SimpleNamespace(**{"value_text": None, "value_enum": None, "value_numeric": None, "assertion_status": "present", "provenance": [SimpleNamespace(quote=quote)], **kwargs})


def test_fields_match_on_enum_number_and_most_of_the_gold_words() -> None:
    assert field_matches(_value(value_enum="Increased", quote="increased echogenicity"), {"value_enum": "increased"})
    assert not field_matches(_value(value_enum="normal", quote="normal"), {"value_enum": "increased"})
    assert field_matches(_value(value_numeric=0.72, quote="0.7 centimetres"), {"value_numeric": 0.7})
    assert field_matches(_value(value_text="9.1", quote="Spleen measures 9.1 cm."), {"value_text": "9.1 cm"})
    assert not field_matches(_value(value_text="normal", quote="Spleen is normal."), {"value_text": "9.1 cm"})


def test_errors_per_draft_and_hallucination_rate() -> None:
    transcript = "Liver is normal. Spleen measures 9.1 cm."
    item = SimpleNamespace(id=uuid.uuid4(), gold_transcript_verbatim=transcript, gold_structured_payload={"fields": {"liver": {"value_enum": "normal"}, "spleen": {"value_text": "9.1 cm"}, "impression": {"value_text": "normal"}}})
    produced = {"liver": _value(value_enum="normal", quote="Liver is normal."), "spleen": _value(value_text="9 cm", quote="Spleen measures 9 cm."), "pancreas": _value(value_text="normal", quote="Pancreas is normal.")}
    outputs = {"extract": StageOutputs(stage_name="extract", outputs={item.id: ExtractionOutput(transcript=transcript, field_values=produced)})}

    errors, detail = CseDraft().score(item, outputs)
    assert errors == 3.0 and detail == {"missed": ["impression"], "wrong": ["spleen"], "invented": ["pancreas"]}

    rate, detail = HallucinationRate().score(item, outputs)
    assert rate == pytest.approx(2 / 3) and detail == {"hallucinated": ["pancreas", "spleen"]}
