"""Choosing the client and URL for a provider: the Anthropic SDK for Anthropic, an OpenAI-compatible base URL for everything else."""

from __future__ import annotations

import uuid

import httpx
import pytest

from radreport.adapters.llm.anthropic_client import AnthropicClient
from radreport.adapters.llm.base import LLMRequest, ResolvedModelRef
from radreport.adapters.llm.factory import client_for
from radreport.adapters.llm.openai_compat import OpenAICompatibleClient
from radreport.adapters.llm.prompt import PromptBundle, VolatileBlock
from radreport.core.errors import ModelResolutionError


def _ref(provider_name: str, *, kind: str = "cloud_api", endpoint: str | None = None) -> ResolvedModelRef:
    return ResolvedModelRef(model_definition_id=uuid.uuid4(), model_identifier="m", provider_name=provider_name, provider_kind=kind, endpoint=endpoint, input_price_per_1k=0.0, output_price_per_1k=0.0, cache_read_price_per_1k=0.0, cache_write_price_per_1k=0.0)


async def _posted_url(client: OpenAICompatibleClient) -> str:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}], "usage": {}})

    client._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    await client.complete(LLMRequest(prompt=PromptBundle(volatile=[VolatileBlock(text="hi")]), max_tokens=1), model_id="m")
    return seen[0]


def test_anthropic_uses_its_sdk(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    assert isinstance(client_for(_ref("anthropic", endpoint="https://api.anthropic.com")), AnthropicClient)


@pytest.mark.parametrize(("provider", "expected"), [("gemini", "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"), ("openai", "https://api.openai.com/v1/chat/completions")])
async def test_known_providers_need_no_endpoint(provider: str, expected: str) -> None:
    client = client_for(_ref(provider))
    assert isinstance(client, OpenAICompatibleClient)
    assert await _posted_url(client) == expected


async def test_an_endpoint_is_a_versioned_base_url() -> None:
    client = client_for(_ref("box", kind="local_openai_compatible", endpoint="http://10.0.0.5:8000/v1/"))
    assert await _posted_url(client) == "http://10.0.0.5:8000/v1/chat/completions"


async def test_a_row_endpoint_beats_the_built_in_one() -> None:
    client = client_for(_ref("gemini", endpoint="https://proxy.example/v1"))
    assert await _posted_url(client) == "https://proxy.example/v1/chat/completions"


def test_an_unknown_provider_without_an_endpoint_is_refused() -> None:
    with pytest.raises(ModelResolutionError, match="base URL"):
        client_for(_ref("mistral"))


async def test_gemini_is_not_sent_the_seed_it_refuses() -> None:
    import json

    bodies: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}], "usage": {}})

    for provider in ("gemini", "box"):
        client = client_for(_ref(provider, endpoint="https://llm.example/v1"))
        client._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        await client.complete(LLMRequest(prompt=PromptBundle(volatile=[VolatileBlock(text="hi")]), max_tokens=1, seed=3), model_id="m")
    assert "seed" not in bodies[0] and bodies[1]["seed"] == 3
