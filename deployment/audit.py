"""Git ignore-aware candidate inventory and credential/privacy lint."""
from __future__ import annotations
import json
import re
import subprocess
import tempfile
from collections import defaultdict
from pathlib import Path
from zipfile import ZipFile, is_zipfile
from production.web_bridge import tree_digest

SECRET_PATTERNS = {
    'google_api_key': re.compile(r'AIza[0-9A-Za-z_-]{30,}'),
    'github_token': re.compile(r'(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{30,})'),
    'private_key': re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
    'bearer_credential': re.compile(r'Bearer\s+[A-Za-z0-9_.-]{20,}'),
    'assigned_credential': re.compile(r'''(?i)(?:password|api_key|token|secret)\s*[=:]\s*["'][A-Za-z0-9_./+-]{20,}["']'''),
    'private_windows_path': re.compile(r'(?i)(?:C:[\\/]+Users[\\/]+|E:[\\/]+workspace[\\/]+)'),
}
FIXTURE_PATH_LITERALS = {
    'tests/test_deployment.py': ('C:' + '/Users/' + 'fixture/private.xlsx',),
    'web/tests/adapter.test.ts': ('C:' + r'\\Users' + r'\\admin\\secret.xlsx',),
    'web/tests/contract.test.ts': ('E:' + r'\\workspace' + r'\\correction\\raw\\file.xlsx',),
}


def candidate_files(root):
    """Do not initialize the user's workspace or guess ignore pattern semantics."""
    root = root.resolve()
    with tempfile.TemporaryDirectory(prefix='corrections-git-audit-') as temp:
        git_dir = Path(temp) / 'git'
        subprocess.run(['git', 'init', '--bare', str(git_dir)], check=True, capture_output=True)
        common = ['git', '-c', 'core.quotepath=false', '--git-dir=' + str(git_dir), '--work-tree=' + str(root)]
        result = subprocess.run(common + ['ls-files', '--others', '--exclude-standard', '-z'],
                                check=True, stdout=subprocess.PIPE)
        files = {s.decode('utf-8') for s in result.stdout.split(b'\0') if s}
    # Already tracked ignored files are still commit candidates and must be audited.
    if (root / '.git').exists():
        tracked = subprocess.run(['git', '-C', str(root), 'ls-files', '-z'], check=True, stdout=subprocess.PIPE)
        files.update(s.decode('utf-8') for s in tracked.stdout.split(b'\0') if s)
    return [root / name for name in sorted(files) if (root / name).is_file()]


def scan_text(text):
    return [name for name, pattern in SECRET_PATTERNS.items() if pattern.search(text)]


def public_audit(root):
    from production.web_contract import validate_web_bundle
    from production.menu_lint import require_clean_public_menus
    folder = root / 'web/public/web_data'
    contract = validate_web_bundle(folder, expected_master_count=55)
    require_clean_public_menus(folder)
    findings = []
    for path in folder.rglob('*.json'):
        text = path.read_text(encoding='utf-8')
        issues = scan_text(text)
        if re.search(r'"(?:local_path|traceback|hostname|developer_username)"\s*:', text, re.I):
            issues.append('private_public_field')
        if issues:
            findings.append({'file': path.relative_to(root).as_posix(), 'issues': issues})
    return {'status': 'FAIL' if findings else 'PASS', 'contract': contract,
            'findings': findings, 'tree_sha256': tree_digest(folder)}


def audit(root):
    files = candidate_files(root)
    directories = defaultdict(int)
    rows, findings, fixture_literals = [], [], []
    for path in files:
        relative = path.relative_to(root).as_posix()
        size = path.stat().st_size
        rows.append({'file': relative, 'bytes': size})
        for depth in range(1, min(3, len(Path(relative).parts))):
            directories['/'.join(Path(relative).parts[:depth])] += size
        contents = []
        if relative == 'data/github/state.zip':
            with ZipFile(path) as archive:
                contents = [(relative + ':' + n, archive.read(n).decode('utf-8')) for n in archive.namelist()]
        elif path.suffix in ('.xlsx', '.xls'):
            if is_zipfile(path):
                with ZipFile(path) as workbook:
                    contents = [(relative + ':' + n, workbook.read(n).decode('utf-8', errors='replace'))
                                for n in workbook.namelist() if n.endswith(('.xml', '.rels'))]
            else:
                payload = path.read_bytes()
                contents = [(relative + ':binary-text', payload.decode('latin1') + '\n' + payload.decode('utf-16le', errors='ignore'))]
        elif path.suffix not in ('.xlsx', '.xls', '.png', '.jpg', '.ico', '.woff', '.woff2'):
            try:
                contents = [(relative, path.read_text(encoding='utf-8'))]
            except UnicodeDecodeError:
                findings.append({'file': relative, 'issues': ['uninspected_binary']})
        for name, content in contents:
            issues = scan_text(content)
            if issues:
                finding = {'file': name, 'issues': issues}
                # Deliberate negative-fixture strings, never an actual assigned credential.
                scrubbed = content
                for literal in FIXTURE_PATH_LITERALS.get(relative, ()):
                    scrubbed = scrubbed.replace(literal, '[intentional unsafe-path fixture]')
                if issues == ['private_windows_path'] and not scan_text(scrubbed):
                    fixture_literals.append(finding)
                else:
                    findings.append(finding)
        if path.is_symlink() or size > 50_000_000 or relative.startswith(('data/production/', 'data/ops/', 'data/raw/')):
            findings.append({'file': relative, 'issues': ['unsafe_or_large_commit_candidate']})
    public = public_audit(root)
    return {'status': 'PASS' if not findings and public['status'] == 'PASS' else 'FAIL',
            'file_count': len(rows), 'total_bytes': sum(r['bytes'] for r in rows),
            'largest_20_files': sorted(rows, key=lambda r: -r['bytes'])[:20],
            'largest_directories': sorted(directories.items(), key=lambda r: -r[1])[:20],
            'public_web_data_bytes': sum(p.stat().st_size for p in (root / 'web/public/web_data').rglob('*') if p.is_file()),
            'findings': findings, 'harmless_fixture_literals': fixture_literals, 'public_audit': public,
            'files': [r['file'] for r in rows]}
