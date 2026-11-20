"""Native Claude Code phases for the official LHTB Harbor trial."""
import json
import shlex
import uuid

from harbor.agents.base import BaseAgent
from clm.run import system_prompt


class ClaudeCode(BaseAgent):
    arm = "native"

    @classmethod
    def name(cls):
        return "lhtb-claude-code-" + cls.arm

    def version(self):
        return "2.1.160"

    def set_process_reward_tracker(self, tracker):
        self.tracker = tracker

    async def setup(self, environment):
        self.environment = environment
        self.session = str(uuid.uuid4())
        self.phase = 0
        declared_user = environment.default_user
        self.uid = 29117
        if declared_user not in (None, "", 0, "0", "root"):
            lookup = await environment.exec(user=declared_user, command="id -u")
            if lookup.return_code or int(lookup.stdout.strip()) == 0:
                raise RuntimeError("Task agent identity unavailable")
            self.uid = int(lookup.stdout.strip())
        result = await environment.exec(user="root", env={
            "LHTB_UID": str(self.uid), "LHTB_CREATE_USER": "1" if declared_user in (None, "", 0, "0", "root") else "0"
        }, command="""
set -eu
if test "$LHTB_CREATE_USER" = 1; then
  if getent passwd "$LHTB_UID" >/dev/null; then exit 1; fi
  useradd -u "$LHTB_UID" -M -d /lhtb-home lhtbworker
fi
mkdir -p /logs/agent /logs/artifacts /lhtb-home/config
chown -R "$LHTB_UID" /lhtb-home /logs/agent /logs/artifacts
if test -d /context; then chown "$LHTB_UID" /context; fi
if test "$LHTB_CREATE_USER" = 1 && test "$PWD" != /; then chown "$LHTB_UID" "$PWD"; fi
command -v python3 >/dev/null
test -x /opt/claude
""")
        if result.return_code:
            raise RuntimeError(f"Claude Code setup failed: {result.stderr}")

    async def run(self, instruction, environment, context):
        await self._phase(instruction, context)

    async def resume_after_verifier_rejection(self, user_prompt, context):
        await self.before_resume(self)
        await self._phase(user_prompt, context)

    async def _phase(self, prompt, context):
        self.phase += 1
        until_checkpoint = ((self.tracker.completed_checkpoints + 1)
                            * self.tracker.config.interval_sec - self.tracker.active_sec)
        args = ["python3", "/opt/lhtb/phase.py", str(self.phase), self.session,
                str(max(0.01, min(until_checkpoint, self.tracker.remaining_sec))),
                self.model_name, prompt]
        if self.arm == "clm":
            args.append(system_prompt("LHTB-" + self.session).replace("/workspace", "/lhtb-home/notes"))
        metadata = dict(context.metadata or {})
        metadata.update(session_id=self.session, phase=self.phase)
        context.metadata = metadata
        result = await self.environment.exec(command=shlex.join(args), user=str(self.uid), env={
            "HOME": "/lhtb-home", "CLAUDE_CONFIG_DIR": "/lhtb-home/config",
            "PATH": "/opt/lhtb:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
            "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1", "DISABLE_AUTOUPDATER": "1",
            "CLM_CONTEXT_DIR": "/context", "CLAUDE_CODE_SUBAGENT_MODEL": self.model_name,
            "CLAUDE_CODE_MAX_OUTPUT_TOKENS": "16384",
            **({"DISABLE_AUTO_COMPACT": "1", "CLAUDE_CODE_AUTO_COMPACT_WINDOW": "393216"}
               if self.arm == "clm" else {"CLAUDE_AUTOCOMPACT_PCT_OVERRIDE": "75",
                                         "CLAUDE_CODE_AUTO_COMPACT_WINDOW": "200000"}),
        })
        if result.return_code:
            raise RuntimeError(f"Claude phase {self.phase} failed: {result.stderr[-800:]}")
        reason = json.loads(result.stdout.strip())["reason"]
        context.metadata["termination_reason"] = reason
        (self.logs_dir / f"phase-{self.phase:03d}.json").write_text(json.dumps(context.metadata))


class ClaudeCodeCLM(ClaudeCode):
    arm = "clm"
