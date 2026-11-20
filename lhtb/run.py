"""Run one LHTB arm with official Trial orchestration and a private API bridge."""
import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import uuid

from clm.context import Context
from harbor.models.trial.config import TrialConfig
from lhtb.environment import ClaudeTrial
from lhtb.resume import Resume
from skillrl.chat_gateway import ChatMessagesGateway
from wire import Wire

MODEL = "deepseek-v4-1-flash-261017"
SOURCE = Path(__file__).resolve().parent


def mount(source, target, readonly=True):
    value = dict(type="bind", source=str(source), target=target)
    if readonly:
        value["read_only"] = True
    return value


async def run(args):
    os.umask(0o077)
    task = args.task.resolve()
    if not all((task / name).exists() for name in ("task.toml", "instruction.md", "tests/test.sh")):
        raise ValueError("Expected a complete LHTB task directory")
    if not 0 < args.interval < args.budget:
        raise ValueError("Expected 0 < interval < budget")
    os.environ.update(HB_PROCESS_REWARD="1", HB_CONTINUE_MODE="same_conversation",
                      HB_PROCESS_REWARD_INTERVAL_SEC=str(args.interval),
                      HB_PROCESS_REWARD_ACTIVE_BUDGET_SEC=str(args.budget))
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    home = out / "home"
    home.mkdir()
    model_service = json.loads(Path("/mount-data/Tools/services.json").read_text())["services"]["deepseek"]["base_url"]
    key = subprocess.check_output(["/mount-data/Tools/skill-api", "_credential", "--service", "deepseek"], text=True).strip()
    backend = ChatMessagesGateway(model_service, key, MODEL, out / "chat-gateway", timeout=360)
    context = None
    clm_path = SOURCE.parent / "clm"
    mounts = [mount(args.cli, "/opt/claude"), mount(home, "/lhtb-home", False),
              mount(SOURCE / "phase.py", "/opt/lhtb/phase.py"),
              mount(clm_path / "container_entry.py", "/opt/clm/clm/container_entry.py")]
    if args.arm == "clm":
        (out / "context").mkdir()
        context = Context(out / "context")
        mounts[-1] = mount(clm_path, "/opt/clm/clm")
        mounts.extend([mount(SOURCE / "clm-context", "/opt/lhtb/clm-context"),
                       mount(out / "context", "/context", False)])
    with tempfile.TemporaryDirectory(prefix="lhtb-") as tmp:
        sock = Path(tmp) / "messages.sock"
        mounts.append(mount(sock, "/gateway/messages.sock"))
        with Wire(sock, out / "wire", "https://example.invalid", backend, MODEL, "", context, "") as wire:
            wire.timeout_sec = 380
            backend.start()
            thread = threading.Thread(target=wire.serve_forever, daemon=True)
            thread.start()
            try:
                agent_class = "ClaudeCodeCLM" if context else "ClaudeCode"
                config = TrialConfig.model_validate({
                    "task": {"path": task}, "trials_dir": out / "trials",
                    "trial_name": "lhtb-" + args.arm + "-" + uuid.uuid4().hex[:10],
                    "agent": {"import_path": "lhtb.agent:" + agent_class,
                              "model_name": MODEL, "override_timeout_sec": args.budget},
                    "environment": {"import_path": "lhtb.environment:EphemeralDocker",
                                    "mounts": mounts, "delete": True},
                })
                if args.local_image:
                    if not args.image_manifest:
                        raise ValueError("--local-image requires the upstream image manifest")
                    task_obj = await ClaudeTrial._load_task(config)
                    manifest = args.image_manifest.read_bytes()
                    pinned = task_obj.config.environment.docker_image or ""
                    if not pinned.endswith("@sha256:" + hashlib.sha256(manifest).hexdigest()):
                        raise ValueError("Manifest differs from the official task image digest")
                    config_id = json.loads(manifest)["config"]["digest"]
                    image_id = subprocess.check_output(
                        ["docker", "image", "inspect", args.local_image, "--format", "{{.Id}}"], text=True).strip()
                    if image_id != config_id:
                        raise ValueError("Local image differs from the official manifest")
                    (out / "image-receipt.json").write_text(json.dumps({"official": pinned, "config": config_id}))
                    task_obj.config.environment.docker_image = args.local_image
                    trial = ClaudeTrial(config, _task=task_obj)
                else:
                    trial = await ClaudeTrial.create(config)
                trial._agent.before_resume = Resume(wire, out)
                result = await trial.run()
                if result.exception_info or result.verifier_result is None:
                    raise RuntimeError(f"Trial incomplete: {result.exception_info}")
            finally:
                wire.shutdown()
                thread.join()
                backend.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--arm", choices=["native", "clm"], required=True)
    parser.add_argument("--budget", type=int, default=10800)
    parser.add_argument("--interval", type=int, default=1800)
    parser.add_argument("--local-image")
    parser.add_argument("--image-manifest", type=Path)
    parser.add_argument("--cli", type=Path, default=Path("/mount-data/Claude-code-CLM/runtime/claude"))
    asyncio.run(run(parser.parse_args()))
