"""Builds the client for a resolved model: the Anthropic SDK for Anthropic, the OpenAI-compatible client for everything else.

Defines: KNOWN_BASE_URLS, base_url_for, client_for.
"""

from __future__ import annotations

import dataclasses
import os

from radreport.adapters.llm.base import LLMClient, ResolvedModelRef
from radreport.adapters.llm.concurrency import ProviderLimiter
from radreport.core.errors import ModelResolutionError
from radreport.core.types import ProviderKind

ANTHROPIC = "anthropic"

#: OpenAI-compatible base URLs of hosted providers, by provider name, so their rows need no endpoint. Version included: the client adds `/chat/completions`.
KNOWN_BASE_URLS: dict[str, str] = {
    "openai": "https://api.openai.com/v1",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai",
}


def uses_anthropic_api(provider_name: str, provider_kind: str) -> bool:
    """True for the Anthropic provider, which is called through its own SDK rather than the OpenAI-compatible client."""
    return provider_name == ANTHROPIC and provider_kind != ProviderKind.LOCAL_OPENAI_COMPATIBLE


def base_url_for(provider_name: str, endpoint: str | None) -> str | None:
    """The OpenAI-compatible base URL: the row's endpoint, else the built-in one for a known provider."""
    return endpoint or KNOWN_BASE_URLS.get(provider_name)


def client_for(ref: ResolvedModelRef, *, api_key_env_var: str | None = None, limiter: ProviderLimiter | None = None) -> LLMClient:
    """A client for this model; the key is read from the environment, never from the database."""
    key = os.environ.get(api_key_env_var) if api_key_env_var else None
    if uses_anthropic_api(ref.provider_name, ref.provider_kind):
        from radreport.adapters.llm.anthropic_client import AnthropicClient

        key = key or os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise ModelResolutionError("the anthropic provider needs an API key in its api_key_env_var (or ANTHROPIC_API_KEY)")
        return AnthropicClient(key, model_ref=ref, limiter=limiter)
    base_url = base_url_for(ref.provider_name, ref.endpoint)
    if not base_url:
        raise ModelResolutionError(f"provider {ref.provider_name!r} has no endpoint: set its OpenAI-compatible base URL, version included (https://host/v1)")
    from radreport.adapters.llm.openai_compat import OpenAICompatibleClient

    return OpenAICompatibleClient(model_ref=dataclasses.replace(ref, endpoint=base_url), api_key=key, limiter=limiter)
