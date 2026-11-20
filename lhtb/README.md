# Long-Horizon-Terminal-Bench 2.0

This adapter runs the isolated Claude Code CLI in LHTB's task container. Harbor owns the task instructions, task environment, active-time clock, intermediate verification, binary rejection, neutral continuation and final grade. Each trial creates a UUID. Every subsequent phase invokes the CLI with `--resume` and the same UUID and working directory.

Both arms use the private WorkBuddy DeepSeek gateway with the billing-line fix and model `deepseek-v4-1-flash-261017`. CLM additionally exposes the existing context editor. At a phase boundary the adapter waits for the outstanding stream and rewrites accepted tool-pair drops in the native transcript before resuming. It saves both transcript versions for a rewrite. The note travels in the CLM-projected request.

## H20 installation

The benchmark and its bundled Harbor come from upstream commit `7ca0cacea9bf6a0694eaad7306bed794eaaaabce`. The dataset contains 46 revised original and 31 additional tasks across 13 domains. Both task trees include their official verifiers. Five Git LFS media objects were fetched and checked separately. The deployment uses the existing H20 Python environment and the private WorkBuddy `serial-cache-prefix` gateway, as selected by `run.sh`. The API key stays in the host process.

The launcher accepts one task and one arm per invocation. Use a fresh output directory per trial. Default settings use 10,800 seconds of agent-active time and 1,800 seconds between hidden checkpoints. The adapter interrupts the CLI at a timed boundary, checks its resume transcript and returns control to Harbor. Verification time is excluded from the active budget. An early CLI success triggers the official verifier. A failed submission receives Harbor's rejection prompt in the same conversation.

```bash
dataset=/mount-data/Datasets/LHTB-2.0
release="$dataset/LHTB-7ca0cacea9bf6a0694eaad7306bed794eaaaabce"
runner=/mount-data/Claude-code-CLM/experiments/lhtb-20261121/adapter/lhtb
results=/mount-data/TeamShared/YangYang/rollouts
for arm in native clm
do
  "$runner/run.sh" --arm "$arm" \
    --task "$release/tasks-2.0/sqlite_wal_recovery_audit__02" \
    --output "$results/lhtb-sqlite-$arm-new" \
    --local-image lhtb-verified:sqlite-e2a72675 \
    --image-manifest "$dataset/image-manifests/e2a726753c88571ec2ee8063dbf53c9c424b4604b4c7761ba28c30d7e262a408" || exit 1
done
```

For an accessible official registry, omit the two offline image options. Offline resolution verifies the upstream manifest SHA against the task's pinned digest and checks the local Docker image configuration ID before use. Verifier files and logs stay in container-local directories and are copied out by Harbor. The worker runs as a non-root user. During verification the adapter suspends its processes. Docker cleanup is confined to the trial's containers, network and volumes.

The output contains `home/config/projects` (native session), `home/phases` (exact instruction, CLI stream and stderr), `wire` and `chat-gateway` (model inputs, outputs and usage), and the official `trials/*/process_reward_checkpoints` and `result.json`. Run `python3 audit.py OUTPUT` to summarize them. The synthetic smoke task in `smoke/` exercises hidden rejection and same-session recall. Shortened SQLite runs exercise the official timed verifier. Benchmark-wide results require fresh full-budget runs. Task-specific Docker images, sidecars, dependencies and verifier modes are resolved individually.

[Paper](https://arxiv.org/abs/2610.14146) · [Official benchmark](https://github.com/zli12321/LHTB/tree/7ca0cacea9bf6a0694eaad7306bed794eaaaabce) · [DeepSeek gateway patch](https://github.com/sheepyedu/Skil-RSI-Repository/tree/4db007ad9361c03405d687f893b186be4156112f/Claude%20code%20CLM/WorkBuddy%20Bench/2026-11-18/cache-prefix-fix)

## H20 acceptance evidence

The dataset and Harbor manifest at `/mount-data/Datasets/LHTB-2.0/release.sha256` covers 4,314 paths. Its SHA-256 is `74b991efedfd5fef15b43e198b2c4226347f3e6219e3dc07395b54089010a273`. All 77 task configurations enable continue-until-timeout and ship the verifier entry point. The core adapter commit for the final probes is `ea8d153a9d934338dceb8962947df8f60d0670db`.

The original Docker Hub pull timed out on H20. The fallback copied the official SQLite image by digest and verified its manifest, configuration and layer hashes. To restore the verified local tag after a Docker restart, load `/mount-data/Datasets/LHTB-2.0/image-manifests/sqlite-offline.tar`. During initial smoke testing, upstream Harbor teardown removed a shared Python image tag. The original tag was restored from the exact local image ID and the adapter now retains cached images. Another early verifier attempt lacked an ephemeral `/logs/verifier` directory. The environment now creates the log directories before agent setup.

The two recall probes each received an official binary rejection and passed after resuming with the same UUID. The SQLite acceptance run used 22-second checkpoints and a 53-second active budget for both arms, with the official task instructions, image and grading script. Its rewards are integration-test observations only. Separate checks applied an accepted CLM edit, preserved its note, rewrote the native transcript and checked repaired parent pointers. Only SQLite's task-specific runtime and the small recall fixture were exercised live.
