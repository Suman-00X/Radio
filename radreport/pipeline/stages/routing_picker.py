"""The model call in the routing cascade: given the dictation and the shortlisted templates, name the one it was dictated against.

Defines: ModelShortlistPicker, the routing stage's ShortlistPicker backed by the lab's routing_pick
model; build_pick_prompt and parse_pick, its prompt and answer.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Sequence
from typing import Any

from radreport.adapters.llm.base import LLMClient, LLMRequest
from radreport.adapters.llm.prompt import PromptBundle, VolatileBlock, system_block
from radreport.core.logging import get_logger
from radreport.pipeline.stages.routing import ScoredCandidate

log = get_logger(__name__)

PICK_PROMPT = """\
You choose which report template a radiology dictation was dictated against.
You are given the dictation and a numbered shortlist of templates. Pick exactly
one, by its number. Judge by modality and body region first, then by the
findings dictated. Confidence is your probability that the pick is right."""

PICK_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"choice": {"type": "integer"}, "confidence": {"type": "number"}, "reason": {"type": "string"}},
    "required": ["choice", "confidence", "reason"],
    "additionalProperties": False,
}

#: Returned for an unusable answer; it is off every shortlist, so the stage falls back to the top-ranked candidate.
NO_PICK = uuid.UUID(int=0)


def build_pick_prompt(transcript: str, shortlist: Sequence[ScoredCandidate]) -> PromptBundle:
    lines = [f"{i}. {s.candidate.template_code}: {s.candidate.display_name} ({s.candidate.modality}, {s.candidate.body_region}). {s.candidate.routing_card}" for i, s in enumerate(shortlist, 1)]
    return PromptBundle(stable=[system_block(PICK_PROMPT)], volatile=[VolatileBlock(text=f"<dictation>\n{transcript}\n</dictation>\n<templates>\n" + "\n".join(lines) + "\n</templates>", label="dictation_and_shortlist")])


def parse_pick(text: str, shortlist: Sequence[ScoredCandidate]) -> tuple[uuid.UUID, float, str]:
    try:
        payload = json.loads(text)
        index = int(payload["choice"])
        confidence = min(1.0, max(0.0, float(payload["confidence"])))
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        log.warning("routing_pick_unparsable", length=len(text))
        return NO_PICK, 0.0, "unparsable answer"
    if not 1 <= index <= len(shortlist):
        return NO_PICK, 0.0, f"choice {index} is outside the shortlist"
    return shortlist[index - 1].candidate.template_version_id, confidence, str(payload.get("reason", ""))


class ModelShortlistPicker:
    """Asks the routing_pick model, deterministically (temperature 0, fixed seed, so a repeat is a cache hit)."""

    def __init__(self, client: LLMClient, model_id: str, *, max_tokens: int = 512) -> None:
        self._client = client
        self._model_id = model_id
        self._max_tokens = max_tokens

    async def pick(self, transcript: str, shortlist: Sequence[ScoredCandidate]) -> tuple[uuid.UUID, float, str]:
        response = await self._client.complete(LLMRequest(prompt=build_pick_prompt(transcript, shortlist), max_tokens=self._max_tokens, temperature=0.0, seed=0, json_schema=PICK_SCHEMA), model_id=self._model_id)
        return parse_pick(response.text, shortlist)
