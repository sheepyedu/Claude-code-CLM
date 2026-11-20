from harbor.environments.docker.docker import DockerEnvironment
from harbor.trial.trial import Trial


class EphemeralDocker(DockerEnvironment):
    async def start(self, force_build):
        await super().start(force_build)
        result = await self.exec(user="root", command="mkdir -p /logs/agent /logs/artifacts /logs/verifier")
        if result.return_code:
            raise RuntimeError("Cannot create ephemeral Harbor log directories")

    async def stop(self, delete):
        try:
            await self._run_docker_compose_command(["down", "--volumes", "--remove-orphans"])
        finally:
            self._cleanup_mounts_compose_file()

    @property
    def capabilities(self):
        return super().capabilities.model_copy(update={"mounted": False})


class ClaudeTrial(Trial):
    # Harbor's stock Docker mounts hidden verifier logs; use container-local
    # directories and the official ephemeral-provider artifact copy path.
    def _default_agent_env_mounts(self):
        return list(self.config.environment.mounts or [])

    def _verifier_env_mounts(self, env_config):
        return []

    async def _hide_shared_verifier_artifacts(self):
        result = await self._environment.exec(user="root", command="rm -rf /tests /logs/verifier && mkdir -p /logs/verifier")
        if result.return_code:
            raise RuntimeError("Hidden verifier cleanup failed")

    async def _signal_agent_process_tree(self, signal_name):
        # CLI tool processes may outlive their shell. This UID belongs only to
        # this trial's agent. Freeze its processes during shared verification.
        if signal_name not in {"STOP", "CONT"}:
            raise ValueError(signal_name)
        cmd = f"python3 - {signal_name} {self._agent.uid}" + " <<'PYTHON'\n" + """import os, signal, sys
from pathlib import Path
for status in Path("/proc").glob("[0-9]*/status"):
    try:
        uid = next(x for x in status.read_text().splitlines() if x.startswith("Uid:"))
        if int(uid.split()[1]) == int(sys.argv[2]):
            os.kill(int(status.parent.name), getattr(signal, "SIG" + sys.argv[1]))
    except (FileNotFoundError, ProcessLookupError):
        pass
PYTHON"""
        result = await self._environment.exec(command=cmd, user="root")
        if result.return_code:
            raise RuntimeError("Failed to signal the trial worker")

    async def _run_verification(self):
        # Harbor can exhaust the active budget while an exec is still inside
        # the container. Keep all agent work frozen during the final grade.
        await self._signal_agent_process_tree("STOP")
        return await super()._run_verification()

    async def _run_process_reward_checkpoint(self, **kwargs):
        await self._signal_agent_process_tree("STOP")
        result = await super()._run_process_reward_checkpoint(**kwargs)
        await self._signal_agent_process_tree("CONT")
        return result
