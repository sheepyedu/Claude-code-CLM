"""Exercise an accepted CLM edit and safe native-transcript rewrite without another API call."""
import asyncio
import json
import os
import shlex
import shutil
import tempfile
from pathlib import Path
from types import SimpleNamespace

from clm.context import Context, editable_exchanges
from lhtb.resume import Resume


async def check():
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        directory = root / "context"
        directory.mkdir()
        context = Context(directory)
        call = {"role": "assistant", "content": [{"type": "tool_use", "id":"tool-1", "name":"Read","input":{}}]}
        answer = {"role":"user","content":[{"type":"tool_result","tool_use_id":"tool-1","content":"ab " * 400}]}
        messages = [{"role":"user","content":"remember"}, call, answer, {"role":"assistant","content":"ok"},
                    {"role":"user","content":"next"}]
        context.apply(messages)
        key, = editable_exchanges(messages)
        (directory/"edit.json").write_text(json.dumps({"revision":context.revision,"drop":[key],"note":"saved"}))
        projected, event = context.apply(messages)
        assert event["edit"] == "accepted" and len(projected) == 3
        record = root/"wire/00001"
        record.mkdir(parents=True)
        (record/"metadata.json").write_text(json.dumps({"context":event}))
        (record/"request.raw.json").write_text(json.dumps({"messages":messages}))
        session = "synthetic"
        native = root/"home/config/projects/test"/(session+".jsonl")
        native.parent.mkdir(parents=True)
        native.write_text("".join(json.dumps({"type":m["role"],"uuid":str(i),"parentUuid":str(i-1) if i else None,
                                       "message":m})+"\n" for i,m in enumerate(messages)))
        class Env:
            async def exec(self, *, user, command):
                command = command.replace("/lhtb-home", str(root/"home")).replace("/tmp/lhtb-resume-", str(root/"staged-"))
                p = await asyncio.create_subprocess_shell(command, stdout=asyncio.subprocess.PIPE)
                output, _ = await p.communicate()
                return SimpleNamespace(stdout=output.decode(), return_code=p.returncode)
            async def upload_file(self, source, target):
                shutil.copyfile(source, target.replace("/tmp/lhtb-resume-", str(root/"staged-")))
        fn=Resume(SimpleNamespace(active=0,context=context),root)
        await fn(SimpleNamespace(environment=Env(),uid=os.getuid(),session=session,phase=1))
        result=[json.loads(line) for line in native.read_text().splitlines()]
        assert [e['uuid'] for e in result]==['0','3','4'] and result[1]['parentUuid']=='0'
        assert context.note=='saved' and (root/'resume-001/before.jsonl').exists()
        print("accepted CLM edit, preserved note, removed pair, repaired parent UUID, saved before and after")
asyncio.run(check())
