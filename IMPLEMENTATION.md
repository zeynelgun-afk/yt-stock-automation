# YouTube Hermes migration implementation evidence

Date: 2026-10-04. Worktree: `/home/zeynel/yt-hermes-migration`.
**Implemented and tested offline; activation and real inference are unverified.**
No commit/push/merge, GitHub mutation, runner registration, service start, production
pipeline, publishing, credential inspection or live inference/data API was performed.
Dependency packages/Python/uv were downloaded for the requested independent test venv.

## Current implementation snapshot after independent review fix

This is the implementation phase snapshot, not activation evidence. The latest
full offline suite is **136/136 passed, 4.108 seconds**. Earlier counts below are
historical stage results.

- Final-confirmation changes retain active quarantine after finish, even with a
  pipeline success marker. Clearing automatically requires a verified completed
  successful GitHub result matching repository, workflow, SHA, run ID and attempt;
  failed, cancelled, incomplete, mismatched and ambiguous outcomes remain blocked.
  This behavior was verified through mocked boundaries only.
- Review replay fix: start durably writes the permanent run receipt before active
  state. Reconciliation reconstructs a missing legacy receipt before writing its
  evidence note and clearing active state; existing receipts remain unchanged.
  Conflicting receipt identity fails closed. Archive and unresolved delivery
  requirements remain in force.
- Red stage: `28-replay-tombstone-red.log`, 23 runner tests executed with expected
  failures (16 failing subtests/assertions and 3 errors), including missing receipt
  after interrupted start and reconciliation losing the replay tombstone.
- Green stage: `29-replay-tombstone-green.log`, **23 runner tests passed**. Covers
  failures before/after durable writes, legacy receipt reconstruction, original
  receipt preservation, conflicting identity, replay rejection and unresolved
  quarantine retention.
- Final stage: `30-replay-tombstone-final-suite.log`, **136 tests passed** using
  `YT_OFFLINE_TESTS=1 /home/zeynel/.local/share/yt-hermes-runner/venv/bin/python -m unittest discover -s tests -v`.
- `31-replay-tombstone-diff-check.log`: `git diff --check` passed.
  No commits, remote/service calls or inference calls were made for this fix.

## Result

- `llm_transport.py` is the sole inference adapter: fixed subscription
  `openai-codex/gpt-6-astra`, stdin one-shot, safe mode, no tools, empty fresh
  temporary cwd, 180-second run budget, 195-second parent timeout, isolated
  application-secret-free environment. Strict JSON/protocol validation; no
  paid provider or fallback. Constructor compatibility arguments are ignored.
- ScriptGenerator `_chat`/`_providers` covers scripts, story selection, learning,
  outlier pattern extraction and ReplyWriter. Domain/script/reply validators,
  word correction limits, editorial publishing guards and live identity/comment
  limits remain. Removed paid key config/env/workflow wiring and status probe.
- BOTH video and comment delivery use durable SQLite attempt/receipt records
  outside checkout, synchronous FULL transactions and explicit fsync. Stable
  channel/event identities for uploads, channel/parent IDs for comments, atomic
  concurrent claims, receipt replay and additional-alias binding. Ambiguous
  insert/no ID remains unresolved until documented operator reconciliation.
- Upload `execute(num_retries=5)` was unsafe after timeout/5xx: changed to ZERO
  retries; no reconstructed automatic upload retry. Receipt precedes thumbnail
  work. Completed upload returns prior ID without another insert. Wrong channel
  or missing event identity prevents sending. Existing pre-upload history and
  editorial gates still run. Comment insertion also has zero retry.
- Staged production workflow requires `YT_EXECUTOR=local-hermes` and dedicated
  `yt-hermes` runner. Exact seven crons, mode choices, created-at/DST resolver,
  pipeline steps/concurrency and existing analytics persistence remain. Python
  uses `/home/zeynel/.local/share/yt-hermes-runner/venv`; pre-provisioned media tools
  replace apt. PR/push checks remain hosted and offline.
- New manual main-only dedicated-runner smoke has no production/data/notification
  secrets. `smoke_llm.py` uses supplied fictional facts and REAL ScriptGenerator
  plus ReplyWriter inference only; it is deliberately never executed/mocked as
  smoke in unit tests. Operator must run this before activation.
- New workflow/app YouTube env names: `YT_LOCAL_TOKEN_JSON` and
  `YT_LOCAL_CLIENT_SECRET_JSON`, including the read-only growth report/history/
  trend consumers. Actual GitHub secrets are unchanged here. Cutover must remove
  old token/client names and repository OPENROUTER_API_KEY secret, without
  revoking provider keys. Any still-present legacy Gemini/Groq repository secret
  names also require operator retirement to close historical fallback paths.
  Historical infra reruns are disabled under local
  ownership; first-attempt job guards reject replays locally.
- Installed-outside-checkout pre/post hook design in `ops/`: fixed repo/main/
  event/workflow/job allowlist, matching workflow/job revision, durable run-ID
  journal, pending delivery checks, final success marker, private fsynced atomic
  safe-artifact archive. Failure/crash/unknown outcome retains unresolved claim.
  Operator-only offline reconciliation records notes, preserving replay guards.
  Service example holds listener-lifetime flock and is not installed/started.

## Strict TDD evidence

The initial stages and their counts below are historical offline implementation
evidence, not the current activation status. Activation and real inference remain
unverified. The current full offline result is **136 tests passed**; the earlier
independent-review result of 127 tests is historical.

Final-confirmation behavior retains active state after finish and archives
`pending-confirmation`; a pipeline marker alone cannot clear it. Confirmation
requires GitHub completed success matching repository, workflow path, SHA, run ID
and attempt. Failed, cancelled, incomplete, mismatched and ambiguous results
remain blocked. These boundaries were tested with mocks, without live API calls.

Second-review interruption fix: start durably writes the permanent run-ID receipt
before the active claim. Operator reconciliation preserves an existing matching
receipt or reconstructs a missing legacy receipt from the original active claim
before clearing active state. Conflicting original identities fail closed without
overwriting the receipt. Tests cover interruption after the first durable write,
reconciliation interruption, same-run replay rejection and legacy active-only
recovery. Focused changes are confined to the runner guard, its tests and this
evidence document.

- `fix2-red.log`: expected failures reproduced before the implementation fix
  (18 tests, 11 failures including conflict subtests).
- `fix2-green.log`: 23 runner guard tests passed.
- `fix2-final-suite.log`: requested full offline suite, **136 tests passed**.
- `fix2-final-diff-check.log`: final `git diff --check` result.


Logs are preserved in `/home/zeynel/yt-migration-evidence`.
Tests use mocked inference/API boundaries, synthetic credentials and temporary
ledgers. Tests import an offline guard; real transport execution is forbidden.
Transport subprocess boundary tests opt out ONLY within mocks. Later temporary
work is directed to the evidence directory with TMPDIR.

| Stage | Red log / expected failure | Green log / result |
|---|---|---|
| Existing baseline | Before edits | `00-baseline.log`: **87 tests passed** |
| Hermes transport | `01-transport-red.log`: missing adapter/new contract failures | `02-transport-green.log`: 6 passed |
| Both delivery paths | `03-delivery-red.log`: missing claims and unsafe upload replay | `04-delivery-green.log`: 9 passed |
| Runner hooks | `05-hooks-red.log`: missing ops guard | `06-hooks-green.log`: 6 passed |
| Workflow/status/secrets/caller integration | `07-contract-red.log`: expected new-contract failures | `09-contract-green.log`: **114 passed** |
| Expanded event aliases | `10-alias-red.log`: new alias could be sent again | `12-alias-green.log`: 10 passed |
| Automatic main data commits and revision guard | `11-hook-revision-red.log`: overrestrictive SHA pin | `13-hook-revision-green.log`: 6 passed |
| Pending delivery blocks job success | `14-pending-delivery-hook-red.log`: marker wrongly allowed | `15-full-green.log`: **118 passed** |
| Operator delivery/job reconciliation | `16-reconcile-delivery-red.log`, `17-reconcile-job-red.log`: missing operations | `18-full-green.log`: **120 passed** |
| JSON overflow/unknown protocol fields | `19-strict-protocol-red.log`: overflow accepted | `20-strict-protocol-green.log`: 7 passed |
| Final full suite | — | `21-final-suite.log`: **121 passed, 5.674 seconds** |

`08-contract-green.log` is an intermediate FAILED integration run despite its
filename: it exposed the obsolete ProviderAccountError import in story_selector.
That import/catch was removed; `09-contract-green.log` is the passing result.
The initial exact-SHA pin was removed because weekly/daily data commits change
main; hooks retain fixed main/workflow/revision and first-attempt validation.

Historical verification before final-confirmation and replay fixes:

- `python -m unittest discover -s tests -v`: **121/121 passed** (87 baseline +
  34 new tests, with obsolete paid tests rewritten to the subscription contract).
- Real concurrent delivery test: four OS processes, exactly one claim winner.
- Failure tests: ambiguous upload/comment reopen/replay, no valid remote ID,
  fsync-before-send/receipt-after-send, stable alias replay, wrong identity,
  guard replay/context errors, absent success marker, pending delivery ledger,
  failed archive/missing workspace, credential file/symlink exclusion, explicit
  operator reconciliation retaining original attempts/receipts.
- `22-compile.log`: root, ops and test Python sources compile.
- `23-workflow-syntax.log`: all five workflow YAML files parse (PyYAML).
- `bash -n ops/runner-pre-job.sh ops/runner-post-job.sh`: passed.
- `24-diff-check.log`: `git diff --check` passed.

Python 3.12.15 venv was created with:

```sh
UV_CACHE_DIR=/home/zeynel/yt-migration-evidence/uv-cache \
UV_PYTHON_INSTALL_DIR=/home/zeynel/yt-migration-evidence/python \
/home/zeynel/yt-migration-evidence/tools/uv venv \
  /home/zeynel/.local/share/yt-hermes-runner/venv --python 3.12
UV_CACHE_DIR=/home/zeynel/yt-migration-evidence/uv-cache \
/home/zeynel/yt-migration-evidence/tools/uv pip install \
  --python /home/zeynel/.local/share/yt-hermes-runner/venv/bin/python -r requirements.txt
```

PyYAML was installed into the same venv solely for local workflow syntax checking.
No production dotenv was created or loaded. uv/Python cache/install artifacts are
under evidence; runtime deployment must retain that Python or recreate the venv.

## References read, without modification

- `/home/zeynel/ai-portfolio-hermes-migration/llm_transport.py`
- Reference `ops/local_runner_guard.py`, `ops/LOCAL_HERMES.md`, `ops/README.md`
- `/home/zeynel/.hermes/skills/safe-local-job-handoff/references/github-actions-local-hermes.md`
- Installed Hermes CLI parser/stream output/oneshot source, to inspect command and
  event contract without invoking Hermes or inspecting authentication.
- Project archive index and memory registry for historical context. Current clone
  code/tests determined implementation; historical live claims were not reverified.

## Activation belongs to the operator

Exact prerequisites, service/hook installation, secret-name cutover, old-job
pause/drain, real smoke, state reconciliation and stop/rollback boundaries are in
[ops/LOCAL_HERMES.md](ops/LOCAL_HERMES.md). Nothing in these tests proves real OAuth,
subscription inference, Actions hook environment compatibility, service availability,
GitHub activation or publication. No provider credentials were exported or revoked.

At-most-once claims deliberately trade unattended retry availability for protection
against duplicate uploads/comments. Remote success before receipt remains ambiguous;
only the operator can resolve it with evidence. Main/ref checks are not a sandbox
or remote-current-head attestation. Local host/session availability and delayed
GitHub jobs remain operational constraints. Telegram previews/other writes are
outside the YouTube delivery ledger. No paid/hosted automatic rollback is provided.
