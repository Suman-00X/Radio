"""Deepgram's hosted speech recognition (Nova-3 Medical by default) behind the common interface.

Defines: DeepgramEngine, which sends one recording to the pre-recorded `/v1/listen` endpoint with the
lab's keyterms and returns the words with their timings.
"""

from __future__ import annotations

import time
from typing import Any

import httpx

from radreport.adapters.asr.base import ASRConfig, ASRResult, Word
from radreport.core.errors import ProviderError
from radreport.core.logging import get_logger

log = get_logger(__name__)

LISTEN_URL = "https://api.deepgram.com/v1/listen"

#: Nova-3 caps keyterm prompting at about 500 tokens; the lexicon's most important terms come first.
MAX_KEYTERMS = 100


def content_type_of(audio: bytes) -> str:
    """The upload's media type from its header; ingest admits only FLAC and WAV."""
    return "audio/flac" if audio[:4] == b"fLaC" else "audio/wav"


class DeepgramEngine:
    """Pre-recorded transcription with word timings, smart formatting and keyterm biasing."""

    def __init__(self, *, api_key: str, model: str = "nova-3-medical", timeout_seconds: float = 300.0, client: httpx.AsyncClient | None = None) -> None:
        if not api_key:
            raise ProviderError("the deepgram engine needs DEEPGRAM_API_KEY")
        self.engine = "deepgram"
        self.engine_version = f"deepgram/{model}"
        self._model = model
        self._headers = {"Authorization": f"Token {api_key}"}
        self._client = client or httpx.AsyncClient(timeout=timeout_seconds)

    def supports_keyterm_biasing(self) -> bool:
        return True

    def _params(self, config: ASRConfig) -> list[tuple[str, str]]:
        params = [("model", config.model_variant or self._model), ("language", config.language), ("smart_format", "true"), ("punctuate", str(config.punctuate).lower()), ("diarize", str(config.diarize).lower())]
        params += [("keyterm", term) for term in config.keyterms[:MAX_KEYTERMS]]
        return params

    async def transcribe(self, audio: bytes, config: ASRConfig) -> ASRResult:
        started = time.perf_counter_ns()
        try:
            response = await self._client.post(LISTEN_URL, params=self._params(config), content=audio, headers={**self._headers, "Content-Type": content_type_of(audio)})
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise ProviderError(f"deepgram answered {exc.response.status_code}: {exc.response.text[:300]}") from exc
        except httpx.HTTPError as exc:
            raise ProviderError(f"deepgram unreachable: {exc}") from exc
        body: dict[str, Any] = response.json()
        try:
            alternative = body["results"]["channels"][0]["alternatives"][0]
        except (KeyError, IndexError) as exc:
            raise ProviderError("unexpected response shape from deepgram") from exc

        words = [
            Word(
                # The formatted form, so the timing map lines up with the formatted transcript.
                text=w.get("punctuated_word") or w["word"],
                start_ms=int(w["start"] * 1000),
                end_ms=int(w["end"] * 1000),
                confidence=w.get("confidence"),
                speaker_label=str(w["speaker"]) if w.get("speaker") is not None else None,
            )
            for w in alternative.get("words", [])
        ]
        channel = body["results"]["channels"][0]
        return ASRResult(
            text=alternative.get("transcript", "").strip(),
            words=words,
            overall_confidence=alternative.get("confidence"),
            language=channel.get("detected_language") or config.language,
            latency_ms=(time.perf_counter_ns() - started) // 1_000_000,
            raw=body,
        )

    async def aclose(self) -> None:
        await self._client.aclose()
