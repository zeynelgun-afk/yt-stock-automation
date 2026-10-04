# YouTube local Hermes execution contract

Implementation is staged in the isolated migration checkout. **Not activated.**
GitHub remains the scheduler; `youtube_auto.yml` requires repository variable
`YT_EXECUTOR=local-hermes`, main, and schedule/manual events. It runs exclusively
on label `yt-hermes`. Register this repository runner with **no default labels**.
PR/push reliability CI remains GitHub-hosted. The daily read-only growth report
remains hosted and uses the renamed YouTube token secret. Its cron is unchanged.

## Runtime and inference

- Independent Python 3.12 venv: `/home/zeynel/.local/share/yt-hermes-runner/venv`.
- Operator-managed Actions installation/checkout beneath
  `/home/zeynel/.local/share/yt-hermes-runner/actions/`; never use this development
  checkout as the runner's production working directory.
- Pre-provision `uv`, trusted `hermes`, `ffmpeg`, `ffprobe`, DejaVu fonts (regular
  and bold), and the independent venv. Production/smoke workflows do not use apt
  or setup-python on Arch. Workflow dependency installation targets this venv.
- All selection, script, learning, pattern extraction and ReplyWriter calls use
  fixed `openai-codex/gpt-6-astra`. Legacy constructor keys are ignored.
- Hermes command: `chat --query-file - --oneshot --format stream-json --safe-mode
  --provider openai-codex --model gpt-6-astra --toolsets none --max-turns 1
  --run-budget 180 --source tool`. Prompt is stdin, fresh empty temp cwd, parent
  timeout 195 seconds. No resume, tools or paid fallback. Subprocess environment
  allowlists HOME/PATH/locale/XDG/HERMES_HOME, excluding application/API secrets.
- Strict JSONL init/text/result ordering and field allowlists; exactly one
  matching-model init and one successful terminal result with session ID.
  Unknown events/fields, tools, invalid JSON, duplicate keys, nonfinite values,
  markdown wrappers, process failures and timeouts fail closed. Known installed
  CLI warning `Warning: Unknown toolsets: none` is the sole non-JSON exception;
  the inspected resolver returns zero tools for this selection.
- Generic caller JSON must be an object. Existing script schema, word budgets,
  editorial checks, source/number validation and reply validation remain. Three
  word-count correction requests at most, on fresh contexts of the same model;
  existing pipeline editorial correction remains bounded. ReplyWriter uses one
  request per draft, existing limits remain 6 generations/3 replies, 14 days,
  page bounds, channel/video identity checks, 210-second pass/240-second wrapper.
- JSON enforcement is **local validation**, not provider-native structured
  decoding or complete semantic fact checking. `provider_status.py` is static
  contract reporting, not an auth, quota or live readiness probe.

## Durable delivery and runner claims

Private local filesystem state must survive checkout cleaning, deployments and
service restarts, and must be backed up with the runner stopped:

- Delivery SQLite: `/home/zeynel/.local/state/yt-hermes-runner/delivery.sqlite`.
  Workflow explicitly sets `YT_DELIVERY_DB` to this same path. Do not override it
  to another ledger when retrying. DB mode 0600; state directories private 0700.
- BOTH video and comment writes claim BEFORE the insertion call. SQLite
  transactions use synchronous FULL and explicit file/directory fsync. Each
  completion receipt is committed/fsynced before follow-up thumbnails/alerts.
- Upload identities are channel + stable `ev:` business-event tags, shared
  across formats and regenerated video/title. No identity means no insert.
  Each alias participates in dedup; a completed replay returns the video ID,
  binds additional aliases and never sends another video. Upload channel must
  match `UCuIeHEWGJoDhiGLNBrwscZw`. `execute(num_retries=0)` replaces the unsafe
  five-retry path. No automatic resumable insert restart after ambiguity.
- Comment identity is channel + parent ID. A receipt suppresses reinsert even
  when list reads are stale or the remote reply has been deleted. Remote reply
  rechecks and existing limits are retained.
- Any exception/no valid remote ID leaves attempted state. It blocks subsequent
  sends of that kind, and the hooks block **all new jobs** until reconciliation.
  No time-based expiry, deletion or assumption that a timeout means no send.
- Job journal: `/home/zeynel/.local/state/yt-hermes-runner/jobs/`. Pre-hook accepts
  only this fixed repository, `refs/heads/main`, approved event/workflow/job/path,
  matching commit/workflow SHA and first run attempt. Production workflow/job:
  `US Stock Market Daily YouTube Automation` / `build-and-generate`; smoke:
  `YouTube Local Hermes Smoke` / `inference-smoke` (manual only).
- Pre-hook fsyncs active claim and permanent run-ID receipt under flock. Any
  unresolved job/delivery blocks the next job; any prior run-ID or attempt >1
  blocks replay. A new ordinary main commit is allowed, including weekly data
  commits. These env checks cannot remotely prove that a SHA is current main.
  At activation the operator must independently verify exact reviewed main SHA.
- Install reviewed `local_runner_guard.py`, `runner-pre-job.sh`, and
  `runner-post-job.sh` **outside checkout** at the runtime root. Configure
  `ACTIONS_RUNNER_HOOK_JOB_STARTED` and `ACTIONS_RUNNER_HOOK_JOB_COMPLETED` to the
  fixed installed executable shell hooks. Never source hook code from checkout.
- `yt-hermes-runner.service.example` is a template, not an installed service.
  Operator provisions one listener, held under flock for its entire lifetime,
  UMask 0077. Service PATH must resolve trusted uv/Hermes; no production dotenv
  or application credentials in its base environment. Secrets belong only to
  the production Actions step. No second listener/manual parallel pipeline.
- Last success-only workflow step calls installed guard `mark-success`. It
  refuses pending deliveries and records pipeline completion only. The post-hook
  archives only explicitly named application artifacts from SAFE_ARTIFACTS.
  Gzip closes before fsync; archive is atomically renamed and directory fsynced
  before writing the `pending-confirmation` receipt and retaining `active.json`.
  It performs no API calls and never waits for its own run to complete. Missing
  marker/workspace, ownership mismatch or archive failure retains unresolved state.
- After GitHub completes the workflow, installed guard `confirm --run-id RUN_ID`
  makes one credential-free public GitHub API GET with a 10-second timeout and
  bounded response size. It requires completed/success, matching repository,
  run ID, head SHA, attempt and workflow path, the original pipeline marker,
  preserved archive and zero unresolved deliveries before durably recording
  success and clearing active state. API failure, malformed/mismatched responses,
  incomplete runs, failure and cancellation remain quarantined with sanitized
  errors; there is no automatic retry/polling loop. The sequential listener's
  next `start` can confirm the immediately prior pending job by the same checks
  before accepting a new run. Failed pipelines require operator reconciliation.
  Existing operator reconciliation remains respected; old run receipts forbid replay.
- No `.git`, `.env`, token/client files, directory-wide globs or general JSON/
  Markdown are archived. Symlinks, linked parents and hardlinked files are
  excluded. Delivery receipts remain separately durable outside checkout.

## Exact operator activation prerequisites (not executed here)

1. Review/merge this migration yourself. Provision Python/uv/media dependencies,
   the independent checkout, private state root, installed hooks and guarded
   service. Register a repository-scoped runner with only `yt-hermes` and no
   default labels. Verify hook execution actually fails the job on pre-hook
   rejection; env assumptions and real runner behavior were not tested here.
2. Leave `YT_EXECUTOR` unset. Pause production YouTube and infrastructure retry
   workflows, pause/drain the growth report during token cutover, and drain or
   cancel ALL running/queued historical jobs. A variable in a new workflow does
   not stop a historical hosted workflow already in flight.
3. At cutover rename production GitHub secrets:
   `YOUTUBE_TOKEN_JSON` → `YT_LOCAL_TOKEN_JSON`,
   `YOUTUBE_CLIENT_SECRET_JSON` → `YT_LOCAL_CLIENT_SECRET_JSON`.
   Remove the **old names**, not just add copies. Remove repository secret
   `OPENROUTER_API_KEY`. Do not revoke any underlying provider/account key.
   New code/workflows use only the renamed YouTube names; historical workflow
   SHAs cannot obtain those names. Remove obsolete Gemini/Groq workflow wiring;
   this migration does not operate on any GitHub secret.
4. Verify exact reviewed main SHA, repository registration, no stale runner
   credentials/checkout, service PATH, existing local Codex subscription route,
   hook paths, state path and media tools. Confirm YouTube token is for the fixed
   channel and contains upload/readonly/analytics/force-ssl scopes. Migration
   tests used synthetic credentials; no real identity/auth was inspected.
5. Start the guarded listener yourself; dispatch `local-hermes-smoke.yml` on
   **main**. It uses only `yt-hermes`, has no publishing/data/notification
   secrets, runs offline tests, then REAL inference on supplied synthetic facts
   through ScriptGenerator and ReplyWriter. It makes 2-4 subscription contexts,
   validates outputs and writes `output/llm_smoke.json`; no sends or data APIs.
   Wait for GitHub's completed smoke conclusion, then explicitly confirm it:

   ```sh
   /home/zeynel/.local/share/yt-hermes-runner/venv/bin/python /home/zeynel/.local/share/yt-hermes-runner/local_runner_guard.py confirm --run-id SMOKE_RUN_ID
   ```

   Require real smoke success, the durable post-hook archive and the confirmed
   success receipt. A pending-confirmation receipt alone cannot prove success.
   Ownership remains unset, so production cannot start during this smoke.
6. Only after these prerequisites, set `YT_EXECUTOR=local-hermes`, re-enable
   schedules and read back workflow/service/runner/variable/secret **names**.
   Preserve all seven exact UTC crons, dispatch choices, created-at/DST resolver
   and `yt-pipeline` concurrency. Do not trigger production to prove activation.
   Infra auto-retry is disabled by the ownership gate; never replay historical
   runs. Operator-approved recovery uses a NEW main dispatch after reconciliation.

The test venv created for this implementation uses a uv-downloaded Python under
`/home/zeynel/yt-migration-evidence/python` and uv under its `tools/`. Keep these
paths if reusing it, or recreate the venv with the operator's durable Python 3.12
installation. No global installer, runner registration or service was activated.

## Operator reconciliation, entirely offline tools

Stop/disable ownership and listener first. Preserve the exact interrupted
checkout before any new checkout. Audit the correct channel, complete comment
thread pages, uploads/processing/private videos and any downstream notifications
manually. A missing/stale list entry is insufficient evidence of absence.

Use the reviewed checkout's Python/tools, without importing production pipelines:

```sh
python delivery_claims.py inspect
python delivery_claims.py reconcile --token ATTEMPT_TOKEN --decision delivered \
  --receipt REMOTE_ID --note 'Operator evidence: verified matching remote publication and channel'
# ONLY if non-delivery was established, not merely absent from a partial listing:
python delivery_claims.py reconcile --token ATTEMPT_TOKEN --decision not-delivered \
  --note 'Operator evidence: verified definitive non-delivery and checked complete remote state'
```

These commands make no API calls. Delivered reconciliation installs a receipt;
confirmed non-delivery permits a newly claimed attempt while retaining old
attempt and audit notes. Unknown delivery must remain blocked. Back up the ledger
before reconciliation; never delete/reset the DB or identities to enable retries.

After delivery reconciliation, use installed guard `finish` with the original
validated run env to preserve an interrupted workspace. If original env cannot
be restored, invoke its `archive_artifacts` helper explicitly on the preserved
workspace and correct run ID (safe allowlist only), then:

```sh
python /home/zeynel/.local/share/yt-hermes-runner/local_runner_guard.py reconcile \
  --run-id ORIGINAL_RUN_ID \
  --note 'Operator evidence: reviewed archive and reconciled all external side effects'
```

It requires an archive and no pending deliveries; records a durable note before
clearing active state. Original run-ID receipt is retained, so same-run replay
still fails. Only a NEW main job is eligible. Do not delete `active.json` manually.

## Limits and stop procedure

At-most-once attempts sacrifice automatic recovery to avoid double publication;
there is no distributed atomic transaction with YouTube. A crash between remote
success and receipt requires human reconciliation. Local filesystem/disk durability
is required; SQLite on unreliable/network storage is unsupported. Telegram previews
and non-YouTube writes are not deduplicated by the delivery ledger.

Trusted main code executes as the local user: hooks, labels, field allowlists and
safe mode are not a security sandbox against malicious main code or a compromised
Hermes binary. No model/provider diversity remains. Subscription inference, OAuth
and real runner protocol compatibility remain unverified until operator smoke.
An installed CLI protocol change deliberately fails closed.

Host-off/session-off means no local execution; schedules may queue and arrive late.
Existing schedule mode/DST selection is preserved, not an availability guarantee.
User-service boot behavior requires separately provisioned lingering/login; this
migration does not enable lingering. To stop, unset ownership, disable schedules,
drain jobs and stop the listener. Retain state/evidence. Never automatically roll
back to old paid/hosted workflows or restore obsolete secret names.
