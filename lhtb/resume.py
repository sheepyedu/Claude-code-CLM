"""Synchronize model-approved CLM drops before the CLI reloads its transcript."""
import asyncio
import base64
import json
import shlex
import uuid

from clm.context import editable_exchanges
from resume_projection import rewrite_transcript


class Resume:
    def __init__(self, wire, directory):
        self.wire = wire
        self.directory = directory
        self.cursor = 0

    async def __call__(self, agent):
        # A CLI interrupted at a timed boundary can disconnect while the
        # provider is finishing its last stream. Keep requests serial.
        while self.wire.active:
            await asyncio.sleep(0.1)
        if not self.wire.context:
            return
        selected = set()
        for record in sorted((self.directory / "wire").glob("*/metadata.json")):
            index = int(record.parent.name)
            if index <= self.cursor:
                continue
            event = json.loads(record.read_bytes()).get("context", {})
            if event.get("dropped_ids"):
                raw = json.loads((record.parent / "request.raw.json").read_bytes())
                exchanges = editable_exchanges(raw["messages"])
                for key in event["dropped_ids"]:
                    selected.update(b["id"] for b in exchanges[key][1][0]["content"]
                                    if b["type"] == "tool_use")
            self.cursor = index
        if not selected:
            return
        env = agent.environment
        uid = str(agent.uid)
        # The agent's HOME is writable. Read/write its paths inside the
        # container, under its own UID, never as a host path.
        transcript = "/lhtb-home/config/projects/*/" + agent.session + ".jsonl"
        result = await env.exec(user=uid, command="base64 -w0 " + transcript)
        if result.return_code:
            raise RuntimeError("Cannot read the active native transcript")
        before = base64.b64decode(result.stdout.strip(), validate=True)
        after, removed, _ = rewrite_transcript(before, selected)
        trace = self.directory / f"resume-{agent.phase:03d}"
        trace.mkdir()
        (trace / "before.jsonl").write_bytes(before)
        source = trace / "after.jsonl"
        source.write_bytes(after)
        temp = "/tmp/lhtb-resume-" + uuid.uuid4().hex
        await env.upload_file(source, temp)
        # Finish and replace under the agent UID on the same mounted filesystem.
        cmd = f'set -eu; set -- {transcript}; test "$#" = 1; t=$(mktemp "$1.XXXXXX"); cat {shlex.quote(temp)} > "$t"; mv "$t" "$1"'
        result = await env.exec(user="root", command="chmod 0444 " + temp)
        if result.return_code:
            raise RuntimeError("Cannot stage the projected transcript")
        result = await env.exec(user=uid, command=cmd)
        if result.return_code:
            raise RuntimeError("Cannot publish the projected transcript")
        (trace / "receipt.json").write_text(json.dumps({"removed_events": removed, "tool_ids": sorted(selected)}))
        await env.exec(user="root", command="rm -f " + temp)
