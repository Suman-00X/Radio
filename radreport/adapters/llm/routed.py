"""One client for a whole pipeline run, sending each call to the client of the model it names, so steps assigned to different providers each reach theirs and are priced at their own rates.

Order: read the lab's live assignments (live_models) -> build one client per model behind a
ModelRoutedClient (routed_client).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from radreport.adapters.llm.base import BatchRequestItem, LLMClient, LLMRequest, LLMResponse, ResolvedModelRef
from radreport.adapters.llm.factory import client_for
from radreport.adapters.llm.registry import _to_ref
from radreport.core.errors import ModelResolutionError
from radreport.core.types import AssignmentStatus
from radreport.db.models.modelconfig import ModelDefinition, ModelProvider, TaskModelAssignment


@dataclass(frozen=True, slots=True)
class LiveModel:
    """The model live for one step of one lab, and the environment variable holding its provider's key."""

    task_key: str
    ref: ResolvedModelRef
    api_key_env_var: str | None


def live_models(session: Session, tenant_id: uuid.UUID) -> dict[str, LiveModel]:
    """task_key -> the model active for it in this lab; a step with no active assignment is absent."""
    rows = session.execute(select(TaskModelAssignment.task_key, ModelDefinition, ModelProvider).join(ModelDefinition, ModelDefinition.id == TaskModelAssignment.model_definition_id).join(ModelProvider, ModelProvider.id == ModelDefinition.provider_id).where(TaskModelAssignment.tenant_id == tenant_id, TaskModelAssignment.status == AssignmentStatus.ACTIVE)).all()
    return {task_key: LiveModel(task_key=task_key, ref=_to_ref(definition, provider), api_key_env_var=provider.api_key_env_var) for task_key, definition, provider in rows}


class ModelRoutedClient:
    """Dispatches on `model_id` to one client per live model."""

    provider_name = "routed"

    def __init__(self, clients: dict[str, LLMClient]) -> None:
        self._clients = clients
        self._batches: dict[str, LLMClient] = {}

    def _client(self, model_id: str) -> LLMClient:
        client = self._clients.get(model_id)
        if client is None:
            raise ModelResolutionError(f"model {model_id!r} is not live for this lab; live: {sorted(self._clients)}")
        return client

    async def complete(self, request: LLMRequest, *, model_id: str) -> LLMResponse:
        return await self._client(model_id).complete(request, model_id=model_id)

    async def submit_batch(self, items: list[BatchRequestItem], *, model_id: str) -> str:
        client = self._client(model_id)
        batch_id = await client.submit_batch(items, model_id=model_id)
        self._batches[batch_id] = client
        return batch_id

    async def poll_batch(self, batch_id: str) -> str:
        return await self._batches[batch_id].poll_batch(batch_id)

    async def fetch_batch_results(self, batch_id: str) -> dict[str, LLMResponse]:
        return await self._batches[batch_id].fetch_batch_results(batch_id)

    async def aclose(self) -> None:
        for client in self._clients.values():
            close = getattr(client, "aclose", None)
            if close is not None:
                await close()


def routed_client(models: dict[str, LiveModel]) -> ModelRoutedClient | None:
    """A client covering every live model, or None when the lab has none (the graph then runs its deterministic path)."""
    if not models:
        return None
    clients: dict[str, LLMClient] = {}
    for live in models.values():
        if live.ref.model_identifier not in clients:
            clients[live.ref.model_identifier] = client_for(live.ref, api_key_env_var=live.api_key_env_var)
    return ModelRoutedClient(clients)
