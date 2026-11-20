"""Run one native CLI process, preserving its transcript across verifier pauses."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys

phase, session, seconds, model, prompt, *extra = sys.argv[1:]
home = Path("/lhtb-home")
(home / "notes").mkdir(exist_ok=True)
logs = home / "phases" / phase
logs.mkdir(parents=True)
args = ["python3", "/opt/clm/clm/container_entry.py", "--bare", "--print", "--verbose",
        "--output-format", "stream-json", "--model", model, "--permission-mode",
        "bypassPermissions", "--setting-sources", "", "--strict-mcp-config",
        "--mcp-config", '{"mcpServers":{}}', "--no-chrome",
        "--session-id" if phase == "1" else "--resume", session]
if extra:
    args += ["--append-system-prompt", extra[0]]
(logs / "prompt.txt").write_text(prompt)
with (logs / "prompt.txt").open("rb") as inp, (logs / "events.jsonl").open("xb") as out, (logs / "stderr").open("xb") as err:
    process = subprocess.Popen(args, stdin=inp, stdout=out, stderr=err, start_new_session=True)
    try:
        code = process.wait(timeout=float(seconds))
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGINT)
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
        reason = "process_reward_checkpoint"
    else:
        events = [json.loads(line) for line in (logs / "events.jsonl").read_bytes().splitlines() if line.strip()]
        if code or not any(e.get("type") == "result" and e.get("session_id") == session
                           and e.get("subtype") == "success" and not e.get("is_error") for e in events):
            raise RuntimeError(f"CLI exit {code} without successful result for session {session}")
        reason = "confirmed_task_complete"
if not any((home / "config/projects").glob(f"*/{session}.jsonl")):
    raise RuntimeError("Missing native CLI resume transcript")
print(json.dumps({"reason": reason}))
