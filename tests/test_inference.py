import json
import asyncio
import httpx
import pytest

from kinematiccad.inference import HTTPProvider, extract_script, infer
from kinematiccad.tasks import make_task


@pytest.mark.parametrize("protocol", ["chat", "responses"])
def test_http_protocol_and_recording(tmp_path, protocol):
    def handler(request):
        body = json.loads(request.content)
        assert body["model"] == "exact-test-model"
        assert body["stream"] is False
        if protocol == "chat":
            assert "messages" in body
            data = {"choices": [{"finish_reason": "stop", "message": {"content": "print('design')"}}]}
        else:
            assert "input" in body
            data = {
                "status": "completed",
                "output": [
                    {"type": "message", "content": [{"type": "output_text", "text": "print('design')"}]}
                ],
            }
        return httpx.Response(200, json=data)

    provider = HTTPProvider(
        dict(url="https://example.test/v1", model="exact-test-model", protocol=protocol),
        transport=httpx.MockTransport(handler),
    )
    script = infer(provider, make_task("linear"), tmp_path)
    assert script == "print('design')\n"
    assert (tmp_path / "request.json").exists() and (tmp_path / "response.json").exists()


def test_incomplete_generation_is_failure():
    transport = httpx.MockTransport(
        lambda _: httpx.Response(200, json={"choices": [{"finish_reason": "length"}]})
    )
    with pytest.raises(ValueError, match="Incomplete"):
        HTTPProvider(dict(url="https://example.test", model="model"), transport).generate([], "task")


def test_code_extraction_rejects_ambiguous_answers():
    assert extract_script("```python\nprint(1)\n```") == "print(1)\n"
    with pytest.raises(ValueError):
        extract_script("```python\nprint(1)\n```\n```python\nprint(2)\n```")
    with pytest.raises(SyntaxError):
        extract_script("Here is my design.")


def test_http_total_deadline_covers_slow_responses():
    async def handler(request):
        await asyncio.sleep(0.1)
        return httpx.Response(200, json={"choices": [{"message": {"content": "print(1)"}}]})

    provider = HTTPProvider(
        dict(url="https://example.test", model="test", timeout=0.02), transport=httpx.MockTransport(handler)
    )
    with pytest.raises(TimeoutError):
        provider.generate([], "task")
