"""Exercise the actual workflow commands against disposable local Git remotes."""

import os
from pathlib import Path
import shutil
import subprocess

import pytest
import yaml


WORKFLOW = yaml.safe_load(
    (Path(__file__).parents[1] / '.github/workflows/sync-upstream.yml').read_text()
)


def git(repo, *args):
    return subprocess.check_output(['git', '-C', str(repo), *args], text=True).strip()


def commit(repo, filename, content):
    path = repo / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    git(repo, 'add', filename)
    git(repo, 'commit', '-m', filename)
    return git(repo, 'rev-parse', 'HEAD')


@pytest.fixture
def repos(tmp_path, monkeypatch):
    monkeypatch.setenv('GIT_CONFIG_GLOBAL', os.devnull)
    monkeypatch.setenv('GIT_CONFIG_NOSYSTEM', '1')
    monkeypatch.setenv('GIT_AUTHOR_NAME', 'Sync test')
    monkeypatch.setenv('GIT_AUTHOR_EMAIL', 'test@example.invalid')
    monkeypatch.setenv('GIT_COMMITTER_NAME', 'Sync test')
    monkeypatch.setenv('GIT_COMMITTER_EMAIL', 'test@example.invalid')
    upstream = tmp_path / 'upstream'
    upstream.mkdir()
    git(upstream, 'init', '-b', 'master')
    commit(upstream, 'shared.txt', 'original\n')
    origin = tmp_path / 'origin.git'
    origin.mkdir()
    git(origin, 'init', '--bare')
    fork = tmp_path / 'fork'
    git(tmp_path, 'clone', str(upstream), str(fork))
    git(fork, 'switch', '-c', 'main')
    commit(fork, 'purifier.txt', '6 Pro support\n')
    git(fork, 'remote', 'set-url', 'origin', str(origin))
    git(fork, 'push', 'origin', 'main')
    return upstream, origin, fork


def run_step(repo, tmp_path, job, step_id, **values):
    step = next(s for s in WORKFLOW['jobs'][job]['steps'] if s.get('id') == step_id)
    runner_temp = tmp_path / 'runner'
    runner_temp.mkdir(exist_ok=True)
    env = os.environ | {
        'RUNNER_TEMP': str(runner_temp),
        'GITHUB_OUTPUT': str(tmp_path / 'output'),
        'GITHUB_STEP_SUMMARY': str(tmp_path / 'summary'),
    } | values
    result = subprocess.run(
        ['bash', '-c', step['run']], cwd=repo, env=env,
        text=True, capture_output=True,
    )
    return result


def prepare(repos, tmp_path):
    upstream, _, fork = repos
    result = run_step(fork, tmp_path, 'prepare', 'merge', UPSTREAM_URL=str(upstream))
    outputs = {}
    if result.returncode == 0:
        outputs = dict(line.split('=', 1) for line in (tmp_path / 'output').read_text().splitlines())
        artifact = tmp_path / 'runner/candidate'
        artifact.mkdir()
        shutil.copyfile(tmp_path / 'runner/candidate.bundle', artifact / 'candidate.bundle')
        git(fork, 'checkout', '--detach', outputs['base'])
    return result, outputs


def publish(repos, tmp_path, outputs):
    return run_step(
        repos[2], tmp_path, 'publish', 'publish',
        **{key.upper(): value for key, value in outputs.items()},
    )


def test_publish_preserves_patch_and_exact_tested_candidate(repos, tmp_path):
    upstream, origin, fork = repos
    upstream_sha = commit(upstream, 'upstream.txt', 'upstream update\n')
    base = git(origin, 'rev-parse', 'main')
    result, outputs = prepare(repos, tmp_path)
    assert result.returncode == 0, result.stderr
    assert outputs['changed'] == 'true'
    assert outputs['upstream'] == upstream_sha
    assert git(origin, 'rev-parse', 'main') == base
    result = publish(repos, tmp_path, outputs)
    assert result.returncode == 0, result.stderr
    assert git(origin, 'rev-parse', 'main') == outputs['candidate']
    assert git(origin, 'show', 'main:purifier.txt') == '6 Pro support'
    assert git(origin, 'show', 'main:upstream.txt') == 'upstream update'
    assert git(fork, 'rev-parse', 'HEAD') == base  # Publisher never checks out candidate code.


def test_no_changes_is_a_safe_noop(repos, tmp_path):
    result, outputs = prepare(repos, tmp_path)
    assert result.returncode == 0, result.stderr
    assert outputs['changed'] == 'false'
    assert outputs['candidate'] == outputs['base']
    assert publish(repos, tmp_path, outputs).returncode == 0


@pytest.mark.parametrize('workflow_change', [False, True])
def test_conflicts_and_workflow_changes_leave_main_unchanged(repos, tmp_path, workflow_change):
    upstream, origin, fork = repos
    if workflow_change:
        commit(upstream, '.github/workflows/example.yml', 'name: changed\n')
    else:
        commit(fork, 'shared.txt', 'fork change\n')
        git(fork, 'push', 'origin', 'main')
        commit(upstream, 'shared.txt', 'upstream change\n')
    base = git(origin, 'rev-parse', 'main')
    result, _ = prepare(repos, tmp_path)
    assert result.returncode != 0
    assert '::error::' in result.stdout
    assert git(origin, 'rev-parse', 'main') == base


def test_concurrent_main_update_is_preserved(repos, tmp_path):
    commit(repos[0], 'upstream.txt', 'upstream update\n')
    result, outputs = prepare(repos, tmp_path)
    assert result.returncode == 0, result.stderr
    newer = commit(repos[2], 'newer.txt', 'concurrent change\n')
    git(repos[2], 'push', 'origin', 'HEAD:main')
    result = publish(repos, tmp_path, outputs)
    assert result.returncode != 0
    assert 'main changed during validation' in result.stdout
    assert git(repos[1], 'rev-parse', 'main') == newer


@pytest.mark.parametrize('tamper', ['bundle', 'candidate'])
def test_modified_artifacts_or_candidate_are_rejected(repos, tmp_path, tamper):
    commit(repos[0], 'upstream.txt', 'upstream update\n')
    result, outputs = prepare(repos, tmp_path)
    assert result.returncode == 0, result.stderr
    if tamper == 'bundle':
        with (tmp_path / 'runner/candidate/candidate.bundle').open('ab') as bundle:
            bundle.write(b'tampered')
    else:
        outputs['candidate'] = outputs['base']
    result = publish(repos, tmp_path, outputs)
    assert result.returncode != 0
    assert git(repos[1], 'rev-parse', 'main') == outputs['base']


def test_only_successful_validation_can_reach_write_credentials():
    assert WORKFLOW['permissions'] == {'contents': 'read'}
    jobs = WORKFLOW['jobs']
    assert jobs['publish']['needs'] == ['prepare', 'validate', 'ha-config']
    assert jobs['publish']['permissions'] == {'contents': 'write'}
    assert all(not step.get('uses', '').startswith('./') for step in jobs['publish']['steps'])
