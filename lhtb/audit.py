"""Summarize CLI, verifier, session, and model receipts from a single trial."""
import argparse
import json
from pathlib import Path


def audit(out):
    trial, = (out / "trials").iterdir()
    result = json.loads((trial / "result.json").read_text())
    session = result["agent_result"]["metadata"]["session_id"]
    transcripts = list((out / "home/config/projects").glob(f"*/{session}.jsonl"))
    assert len(transcripts) == 1
    phases = []
    for phase in sorted((out / "home/phases").iterdir(), key=lambda x: int(x.name)):
        events = []
        for line in (phase / "events.jsonl").read_bytes().splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("session_id"):
                events.append(event["session_id"])
        assert all(value == session for value in events)
        phases.append({"phase": int(phase.name), "session_events": len(events)})
    checkpoints = [json.loads(p.read_text()) for p in sorted(trial.glob("process_reward_checkpoints/*/checkpoint.json"))]
    calls = []
    removed = 0
    for path in sorted((out / "chat-gateway").glob("*/receipt.json")):
        calls.append(json.loads(path.read_bytes()))
        if (path.parent / "request.raw").exists():
            body = json.loads((path.parent / "request.raw").read_bytes())
            system = body["messages"][0]["content"]
            assert body["model"] == "deepseek-v4-1-flash-261017"
            assert not system.startswith("x-anthropic-billing-header:")
            raw = json.loads((path.parent / "request.messages.raw").read_bytes())
            if "x-anthropic-billing-header:" in str(raw.get("system", "")):
                removed += 1
    return {"session": session, "phases": phases, "api_attempts_with_receipts": len(calls),
            "complete_api_calls": sum(bool(c.get("complete")) for c in calls), "billing_lines_removed": removed,
            "checkpoints": [{"id": c["checkpoint_id"], "active_sec": c["active_agent_time_sec"],
                             "rewards": c["rewards"], "error": c.get("error")} for c in checkpoints],
            "trial_error": result["exception_info"], "official_grade": result["verifier_result"]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("trial_output", type=Path)
    print(json.dumps(audit(parser.parse_args().trial_output), indent=2))
