from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from config.settings import Settings
from production.io import atomic_json
from production.web_bridge import WebDataBridge, tree_digest
from operations.daily import EXIT_CODES

OPS_FILES = ('catalog/posts.jsonl', 'catalog/attachment_history.jsonl',
             'processed_sources.json', 'parser_drift.json', 'review_queue.json', 'health.json')
COMMIT_PATHS = ('data/github/state.zip', 'data/github/state.json',
                'data/github/review_queue.json', 'data/github/health.json', 'web/public/web_data')
MACHINE_PATH = re.compile(r'(?<![A-Za-z])[A-Za-z]:[\\/]|/(?:home|Users|workspace|tmp)/')


def sanitized(value):
    """Machine-specific diagnostic strings only; original local data stays untouched."""
    if isinstance(value, dict):
        return {k: sanitized(v) for k, v in value.items()}
    if isinstance(value, list):
        return [sanitized(v) for v in value]
    if isinstance(value, str) and MACHINE_PATH.search(value):
        return '[redacted machine-specific diagnostic]'
    return value


def portable_bytes(path):
    if path.suffix == '.jsonl':
        return ''.join(json.dumps(sanitized(json.loads(line)), ensure_ascii=False, sort_keys=True) + '\n'
                       for line in path.read_text(encoding='utf-8').splitlines() if line.strip()).encode()
    return json.dumps(sanitized(json.loads(path.read_text(encoding='utf-8'))),
                      ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()


def state_name_allowed(name):
    if '..' in Path(name).parts or '\\' in name or name.startswith('/'):
        return False
    if name == 'current.json' or name.startswith('ops/') and name[4:] in OPS_FILES:
        return True
    if name in ('run/excel_manifest.jsonl', 'run/metadata.json',
                'run/reports/excel_production_report.json', 'run/web_data/manifest.json', 'run/web_data/institutions.json'):
        return True
    return bool(re.fullmatch(r'run/(ready|review|failed)/[A-Za-z0-9_-]+\.json', name))


def validate(settings=None):
    bridge = WebDataBridge(settings)
    _, run, report = bridge.active_run()
    from production.pipeline import ProductionExcelPipeline
    ProductionExcelPipeline(bridge.settings)._validate_staging(run, report)
    bridge.validate(bridge.deploy_path)
    bridge.validate(bridge.settings.project_root / 'web/public/web_data')
    return report


def pack(settings=None):
    settings = settings or Settings()
    for relative in ('data/ops/update.lock', 'data/ops/publication_transaction.json',
                     'data/institutions/location_transaction.json'):
        if (settings.project_root / relative).exists():
            raise ValueError('unfinished or active transaction; do not pack')
    validate(settings)
    root = settings.project_root
    folder = root / 'data/github'
    folder.mkdir(parents=True, exist_ok=True)
    pointer, run, _ = WebDataBridge(settings).active_run()
    entries = {'current.json': (settings.production_root / 'current.json').read_bytes()}
    for relative in ('excel_manifest.jsonl', 'metadata.json', 'reports/excel_production_report.json',
                     'web_data/manifest.json', 'web_data/institutions.json'):
        entries['run/' + relative] = portable_bytes(run / relative)
    for route in ('ready', 'review', 'failed'):
        for path in sorted((run / route).glob('*.json')):
            entries[f'run/{route}/{path.name}'] = portable_bytes(path)
    for relative in OPS_FILES:
        path = root / 'data/ops' / relative
        # The existing crawler uses Settings.attachment_history_path (data/catalog),
        # even when its posts catalog is under data/ops. Preserve that history too.
        if relative == 'catalog/attachment_history.jsonl' and (root / 'data/catalog/attachment_history.jsonl').exists():
            path = root / 'data/catalog/attachment_history.jsonl'
        if path.exists():
            entries['ops/' + relative] = portable_bytes(path)
    if 'ops/catalog/posts.jsonl' not in entries:
        raise ValueError('operational catalog required; seed it before packing')
    temp = folder / 'state.zip.pending'
    with ZipFile(temp, 'w', compression=ZIP_DEFLATED, compresslevel=9) as archive:
        for name, content in sorted(entries.items()):
            info = ZipInfo(name, date_time=(2020, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            archive.writestr(info, content)
    os.replace(temp, folder / 'state.zip')
    atomic_json(folder / 'state.json', {'schema_version': '1', 'dataset_version': pointer['dataset_version'],
                'archive_sha256': hashlib.sha256((folder / 'state.zip').read_bytes()).hexdigest(),
                'public_tree_sha256': tree_digest(root / 'web/public/web_data'),
                'members': len(entries), 'raw_files_included': 0})
    for name in ('review_queue.json', 'health.json'):
        data = entries.get('ops/' + name, b'[]' if name.startswith('review') else b'{}')
        atomic_json(folder / name, json.loads(data))
    return json.loads((folder / 'state.json').read_text(encoding='utf-8'))


def restore(settings=None):
    """Fresh-checkout bootstrap only; refuses to overwrite any active local run."""
    settings = settings or Settings()
    root = settings.project_root
    if (settings.production_root / 'current.json').exists():
        raise ValueError('active local production exists; restore is for a fresh checkout')
    folder = root / 'data/github'
    metadata = json.loads((folder / 'state.json').read_text(encoding='utf-8'))
    if hashlib.sha256((folder / 'state.zip').read_bytes()).hexdigest() != metadata['archive_sha256']:
        raise ValueError('state archive hash mismatch')
    if tree_digest(root / 'web/public/web_data') != metadata['public_tree_sha256']:
        raise ValueError('public/state mismatch')
    with ZipFile(folder / 'state.zip') as archive:
        names = archive.namelist()
        if len(set(names)) != len(names) or len(names) != metadata['members']:
            raise ValueError('duplicate/missing archive members')
        if any(not state_name_allowed(n) for n in names) or sum(i.file_size for i in archive.infolist()) > 300_000_000:
            raise ValueError('unsafe or oversized state archive')
        pointer = json.loads(archive.read('current.json'))
        version = pointer['dataset_version']
        if not re.fullmatch(r'[A-Za-z0-9+_.-]+', version) or pointer['run_path'] != 'runs/' + version or version != metadata['dataset_version']:
            raise ValueError('invalid state pointer')
        run = settings.production_root / pointer['run_path']
        if run.exists() or (root / 'data/ops/catalog/posts.jsonl').exists():
            raise ValueError('restore destinations already exist')
        for name in names:
            if name == 'current.json':
                continue
            destination = run / name[4:] if name.startswith('run/') else root / 'data' / name
            if name == 'ops/catalog/attachment_history.jsonl':
                destination = root / 'data/catalog/attachment_history.jsonl'
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(archive.read(name))
    shutil.copytree(root / 'web/public/web_data/menus', run / 'web_data/menus')
    shutil.copytree(root / 'web/public/web_data', settings.production_root / 'deploy/web_data')
    atomic_json(settings.production_root / 'current.json', pointer)
    try:
        validate(settings)
    except BaseException:
        (settings.production_root / 'current.json').unlink()
        raise
    return pointer


def review_identity(queue):
    return [{k: v for k, v in item.items() if k != 'last_seen'} for item in queue]


def decide(report, exit_code, before_version, before_review, before_processed, after_review, after_processed):
    status = report['status']
    if report.get('dry_run') or status not in ('SUCCESS', 'NO_CHANGES', 'PARTIAL') or EXIT_CODES[status] != exit_code:
        raise ValueError('fatal/locked/dry/stale report or exit mismatch; no commit/deploy')
    published = report['publication']['published']
    changed = report['publication']['dataset_version'] != before_version
    if changed != published:
        raise ValueError('publication flag/version mismatch')
    state_changed = review_identity(before_review) != review_identity(after_review) or before_processed != after_processed
    if status == 'NO_CHANGES':
        if published:
            raise ValueError('NO_CHANGES contradicts publication')
        return {'commit': False, 'deploy': False, 'status': status}
    return {'commit': published or state_changed, 'deploy': published, 'status': status}


def write_summary(report, decision, before_ready, after_ready):
    return (f"## Corrections Daily Update\n\nStatus: {report['status']}\n\n"
            f"Checked posts: {report['site']['posts_checked']}\n\nNew attachments: {report['attachments']['new']}\n\n"
            f"AUTO READY: {report['processing']['auto_ready']} / REVIEW: {report['processing']['review']}\n\n"
            f"NEW LAYOUT: {report['review']['new_layout_count']}\n\nDataset updated: {'YES' if decision['deploy'] else 'NO'}\n\n"
            f"READY documents: {before_ready} → {after_ready}\n\nState commit: {'YES' if decision['commit'] else 'NO'}\n")


def run_daily(settings=None):
    settings = settings or Settings()
    root = settings.project_root
    def read(relative, default):
        path = root / relative
        return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default
    before = read('data/production/current.json', {})['dataset_version']
    before_public_hash = tree_digest(root / 'web/public/web_data')
    queue = read('data/ops/review_queue.json', [])
    processed = read('data/ops/processed_sources.json', {})
    ready = read('web/public/web_data/manifest.json', {})['stats']['structured_documents']
    # Runner-only latest report: a LOCKED run must not reuse a stale success.
    (root / 'data/ops/latest_report.json').unlink(missing_ok=True)
    result = subprocess.run([os.sys.executable, 'scripts/daily_update.py'], cwd=root)
    report = read('data/ops/latest_report.json', {})
    if not report:
        raise ValueError('no fresh daily report; no commit/deploy')
    try:
        decision = decide(report, result.returncode, before, queue, processed,
                          read('data/ops/review_queue.json', []), read('data/ops/processed_sources.json', {}))
    except ValueError:
        if os.environ.get('GITHUB_STEP_SUMMARY'):
            with open(os.environ['GITHUB_STEP_SUMMARY'], 'a', encoding='utf-8') as handle:
                handle.write('## Corrections Daily Update\n\nFATAL/LOCKED or inconsistent result; previous Pages site retained.\n')
        raise
    validate(settings)
    if not decision['deploy'] and tree_digest(root / 'web/public/web_data') != before_public_hash:
        raise ValueError('non-publication run changed served data; no commit/deploy')
    if decision['commit']:
        pack(settings)
    after_ready = read('web/public/web_data/manifest.json', {})['stats']['structured_documents']
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a', encoding='utf-8') as handle:
            handle.write(write_summary(report, decision, ready, after_ready))
    if os.environ.get('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'], 'a', encoding='utf-8') as handle:
            handle.write(f"commit={str(decision['commit']).lower()}\ndeploy={str(decision['deploy']).lower()}\n")
    return decision
