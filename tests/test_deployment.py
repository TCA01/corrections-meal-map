from __future__ import annotations
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile
from copy import deepcopy

import pytest
import yaml

from deployment.state import (COMMIT_PATHS, decide, state_name_allowed, sanitized, restore, pack,
                              write_summary)
from deployment.audit import candidate_files, scan_text
from tests.test_web_bridge import bridge

ROOT = Path(__file__).resolve().parents[1]


def workflow(name):
    return yaml.load((ROOT / '.github/workflows' / name).read_text(encoding='utf-8'), Loader=yaml.BaseLoader)


def report(status='NO_CHANGES', published=False):
    return {'status': status, 'dry_run': False,
            'publication': {'published': published, 'dataset_version': 'new' if published else 'old'},
            'site': {'posts_checked': 10}, 'attachments': {'new': 2},
            'processing': {'auto_ready': 1, 'review': 1}, 'review': {'new_layout_count': 1}}


@pytest.mark.parametrize('name', ['daily-update.yml', 'deploy-pages.yml'])
def test_workflow_yaml_syntax(name):
    value = workflow(name)
    assert 'on' in value and 'jobs' in value and 'permissions' in value


def test_daily_schedule_manual_concurrency():
    value = workflow('daily-update.yml')
    assert value['on']['schedule'][0]['cron'] == '37 23 * * *'
    assert 'workflow_dispatch' in value['on']
    assert value['concurrency'] == {'group': 'corrections-daily-update', 'cancel-in-progress': 'false'}


def test_pages_official_actions_and_build_path():
    value = workflow('deploy-pages.yml')
    steps = value['jobs']['deploy']['steps']
    uses = [s.get('uses', '') for s in steps]
    assert 'actions/configure-pages@v5' in uses
    assert 'actions/upload-pages-artifact@v3' in uses
    assert 'actions/deploy-pages@v4' in uses
    upload = next(s for s in steps if s.get('uses', '').startswith('actions/upload-pages'))
    assert upload['with']['path'] == 'web/dist'
    assert value['permissions'] == {'contents': 'read', 'pages': 'write', 'id-token': 'write'}


def test_daily_python_node_setup_and_test_gates():
    steps = workflow('daily-update.yml')['jobs']['update']['steps']
    assert any(s.get('uses', '').startswith('actions/setup-python@') and s['with']['python-version'] == '3.11' for s in steps)
    assert any(s.get('uses', '').startswith('actions/setup-node@') and s['with']['node-version'] == '24' for s in steps)
    commands = '\n'.join(s.get('run', '') for s in steps)
    for required in ('pip install -r requirements.txt', 'python -m pytest', 'github_state.py validate', 'npm ci', 'npm run test', 'npm run build'):
        assert required in commands


def test_bot_commit_allowlist_no_raw_no_add_all():
    steps = workflow('daily-update.yml')['jobs']['update']['steps']
    script = next(s['run'] for s in steps if s.get('id') == 'commit')
    add = next(line.strip() for line in script.splitlines() if 'git add ' in line)
    assert add == 'git add -- ' + ' '.join(COMMIT_PATHS)
    assert 'git add -A' not in script and 'git add .' not in script
    assert 'raw/' not in script and 'github-actions[bot]' in script
    assert 'git push origin HEAD:main' in script


def test_daily_reusable_pages_link_and_review_only_guard():
    jobs = workflow('daily-update.yml')['jobs']
    assert jobs['deploy']['uses'] == './.github/workflows/deploy-pages.yml'
    assert "outputs.deploy == 'true'" in jobs['deploy']['if']
    assert jobs['deploy']['with']['ref'] == '${{ needs.update.outputs.commit_sha }}'


def test_workflows_no_embedded_credentials():
    for name in ('daily-update.yml', 'deploy-pages.yml'):
        assert scan_text((ROOT / '.github/workflows' / name).read_text(encoding='utf-8')) == []


def test_no_changes_no_timestamp_commit():
    queue = [{'review_id': '1', 'last_seen': 'yesterday'}]
    after = [{'review_id': '1', 'last_seen': 'today'}]
    assert decide(report(), 0, 'old', queue, {}, after, {}) == {'commit': False, 'deploy': False, 'status': 'NO_CHANGES'}


def test_no_changes_ignores_out_of_scope_state():
    assert not decide(report(), 0, 'old', [], {}, [], {'staff': {}})['commit']


def test_ready_commit_deploy():
    assert decide(report('SUCCESS', True), 0, 'old', [], {}, [], {})['deploy']


def test_partial_with_ready_can_deploy():
    assert decide(report('PARTIAL', True), 1, 'old', [], {}, [{'review_id': 'new'}], {})['deploy']


def test_review_only_state_commit_not_deploy():
    value = decide(report('PARTIAL'), 1, 'old', [], {}, [{'review_id': 'new'}], {})
    assert value['commit'] and not value['deploy']


def test_repeated_partial_no_empty_commit():
    assert not decide(report('PARTIAL'), 1, 'old', [], {}, [], {})['commit']


@pytest.mark.parametrize('status,exit_code', [('FATAL', 2), ('LOCKED', 3), ('PARTIAL', 0), ('SUCCESS', 1)])
def test_failure_or_exit_mismatch_rejected(status, exit_code):
    with pytest.raises(ValueError):
        decide(report(status), exit_code, 'old', [], {}, [], {})


def test_publication_version_mismatch_rejected():
    with pytest.raises(ValueError):
        decide(report('SUCCESS', True), 0, 'new', [], {}, [], {})


@pytest.mark.parametrize('name', ['../secret', '/secret', 'run/raw/1.xlsx', 'run/ready/../../secret', 'ops/update.lock', 'run/parsed/1.json'])
def test_archive_member_allowlist_rejects_unsafe(name):
    assert not state_name_allowed(name)


def test_audit_sanitizes_machine_paths_but_keeps_relative_provenance():
    value = sanitized({'local_path': 'data/ops/raw/test.xlsx', 'error': 'C:/Users/fixture/private.xlsx'})
    assert value['local_path'] == 'data/ops/raw/test.xlsx'
    assert value['error'] == '[redacted machine-specific diagnostic]'
    assert sanitized('https://www.corrections.go.kr/post/1') == 'https://www.corrections.go.kr/post/1'


def test_summary_readable_ready_transition():
    text = write_summary(report('PARTIAL', True), {'commit': True, 'deploy': True}, 415, 416)
    assert '415 → 416' in text and 'Dataset updated: YES' in text and 'NEW LAYOUT: 1' in text


def test_gitignore_actual_candidates_exclude_large_state(tmp_path):
    (tmp_path / '.gitignore').write_text((ROOT / '.gitignore').read_text(), encoding='utf-8')
    for name in ('data/production/raw/huge.xlsx', 'data/production/runs/old/ready/1.json', 'data/ops/raw/new.xlsx',
                 'data/github/state.json', 'web/public/web_data/manifest.json', '.venv/secret', 'tmp/test', 'source.py'):
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('{}', encoding='utf-8')
    names = [p.relative_to(tmp_path).as_posix() for p in candidate_files(tmp_path)]
    assert 'data/github/state.json' in names and 'web/public/web_data/manifest.json' in names and 'source.py' in names
    assert not any('raw/' in p or '/runs/' in p or p.startswith(('.venv/', 'tmp/')) for p in names)


def test_secret_scan_realistic_credential():
    assert scan_text('ghp_' + 'x' * 36) == ['github_token']
    assert scan_text('os.environ.get("KAKAO_REST_API_KEY")') == []


def test_pack_deterministic_and_restore_fresh_checkout(tmp_path, bridge):
    from dataclasses import replace
    from production.io import atomic_json, atomic_jsonl
    from production.web_bridge import WebDataBridge, tree_digest
    # Existing representative bridge fixture supplies real routed schema.
    _, run, _ = bridge.active_run()
    atomic_json(run / 'metadata.json', {'dataset_version': 'test-v1'})
    master = json.loads(bridge.settings.institutions_path.read_text(encoding='utf-8'))
    for item in master:
        item['aliases'] = []
        item['short_name'] = item['canonical_name']
    atomic_json(bridge.settings.institutions_path, master)
    bridge.build()
    bridge.sync()
    settings = bridge.settings
    atomic_jsonl(settings.project_root / 'data/ops/catalog/posts.jsonl', [])
    history = [{'post_id': '1', 'attachment_id': '1', 'old_sha256': 'old', 'new_sha256': 'new'}]
    atomic_jsonl(settings.project_root / 'data/catalog/attachment_history.jsonl', history)
    first = pack(settings)
    assert pack(settings)['archive_sha256'] == first['archive_sha256']
    target = tmp_path / 'fresh'
    import shutil
    shutil.copytree(settings.project_root / 'data/github', target / 'data/github')
    shutil.copytree(settings.project_root / 'web/public/web_data', target / 'web/public/web_data')
    target.mkdir(exist_ok=True)
    shutil.copyfile(settings.institutions_path, target / 'institutions.json')
    fresh = replace(settings, project_root=target, production_root=target / 'data/production', institutions_path=target / 'institutions.json')
    assert restore(fresh)['dataset_version'] == first['dataset_version']
    assert json.loads((target / 'data/catalog/attachment_history.jsonl').read_text(encoding='utf-8')) == history[0]
    assert tree_digest(target / 'web/public/web_data') == first['public_tree_sha256']
    with pytest.raises(ValueError, match='active local'):
        restore(fresh)


def test_pack_refuses_interrupted_transaction(tmp_path):
    from dataclasses import replace
    from config.settings import Settings
    path = tmp_path / 'data/ops/publication_transaction.json'
    path.parent.mkdir(parents=True)
    path.write_text('{}', encoding='utf-8')
    with pytest.raises(ValueError, match='transaction'):
        pack(replace(Settings(), project_root=tmp_path))


def test_restore_tampered_archive_rejected_before_writes(tmp_path):
    from dataclasses import replace
    from config.settings import Settings
    folder = tmp_path / 'data/github'
    folder.mkdir(parents=True)
    (folder / 'state.json').write_text(json.dumps({'archive_sha256': 'wrong'}), encoding='utf-8')
    (folder / 'state.zip').write_bytes(b'not a trusted archive')
    with pytest.raises(ValueError, match='hash mismatch'):
        restore(replace(Settings(), project_root=tmp_path, production_root=tmp_path / 'data/production'))
    assert not (tmp_path / 'data/production').exists()


def test_archive_actual_contains_no_raw_or_private_paths():
    with ZipFile(ROOT / 'data/github/state.zip') as archive:
        assert all(state_name_allowed(n) for n in archive.namelist())
        assert all(not scan_text(archive.read(n).decode('utf-8')) for n in archive.namelist())
