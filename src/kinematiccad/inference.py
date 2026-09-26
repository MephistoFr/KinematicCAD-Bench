"""Inference adapters are outside the judge; recorded responses are the replay boundary."""

from __future__ import annotations

import ast
import asyncio
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Protocol

import httpx

from .io import canonical, digest, write_json
from .process import bounded_run

SYSTEM = """You design mechanical parts for KinematicCAD-Bench. Return one complete Python 3.11
script, optionally in a single python code fence. Use CadQuery 2.6.1 and kinematiccad.sdk.
The script is called as: python design.py OUTPUT_DIRECTORY. Work in millimetres in each
body's local coordinate frame. The task defines supplied ideal bearings, body positions,
axes, density, input motor, loads and acceptance thresholds; you cannot change them.
You must design every named part. No evaluator files or solved examples are available.

SDK:
  from kinematiccad.sdk import Part, box, cylinder, prism, transform, export
  box(x,y,z,center=(0,0,0)) -> convex Cell
  cylinder(radius,thickness,center=(0,0,0),segments=96) -> polygonal convex Cell
  prism([(x,y),...],thickness,z=0) -> Cell (convex hull of the supplied points)
  transform(cell,angle=0,offset=(0,0,0)) -> Cell (Z rotation in radians)
  Part.from_cells(name,[cells...]) -> Part, a boolean union of convex CAD solids
  Part(name,cadquery_shape,cells) -> custom shape plus a verified convex decomposition
  export([parts...],sys.argv[1]) -> STEP files and submission.json
For example, Part.from_cells('part',[box(10,8,6)]) constructs one solid box.
Each part must be exactly one closed, positive-volume valid B-Rep solid. Its collision
cells must reconstruct the same occupied volume within the declared tolerance, checked
in both boolean directions. Each cell accepts at most 256 vertices; each part at most
512 cells; all parts together at most 1400. Do not substitute a gear's convex hull for
its teeth. No mesh, actuator, inertia, force, friction or output trajectory is accepted
from your script. Only STEP geometry and convex cells cross into the physical judge.
"""


@dataclass
class Response:
    text: str
    metadata: dict


class Provider(Protocol):
    def generate(self, messages: list[dict], task_id: str) -> Response: ...


class HTTPProvider:
    """OpenAI-compatible Chat Completions and Responses wire formats.

    Explicit parameters allow reasoning models and local servers to differ. No implicit
    retries or replacement of model names; every API call is an evaluation attempt.
    """

    def __init__(self, config, transport=None):
        self.config = config
        self.transport = transport

    def generate(self, messages, task_id):
        c = self.config
        headers = {"Content-Type": "application/json"}
        if c.get("api_key_env"):
            key = os.environ.get(c["api_key_env"])
            if not key:
                raise ValueError(f"Missing environment variable {c['api_key_env']}")
            headers["Authorization"] = "Bearer " + key
        parameters = c.get("parameters", {})
        if set(parameters) & {"model", "messages", "input", "stream", "tools"}:
            raise ValueError("Parameters cannot replace the model, prompt or response protocol")
        protocol = c.get("protocol", "chat")
        if protocol not in ("chat", "responses"):
            raise ValueError("Unknown HTTP protocol")
        body = {"model": c["model"], "stream": False, **parameters}
        body["messages" if protocol == "chat" else "input"] = messages

        async def request():
            # A per-read socket timeout alone would allow an indefinitely trickling response.
            async with asyncio.timeout(c.get("timeout", 180)):
                async with httpx.AsyncClient(
                    timeout=c.get("timeout", 180), transport=self.transport, follow_redirects=False
                ) as client:
                    async with client.stream("POST", c["url"], headers=headers, json=body) as response:
                        response.raise_for_status()
                        chunks = []
                        size = 0
                        async for chunk in response.aiter_bytes():
                            size += len(chunk)
                            if size > 4_000_000:
                                raise ValueError("Inference response quota exceeded")
                            chunks.append(chunk)
                        return json.loads(b"".join(chunks))

        data = asyncio.run(request())
        if protocol == "chat":
            choice = data["choices"][0]
            if choice.get("finish_reason") not in ("stop", None):
                raise ValueError(f"Incomplete generation: {choice.get('finish_reason')}")
            text = choice["message"]["content"]
        else:
            if data.get("status") != "completed":
                raise ValueError(f"Incomplete generation: {data.get('status')}")
            text = "".join(
                block["text"]
                for item in data.get("output", [])
                if item.get("type") == "message"
                for block in item.get("content", [])
                if block.get("type") == "output_text"
            )
        if not isinstance(text, str) or not text.strip():
            raise ValueError("No text in inference response")
        return Response(
            text,
            {
                "provider": "http",
                "protocol": protocol,
                "model": c["model"],
                "response_id": data.get("id"),
                "usage": data.get("usage"),
                "system_fingerprint": data.get("system_fingerprint"),
                "parameters": parameters,
            },
        )


class CommandProvider:
    """Any trusted local model adapter: JSON messages on stdin, Python text on stdout."""

    def __init__(self, config):
        self.config = config

    def generate(self, messages, task_id):
        argv = self.config["argv"]
        if not isinstance(argv, list) or not argv or not all(isinstance(x, str) for x in argv):
            raise ValueError("Command argv must be a nonempty string list")
        data, _ = bounded_run(
            argv,
            timeout=self.config.get("timeout", 300),
            output_limit=1_000_000,
            stdin=canonical({"messages": messages, "task_id": task_id}),
        )
        return Response(
            data.decode("utf-8"),
            {"provider": "command", "argv": argv, "model": self.config.get("model", "local")},
        )


class ReplayProvider:
    def __init__(self, config):
        self.root = Path(config["directory"])

    def generate(self, messages, task_id):
        from .io import confined_file

        source = confined_file(self.root, task_id + ".py", 1_000_000).read_text(encoding="utf-8")
        return Response(
            source,
            {
                "provider": "replay",
                "model": "recorded",
                "source_sha256": hashlib.sha256(source.encode()).hexdigest(),
            },
        )


def provider_from_config(config) -> Provider:
    factories = {"http": HTTPProvider, "command": CommandProvider, "replay": ReplayProvider}
    if config.get("kind") not in factories:
        raise ValueError("Provider kind must be http, command or replay")
    return factories[config["kind"]](config)


def extract_script(text: str) -> str:
    if len(text) > 1_000_000:
        raise ValueError("Script quota exceeded")
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, re.DOTALL)
    if "```" in text:
        if len(blocks) != 1:
            raise ValueError("Expected exactly one Python code block")
        text = blocks[0]
    ast.parse(text)  # Syntax check only: this is not a security sandbox.
    return text.strip() + "\n"


def infer(provider: Provider, task, output: Path) -> str:
    messages = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": canonical(task).decode("utf-8")},
    ]
    output.mkdir(parents=True, exist_ok=True)
    write_json(output / "request.json", {"task_sha256": digest(task), "messages": messages})
    response = provider.generate(messages, task.id)
    write_json(
        output / "response.json",
        {"text": response.text, "metadata": response.metadata, "request_sha256": digest(messages)},
    )
    source = extract_script(response.text)
    (output / "design.py").write_text(source, encoding="utf-8")
    return source
