"""Measures a proposed model on a lab's frozen gold set and records the release-gate run that activation checks.

Order: propose the model for the step (propose_assignment) -> run the step's real stages over every
gold item with that model (stage_runner) -> score and record the run through the harness
(run_release_gate) -> attach it to the proposal (attach_eval_run) -> optionally activate, which
re-checks the gate (main).

    python -m radreport.eval.gate_run --lab sunrise --task extraction --model gemini-3.5-flash-lite --eval-set sunrise-synthetic-gold-v1 --activate
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from radreport.adapters.llm.base import BatchRequestItem, LLMClient, LLMRequest, LLMResponse
from radreport.adapters.llm.concurrency import ProviderLimiter
from radreport.adapters.llm.factory import client_for
from radreport.adapters.llm.registry import ResolvedModel, _to_ref, activate_assignment, attach_eval_run
from radreport.admin.modelconfig import propose_assignment
from radreport.core.errors import UngatedActivation
from radreport.core.logging import configure_logging, get_logger
from radreport.core.types import TaskKey
from radreport.db.models.evaluation import EvalItem, EvalRun, EvalSet
from radreport.db.models.modelconfig import ModelDefinition, ModelProvider, TaskModelAssignment
from radreport.db.models.tenancy import PlatformUser, Tenant
from radreport.db.session import bind_tenant, system_session
from radreport.eval.gates import evaluate_gate
from radreport.eval.harness import EvalHarness, StageOutputs, StageRunner, gather_stage
from radreport.eval.metrics.extraction_metrics import EXTRACT_STAGE, ExtractionOutput
from radreport.eval.metrics.routing_metrics import ROUTE_STAGE
from radreport.pipeline.sections import load_sections
from radreport.pipeline.stages.extract import ExtractStage
from radreport.pipeline.stages.normalise import NormaliseStage
from radreport.pipeline.stages.providers import StaticKnowledgeProvider, load_tenant_knowledge
from radreport.pipeline.stages.routing import RoutingStage
from radreport.pipeline.stages.routing_picker import ModelShortlistPicker
from radreport.pipeline.stages.study_code import StudyCodeStage
from radreport.pipeline.state import PipelineState, RoutingState, TranscriptState
from radreport.pipeline.v1 import V1_PIPELINE_VERSION

log = get_logger(__name__)

#: The steps a gate run can measure, and the stage whose output their metrics read.
MEASURABLE_TASKS: dict[str, str] = {TaskKey.EXTRACTION: EXTRACT_STAGE, TaskKey.ROUTING_PICK: ROUTE_STAGE}


class MeteredClient:
    """Adds up what every call cost, including the routing picker's, which no stage result carries."""

    def __init__(self, client: LLMClient) -> None:
        self._client = client
        self.provider_name = client.provider_name
        self.spent_usd = 0.0
        self.calls = 0

    async def complete(self, request: LLMRequest, *, model_id: str) -> LLMResponse:
        response = await self._client.complete(request, model_id=model_id)
        self.spent_usd += response.cost_usd
        self.calls += 1
        return response

    async def submit_batch(self, items: list[BatchRequestItem], *, model_id: str) -> str:
        return await self._client.submit_batch(items, model_id=model_id)

    async def poll_batch(self, batch_id: str) -> str:
        return await self._client.poll_batch(batch_id)

    async def fetch_batch_results(self, batch_id: str) -> dict[str, LLMResponse]:
        return await self._client.fetch_batch_results(batch_id)


@dataclass(slots=True)
class GateContext:
    """The StageContext for one gold item: the candidate model answers every resolve, whatever is live."""

    tenant_id: uuid.UUID
    recording_id: uuid.UUID
    resolved: ResolvedModel
    pipeline_run_id: uuid.UUID = field(default_factory=uuid.uuid4)
    is_shadow: bool = True

    def record_cost(self, usd: float) -> None:
        return None

    async def resolve_model(self, task_key: str) -> ResolvedModel:
        return self.resolved


@dataclass(slots=True)
class GateOutcome:
    assignment_id: uuid.UUID
    eval_run_id: uuid.UUID
    metrics: dict[str, Any]
    passed: bool
    reasons: list[str]
    cost_usd: float
    calls: int


def _state(tenant_id: uuid.UUID, item: EvalItem) -> PipelineState:
    """The gold verbatim as the transcript, so the step is measured on what was said rather than on what the speech engine heard."""
    return PipelineState(tenant_id=tenant_id, recording_id=item.recording_id, pipeline_run_id=uuid.uuid4(), is_shadow=True, transcript=TranscriptState(text=item.gold_transcript_verbatim or "", reconciliation_method="gold_verbatim"))


def stage_runner(session: Session, *, tenant_id: uuid.UUID, task_key: str, resolved: ResolvedModel, client: LLMClient, concurrency: int) -> StageRunner:
    """Runs the stages `task_key` depends on, for real, over each item, and hands the measured stage's output to the harness."""
    knowledge = StaticKnowledgeProvider(load_tenant_knowledge(session, tenant_id))
    from radreport.pipeline.runner import load_template_candidates

    templates = load_template_candidates(session, tenant_id)
    sections = load_sections(session, tenant_id)
    model_id = resolved.ref.model_identifier

    async def run_item(item: EvalItem) -> object:
        ctx = GateContext(tenant_id=tenant_id, recording_id=item.recording_id, resolved=resolved)
        state = _state(tenant_id, item)
        state = (await NormaliseStage(knowledge).run(state, ctx)).output
        if task_key == TaskKey.ROUTING_PICK:
            state = (await StudyCodeStage(knowledge).run(state, ctx)).output
            state = (await RoutingStage(knowledge, templates, picker=ModelShortlistPicker(client, model_id)).run(state, ctx)).output
            return state.routing or RoutingState()
        # Extraction on the gold template, so a routing miss does not count against the extractor.
        state.routing = RoutingState(chosen_template_version_id=item.gold_template_version_id)
        state = (await ExtractStage(client, [], sections_by_template=sections).run(state, ctx)).output
        return ExtractionOutput(transcript=state.transcript.text if state.transcript else "", field_values=dict(state.field_values))

    async def runner(items: Any) -> StageOutputs:
        return await gather_stage(items, MEASURABLE_TASKS[task_key], run_item, max_concurrency=concurrency)

    return runner


async def run_release_gate(session: Session, *, tenant_id: uuid.UUID, assignment: TaskModelAssignment, eval_set: EvalSet, actor_id: uuid.UUID, concurrency: int = 2) -> GateOutcome:
    """Measure the proposal on the frozen set as a release gate, record the run, and attach it to the proposal."""
    if assignment.task_key not in MEASURABLE_TASKS:
        raise ValueError(f"no gate run measures {assignment.task_key!r} yet; measurable: {', '.join(MEASURABLE_TASKS)}")
    definition = session.get(ModelDefinition, assignment.model_definition_id)
    provider = session.get(ModelProvider, definition.provider_id) if definition else None
    if definition is None or provider is None:
        raise ValueError(f"assignment {assignment.id} names no model")
    ref = _to_ref(definition, provider)
    resolved = ResolvedModel(ref=ref, task_key=assignment.task_key, task_bucket=assignment.task_bucket, assignment_id=assignment.id, eval_run_id=None)
    # Patient retries: a free tier answers 429 for a minute at a time, and a gate run must not fail on quota.
    limiter = ProviderLimiter(name=f"gate:{provider.name}", max_concurrency=concurrency, max_attempts=10, base_delay=2.0, max_delay=60.0)
    client = MeteredClient(client_for(ref, api_key_env_var=provider.api_key_env_var, limiter=limiter))

    snapshot = {"model_identifier": ref.model_identifier, "provider": ref.provider_name, "assignment_id": str(assignment.id), "eval_set": eval_set.name, "eval_set_provenance": (eval_set.stratification_spec or {}).get("provenance", "annotated"), "input": "gold_verbatim"}
    runner = stage_runner(session, tenant_id=tenant_id, task_key=assignment.task_key, resolved=resolved, client=client, concurrency=concurrency)
    run = await EvalHarness(session).run(eval_set_id=eval_set.id, pipeline_version=V1_PIPELINE_VERSION, stages=[(MEASURABLE_TASKS[assignment.task_key], runner)], task_key=assignment.task_key, is_release_gate=True, config_snapshot=snapshot)
    run.total_cost_usd = round(client.spent_usd, 6)
    session.flush()

    attach_eval_run(session, assignment_id=assignment.id, tenant_id=tenant_id, eval_run_id=run.id, actor_id=actor_id)
    verdict = evaluate_gate(run, None)
    log.info("release_gate_measured", task_key=assignment.task_key, model_identifier=ref.model_identifier, eval_run_id=str(run.id), metrics={k: v for k, v in (run.metrics or {}).items() if not k.startswith("_")}, passed=verdict.passed, calls=client.calls, cost_usd=run.total_cost_usd)
    return GateOutcome(assignment_id=assignment.id, eval_run_id=run.id, metrics=dict(run.metrics or {}), passed=verdict.passed, reasons=verdict.regressions, cost_usd=float(run.total_cost_usd or 0), calls=client.calls)


def _one(session: Session, statement: Any, what: str) -> Any:
    found = session.execute(statement).scalar_one_or_none()
    if found is None:
        raise SystemExit(f"{what} not found")
    return found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--lab", required=True, help="the lab's slug")
    parser.add_argument("--task", required=True, choices=sorted(MEASURABLE_TASKS))
    parser.add_argument("--model", required=True, help="model_identifier of an active model definition")
    parser.add_argument("--eval-set", required=True, help="name of the lab's frozen eval set")
    parser.add_argument("--actor", default="admin@radreport.local", help="the product admin proposing and activating")
    parser.add_argument("--concurrency", type=int, default=2)
    parser.add_argument("--activate", action="store_true", help="activate the proposal when the gate passes")
    args = parser.parse_args(argv)
    configure_logging()

    with system_session() as session:
        tenant = _one(session, select(Tenant).where(Tenant.slug == args.lab), f"lab {args.lab!r}")
        actor = _one(session, select(PlatformUser).where(PlatformUser.email == args.actor), f"product admin {args.actor!r}")
        bind_tenant(session, tenant.id)
        eval_set = _one(session, select(EvalSet).where(EvalSet.tenant_id == tenant.id, EvalSet.name == args.eval_set), f"eval set {args.eval_set!r}")
        if not eval_set.is_frozen:
            raise SystemExit(f"eval set {args.eval_set!r} is not frozen; a release gate needs a fixed set")
        definition = _one(session, select(ModelDefinition).where(ModelDefinition.model_identifier == args.model, ModelDefinition.is_active.is_(True), or_(ModelDefinition.tenant_id.is_(None), ModelDefinition.tenant_id == tenant.id)), f"model {args.model!r}")
        assignment = propose_assignment(session, tenant_id=tenant.id, task_key=args.task, model_definition_id=definition.id, actor_id=actor.id)
        outcome = asyncio.run(run_release_gate(session, tenant_id=tenant.id, assignment=assignment, eval_set=eval_set, actor_id=actor.id, concurrency=args.concurrency))

        status = "measured"
        if args.activate:
            try:
                activate_assignment(session, assignment_id=assignment.id, tenant_id=tenant.id, actor_id=actor.id)
                status = "activated"
            except UngatedActivation as exc:
                status = f"not activated: {exc}"
        items = session.get(EvalRun, outcome.eval_run_id).metrics.get("_item_count")

    print(json.dumps({"lab": args.lab, "task": args.task, "model": args.model, "eval_set": args.eval_set, "items": items, "metrics": {k: v for k, v in outcome.metrics.items() if not k.startswith("_")}, "gate_passed": outcome.passed, "gate_reasons": outcome.reasons, "calls": outcome.calls, "cost_usd": outcome.cost_usd, "eval_run_id": str(outcome.eval_run_id), "assignment_id": str(outcome.assignment_id), "status": status}, indent=1))
    return 0 if status == "activated" or (not args.activate and outcome.passed) else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
