#!/usr/bin/env python3
"""Install outside checkout; stdlib-only runner hooks, no credentials.

The listener must hold flock for its lifetime. The post-job hook archives evidence
and retains pending confirmation; only a completed public GitHub run can resolve
it automatically. No network in finish, no polling for its own run. Never expire.
"""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import re
import sqlite3
import tarfile
from urllib.request import Request, urlopen

REPOSITORY = 'zeynelgun-afk/yt-stock-automation'
DEFAULT_STATE = Path.home()/'.local/state/yt-hermes-runner/jobs'
WORKFLOWS = {
    'US Stock Market Daily YouTube Automation': ('youtube_auto.yml', 'build-and-generate', {'schedule','workflow_dispatch'}),
    'YouTube Local Hermes Smoke': ('local-hermes-smoke.yml', 'inference-smoke', {'workflow_dispatch'}),
}
SAFE_ARTIFACTS = (
    'output/editorial_decision.json', 'output/editorial_story.json',
    'output/editorial_selection.json', 'output/editorial_publication.json',
    'output/editorial_provider_status.json', 'output/llm_smoke.json',
    'reports/channel-status.json', 'reports/channel-status.md',
    'reports/growth-experiment.json', 'reports/growth-experiment.md',
    'reports/small-channel-breakouts.json', 'reports/small-channel-breakouts.md',
    'data/channel_learnings.json',
)


def validate_context(env, root):
    rule = WORKFLOWS.get(env.get('GITHUB_WORKFLOW'))
    sha = env.get('GITHUB_SHA','')
    if (not rule or env.get('GITHUB_REPOSITORY') != REPOSITORY
            or env.get('GITHUB_REF') != 'refs/heads/main'
            or env.get('GITHUB_EVENT_NAME') not in rule[2]
            or env.get('GITHUB_JOB') != rule[1]
            or not re.fullmatch(r'[1-9][0-9]*',env.get('GITHUB_RUN_ID',''))
            or env.get('GITHUB_RUN_ATTEMPT') != '1'
            or not re.fullmatch(r'[0-9a-f]{40}',sha)
            or env.get('GITHUB_WORKFLOW_SHA') != sha
            or env.get('GITHUB_WORKFLOW_REF') != f'{REPOSITORY}/.github/workflows/{rule[0]}@refs/heads/main'):
        raise RuntimeError('Unapproved local runner context')


def sync_directory(path):
    fd = os.open(path,os.O_RDONLY | os.O_DIRECTORY)
    try: os.fsync(fd)
    finally: os.close(fd)


@contextmanager
def locked(root):
    root = Path(root)
    if root.is_symlink(): raise RuntimeError('Unsafe state directory')
    root.mkdir(parents=True,exist_ok=True,mode=0o700)
    with (root/'journal.lock').open('a') as handle:
        os.chmod(root/'journal.lock',0o600)
        fcntl.flock(handle,fcntl.LOCK_EX)
        yield root


def atomic_json(path,data):
    tmp = path.with_suffix('.tmp')
    with tmp.open('w') as handle:
        os.chmod(tmp,0o600)
        json.dump(data,handle,indent=2); handle.flush(); os.fsync(handle.fileno())
    tmp.replace(path); sync_directory(path.parent)


def check_deliveries(root):
    # The installed hooks use the same fixed sibling DB as production workflow.
    # Never create a ledger during the read-only safety check.
    path = Path(root).parent/'delivery.sqlite'
    if path.is_symlink(): raise RuntimeError('Unsafe delivery ledger')
    if not path.exists(): return  # a new installation has not attempted a send
    try:
        with sqlite3.connect(path.absolute().as_uri()+'?mode=ro',uri=True) as db:
            pending = db.execute("SELECT 1 FROM attempts WHERE status='attempted' LIMIT 1").fetchone()
        if pending: raise RuntimeError('Unresolved delivery; operator reconciliation required')
    except sqlite3.Error:
        raise RuntimeError('Cannot verify delivery ledger; fail closed') from None


def start(root,env):
    validate_context(env,root)
    with locked(root) as root:
        check_deliveries(root)
        if (root/'active.json').exists():
            prior = json.loads((root/'active.json').read_text())
            if prior.get('run_id') == env['GITHUB_RUN_ID']:
                raise RuntimeError('Run already attempted; replay forbidden')
            confirm_locked(root, prior.get('run_id'))
        receipt = root/(env['GITHUB_RUN_ID']+'.json')
        if receipt.exists(): raise RuntimeError('Run already attempted; replay forbidden')
        attempt = dict(run_id=env['GITHUB_RUN_ID'],attempt=env['GITHUB_RUN_ATTEMPT'],
                       repository=REPOSITORY,workflow_path=f'.github/workflows/{WORKFLOWS[env["GITHUB_WORKFLOW"]][0]}',
                       workflow=env['GITHUB_WORKFLOW'],job=env['GITHUB_JOB'],sha=env['GITHUB_SHA'],
                       started_at=datetime.now(timezone.utc).isoformat(),status='attempted')
        # Persist the replay tombstone before exposing the active claim.
        atomic_json(receipt,attempt)
        atomic_json(root/'active.json',attempt)


def owned_attempt(root,env):
    active = root/'active.json'
    if not active.is_file(): raise RuntimeError('Missing active job claim')
    attempt = json.loads(active.read_text())
    if any(attempt.get(k) != env.get(v) for k,v in
           [('run_id','GITHUB_RUN_ID'),('attempt','GITHUB_RUN_ATTEMPT'),('sha','GITHUB_SHA'),
            ('workflow','GITHUB_WORKFLOW'),('job','GITHUB_JOB')]):
        raise RuntimeError('Attempt ownership mismatch')
    return attempt


def mark_success(root,env):
    validate_context(env,root)
    with locked(root) as root:
        attempt = owned_attempt(root,env)
        check_deliveries(root)
        atomic_json(root/(env['GITHUB_RUN_ID']+'-success.json'), attempt)


def archive_artifacts(root,workspace,run_id):
    if not workspace.is_dir() or workspace.is_symlink(): raise RuntimeError('Missing/unsafe workspace')
    archive = root/(run_id+'-artifacts.tar.gz'); tmp = archive.with_suffix('.tmp')
    with tmp.open('wb') as handle:
        os.chmod(tmp,0o600)
        with tarfile.open(fileobj=handle,mode='w:gz') as tar:
            for relative in SAFE_ARTIFACTS:
                path = workspace/relative
                if not path.is_file() or path.is_symlink(): continue
                # Reject symlinked parents and hardlinks as well as leaf links.
                if any(p.is_symlink() for p in path.parents if p != workspace.parent): continue
                if path.stat().st_nlink != 1: continue
                tar.add(path,arcname=relative,recursive=False)
        handle.flush(); os.fsync(handle.fileno())
    tmp.replace(archive); sync_directory(root)
    return archive


def finish(root,env):
    validate_context(env,root)
    with locked(root) as root:
        attempt = owned_attempt(root,env)
        if not env.get('GITHUB_WORKSPACE'): raise RuntimeError('Missing workspace')
        archive = archive_artifacts(root,Path(env['GITHUB_WORKSPACE']),env['GITHUB_RUN_ID'])
        marker = root/(env['GITHUB_RUN_ID']+'-success.json')
        success = marker.is_file() and json.loads(marker.read_text()) == attempt
        if success: check_deliveries(root)
        attempt.update(status='pending-confirmation' if success else 'unresolved',archive=archive.name,
                       finished_at=datetime.now(timezone.utc).isoformat())
        atomic_json(root/(env['GITHUB_RUN_ID']+'.json'),attempt)
        atomic_json(root/'active.json',attempt)
        if not success:
            raise RuntimeError('Job did not reach final success marker; reconciliation required')


def fetch_run(run_id):
    """One credential-free public GET; bounded timeout/body, sanitized failures."""
    if not isinstance(run_id, str) or not re.fullmatch(r'[1-9][0-9]*', run_id):
        raise RuntimeError('Invalid confirmation run ID')
    request = Request(f'https://api.github.com/repos/{REPOSITORY}/actions/runs/{run_id}',
                      headers={'Accept':'application/vnd.github+json',
                               'User-Agent':'yt-local-runner-guard'})
    try:
        with urlopen(request, timeout=10) as response:
            body = response.read(1_048_577)
        if len(body) > 1_048_576: raise ValueError('Oversized response')
        return json.loads(body)
    except Exception:
        raise RuntimeError('Cannot verify GitHub run; fail closed') from None


def confirm_locked(root,run_id):
    """Caller holds journal lock; never trust a pipeline marker alone."""
    if not isinstance(run_id,str) or not re.fullmatch(r'[1-9][0-9]*',run_id):
        raise RuntimeError('Invalid confirmation run ID')
    active = root/'active.json'
    if not active.is_file(): raise RuntimeError('No pending job')
    attempt = json.loads(active.read_text())
    if attempt.get('run_id') != run_id or attempt.get('status') != 'pending-confirmation':
        raise RuntimeError('Job is not pending confirmation; reconciliation required')
    rule = WORKFLOWS.get(attempt.get('workflow'))
    if (not rule or attempt.get('repository') != REPOSITORY
            or attempt.get('workflow_path') != f'.github/workflows/{rule[0]}'
            or attempt.get('job') != rule[1] or attempt.get('attempt') != '1'
            or not re.fullmatch(r'[0-9a-f]{40}',attempt.get('sha',''))):
        raise RuntimeError('Invalid pending job identity')
    marker = root/(run_id+'-success.json')
    # finish adds outcome metadata; marker must match the original start claim.
    original = {k:v for k,v in attempt.items() if k not in ('archive','finished_at')}
    original['status'] = 'attempted'
    if not marker.is_file() or json.loads(marker.read_text()) != original:
        raise RuntimeError('Missing/mismatched pipeline completion marker')
    archive = root/(run_id+'-artifacts.tar.gz')
    if attempt.get('archive') != archive.name or not archive.is_file() or archive.is_symlink():
        raise RuntimeError('Missing/unsafe archived job evidence')
    check_deliveries(root)
    try:
        run = fetch_run(run_id)
    except Exception:
        raise RuntimeError('Cannot verify GitHub run; fail closed') from None
    if (not isinstance(run,dict) or type(run.get('id')) is not int
            or type(run.get('run_attempt')) is not int
            or run.get('id') != int(run_id) or run.get('run_attempt') != int(attempt['attempt'])
            or run.get('head_sha') != attempt['sha']
            or not isinstance(run.get('repository'),dict)
            or run['repository'].get('full_name') != REPOSITORY
            or run.get('path') != attempt['workflow_path']
            or run.get('status') != 'completed' or run.get('conclusion') != 'success'):
        raise RuntimeError('GitHub run is not verified completed success; fail closed')
    check_deliveries(root)
    attempt.update(status='success',confirmed_at=datetime.now(timezone.utc).isoformat())
    atomic_json(root/(run_id+'.json'),attempt)
    active.unlink(); sync_directory(root)


def confirm(root,run_id):
    with locked(root) as root:
        confirm_locked(root,run_id)


def reconcile(root,run_id,note):
    """Operator-only job resolution. Preserve run receipt, never enable replay."""
    if not re.fullmatch(r'[1-9][0-9]*',run_id) or not isinstance(note,str) or len(note.strip()) < 20:
        raise RuntimeError('Run ID and explicit operator evidence note required')
    with locked(root) as root:
        check_deliveries(root)
        active = root/'active.json'
        if not active.is_file(): raise RuntimeError('No unresolved job')
        attempt = json.loads(active.read_text())
        if attempt['run_id'] != run_id: raise RuntimeError('Wrong unresolved job')
        # Crash may have prevented the post-hook archive. Require preserved
        # evidence before clearing the job; never archive an unknown checkout.
        archive = root/(run_id+'-artifacts.tar.gz')
        if not archive.is_file() or archive.is_symlink():
            raise RuntimeError('Preserve exact interrupted workspace artifacts before reconciliation')
        receipt = root/(run_id+'.json')
        if receipt.exists():
            try:
                preserved = json.loads(receipt.read_text())
            except (OSError, ValueError):
                raise RuntimeError('Conflicting run receipt; fail closed') from None
            identity = ('run_id','attempt','repository','workflow_path','workflow','job','sha','started_at')
            if (not isinstance(preserved,dict)
                    or any(k not in attempt or preserved.get(k) != attempt[k] for k in identity)):
                raise RuntimeError('Conflicting run receipt; fail closed')
        else:
            # Recover legacy active-only claims using their original identity,
            # never the current operator environment or a new start timestamp.
            atomic_json(receipt,attempt)
        receipt = root/(run_id+'.json')
        if receipt.exists():
            original = json.loads(receipt.read_text())
            identity = ('run_id','attempt','repository','workflow_path','workflow','job','sha','started_at')
            if not isinstance(original,dict) or any(original.get(k) != attempt.get(k) for k in identity):
                raise RuntimeError('Conflicting run receipt; reconciliation required')
        else:
            # Recover legacy active-before-receipt interruptions. A failed write
            # must retain active quarantine; existing receipts remain untouched.
            atomic_json(receipt,attempt)
        atomic_json(root/(run_id+'-reconciliation.json'),dict(attempt=attempt,note=note.strip(),
                    recorded_at=datetime.now(timezone.utc).isoformat()))
        active.unlink(); sync_directory(root)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('command',choices=['start','finish','mark-success','plan','reconcile','confirm'])
    parser.add_argument('--state',default=str(DEFAULT_STATE))
    parser.add_argument('--run-id')
    parser.add_argument('--note')
    args = parser.parse_args()
    if args.command == 'plan':
        print(json.dumps(dict(repository=REPOSITORY,workflows=sorted(WORKFLOWS),state=args.state,
                              historical_replay=False,safe_artifacts=SAFE_ARTIFACTS)))
    elif args.command == 'start': start(args.state,os.environ)
    elif args.command == 'finish': finish(args.state,os.environ)
    elif args.command == 'mark-success': mark_success(args.state,os.environ)
    elif args.command == 'confirm': confirm(args.state,args.run_id or '')
    else: reconcile(args.state,args.run_id or '',args.note or '')


if __name__ == '__main__': main()
