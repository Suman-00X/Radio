"""Transcribing through Deepgram: the request it sends and the words it maps back."""

from __future__ import annotations

import httpx
import pytest

from radreport.adapters.asr.base import ASRConfig
from radreport.adapters.asr.deepgram import MAX_KEYTERMS, DeepgramEngine, content_type_of
from radreport.core.errors import ProviderError

_BODY = {
    "results": {
        "channels": [
            {
                "alternatives": [
                    {
                        "transcript": "No hydronephrosis.",
                        "confidence": 0.98,
                        "words": [
                            {"word": "no", "punctuated_word": "No", "start": 0.0, "end": 0.32, "confidence": 0.99},
                            {"word": "hydronephrosis", "punctuated_word": "hydronephrosis.", "start": 0.32, "end": 1.1, "confidence": 0.97, "speaker": 0},
                        ],
                    }
                ]
            }
        ]
    }
}


def _engine(handler) -> DeepgramEngine:
    return DeepgramEngine(api_key="dg-test", client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))


async def test_sends_keyterms_language_and_media_type() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=_BODY)

    terms = tuple(f"term{i}" for i in range(MAX_KEYTERMS + 20))
    await _engine(handler).transcribe(b"fLaC....", ASRConfig(keyterms=terms, language="en-IN"))

    request = seen[0]
    assert request.headers["Authorization"] == "Token dg-test"
    assert request.headers["Content-Type"] == "audio/flac"
    params = request.url.params
    assert params["model"] == "nova-3-medical"
    assert params["language"] == "en-IN"
    assert len(params.get_list("keyterm")) == MAX_KEYTERMS


async def test_maps_words_with_millisecond_timings() -> None:
    result = await _engine(lambda r: httpx.Response(200, json=_BODY)).transcribe(b"RIFF....WAVE", ASRConfig())

    assert result.text == "No hydronephrosis."
    assert [(w.text, w.start_ms, w.end_ms) for w in result.words] == [("No", 0, 320), ("hydronephrosis.", 320, 1100)]
    assert result.words[1].speaker_label == "0"
    assert result.overall_confidence == 0.98
    assert result.raw == _BODY


async def test_an_error_answer_is_a_provider_error() -> None:
    with pytest.raises(ProviderError, match="401"):
        await _engine(lambda r: httpx.Response(401, text="invalid credentials")).transcribe(b"RIFF", ASRConfig())


def test_needs_a_key() -> None:
    with pytest.raises(ProviderError, match="DEEPGRAM_API_KEY"):
        DeepgramEngine(api_key="")


def test_media_type_follows_the_header() -> None:
    assert content_type_of(b"fLaC\x00") == "audio/flac"
    assert content_type_of(b"RIFF\x00\x00\x00\x00WAVE") == "audio/wav"
