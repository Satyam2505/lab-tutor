"""OllamaBackend -- the `think` toggle added this session.

Measured during evaluation/run_evaluation.py's real run against local
qwen3:8b: with thinking on and the default 400-token budget, most calls
silently fell back to the template because the reasoning pass consumed
the whole budget before any visible reply. This pins the fix: `think`
must be sent as an explicit boolean matching `LABTUTOR_OLLAMA_THINK`,
and the reply must come from `message.content`, never `message.thinking`.
"""

from __future__ import annotations

import asyncio

import httpx
import pytest

from backend.config import Settings
from backend.llm.client import OllamaBackend


class _FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload
        self.status_code = 200

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


@pytest.fixture
def capture_post(monkeypatch):
    captured: dict = {}

    async def fake_post(self, url, json=None, **kwargs):  # noqa: ANN001
        captured["url"] = url
        captured["json"] = json
        return _FakeResponse(
            {"message": {"role": "assistant", "content": "a real reply", "thinking": "internal"}}
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    return captured


async def test_think_false_by_default(capture_post, monkeypatch):
    monkeypatch.delenv("LABTUTOR_OLLAMA_THINK", raising=False)
    backend = OllamaBackend(Settings())
    reply = await backend.complete(system="s", user="u")
    assert capture_post["json"]["think"] is False
    assert reply.text == "a real reply"  # never the "thinking" field


async def test_think_true_when_configured(capture_post, monkeypatch):
    monkeypatch.setenv("LABTUTOR_OLLAMA_THINK", "true")
    backend = OllamaBackend(Settings())
    await backend.complete(system="s", user="u")
    assert capture_post["json"]["think"] is True


async def test_concurrent_calls_are_bounded_by_llm_max_concurrency(monkeypatch):
    """Regression test for the missing concurrency cap found this session
    (Explore-agent sweep): before this, nothing bounded how many LLM
    calls could run at once."""
    from backend.config import reload_settings

    monkeypatch.setenv("LABTUTOR_LLM_MAX_CONCURRENCY", "3")
    reload_settings()  # also exercises this session's reload_settings() cascade fix

    in_flight = 0
    peak_in_flight = 0
    lock = asyncio.Lock()

    async def slow_fake_post(self, url, json=None, **kwargs):  # noqa: ANN001
        nonlocal in_flight, peak_in_flight
        async with lock:
            in_flight += 1
            peak_in_flight = max(peak_in_flight, in_flight)
        await asyncio.sleep(0.05)
        async with lock:
            in_flight -= 1
        return _FakeResponse({"message": {"content": "ok"}})

    monkeypatch.setattr(httpx.AsyncClient, "post", slow_fake_post)

    backend = OllamaBackend(Settings())
    await asyncio.gather(
        *(backend.complete(system="s", user=f"u{i}") for i in range(10))
    )

    assert peak_in_flight <= 3, f"concurrency cap was not enforced: peak={peak_in_flight}"

    monkeypatch.delenv("LABTUTOR_LLM_MAX_CONCURRENCY", raising=False)
    reload_settings()
