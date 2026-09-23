"""Worker protocol returns one schema-valid JSON result on execution and input failures."""

import io
import json
from uuid import uuid4

import pytest

from animus_forge.missions.domain import CitizenOutput
from animus_forge.scheduler import worker_main


@pytest.fixture
def payload():
    return dict(
        citizen_role="builder",
        task_id=str(uuid4()),
        mission_id=str(uuid4()),
        description="Review fixture",
        context=dict(
            mission_objective="Fixture", task_description="Review fixture", repository="test/repo"
        ),
    )


def test_worker_passes_typed_context_and_serializes_result(monkeypatch, payload):
    received = []

    class Citizen:
        def run(self, task, context):
            received.append((task, context))
            return CitizenOutput(status="completed", summary="Fixture complete", confidence=1)

    monkeypatch.setitem(worker_main._CITIZEN_REGISTRY, "builder", Citizen)
    output = CitizenOutput.model_validate(worker_main._run(payload))
    assert output.status == "completed"
    assert str(received[0][0].task_id) == payload["task_id"]
    assert received[0][1].repository == "test/repo"


@pytest.mark.parametrize(
    "change,summary",
    [
        ({"citizen_role": "unknown"}, "Unknown citizen"),
        ({"task_id": "bad-uuid"}, "Payload parse error"),
        ({"context": {}}, "Payload parse error"),
    ],
)
def test_invalid_task_is_a_structured_failure(payload, change, summary):
    output = CitizenOutput.model_validate(worker_main._run({**payload, **change}))
    assert output.status == "failed" and summary in output.summary
    assert output.confidence == 0 and output.evidence[0]["type"] == "worker_error"


def test_citizen_exception_becomes_structured_failure(monkeypatch, payload):
    class CrashingCitizen:
        def run(self, **kwargs):
            raise RuntimeError("fixture execution error")

    monkeypatch.setitem(worker_main._CITIZEN_REGISTRY, "builder", CrashingCitizen)
    output = CitizenOutput.model_validate(worker_main._run(payload))
    assert output.status == "failed" and "Worker crashed" in output.summary
    assert output.risks[0]["severity"] == "critical"


@pytest.mark.parametrize(
    "raw,summary",
    [
        ("", "Empty worker payload"),
        ("{broken", "Invalid JSON payload"),
        ("[]", "Unexpected worker error"),
        ('{"citizen_role":"unknown"}', "Unknown citizen"),
    ],
)
def test_stdio_emits_exactly_one_json_line(monkeypatch, capsys, raw, summary):
    monkeypatch.setattr(worker_main.sys, "stdin", io.StringIO(raw))
    worker_main.main()
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 1
    output = CitizenOutput.model_validate(json.loads(lines[0]))
    assert summary in output.summary and output.status == "failed"
