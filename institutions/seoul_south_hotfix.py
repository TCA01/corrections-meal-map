"""Two user-supplied official-address geocoding references, not official markers."""
from copy import deepcopy
import hashlib

from config.settings import Settings
from operations.state import RunLock
from production.io import atomic_json
from production.validation import read_json
from production.web_bridge import WebDataBridge, tree_digest
from .geocoding import timestamp
from .location_validation import normalized_address, validate_location, duplicate_coordinates
from .location_pipeline import apply_location_master, recover_location_publication, location_report

REFERENCES = {
    'KR_CORR_SEOUL_SOUTHERN_DETENTION': ('서울특별시 구로구 금오로 865', 37.4771593, 126.8371928),
    'KR_CORR_SEOUL_SOUTHERN_PRISON': ('서울특별시 구로구 금오로 867', 37.4770251553096, 126.837830132687),
}


def refresh_portable_public_hash(settings=None):
    """Keep the newest committed operational archive; change only its public hash."""
    settings = settings or Settings()
    folder = settings.project_root / 'data/github'
    path = folder / 'state.json'
    if not path.exists():
        return
    state = read_json(path)
    if hashlib.sha256((folder / 'state.zip').read_bytes()).hexdigest() != state['archive_sha256']:
        raise ValueError('portable archive integrity mismatch')
    if state['dataset_version'] != read_json(settings.production_root / 'current.json')['dataset_version']:
        raise ValueError('portable/current dataset mismatch')
    state['public_tree_sha256'] = tree_digest(settings.project_root / 'web/public/web_data')
    atomic_json(path, state)


def reassess(master, audit):
    updated, evidence = deepcopy(master), deepcopy(audit)
    if len(updated) != 55 or len({i['institution_id'] for i in updated}) != 55:
        raise ValueError('expected canonical 55-institution master')
    by_id = {row['institution_id']: row for row in evidence}
    if set(by_id) != {i['institution_id'] for i in updated}:
        raise ValueError('master/audit identity mismatch')
    for institution_id, (address, lat, lon) in REFERENCES.items():
        institution = next(i for i in updated if i['institution_id'] == institution_id)
        if normalized_address(institution['address']) != address:
            raise ValueError('official physical address differs from reference')
        candidate = {'latitude': lat, 'longitude': lon, 'returned_address': address,
                     'query': address, 'official': False,
                     'provider': 'user_supplied_address_geocoding_reference', 'source_url': None,
                     'precision': 'institution_marker_or_full_road_address',
                     'evidence': 'user_supplied_road_address_geocoding_result',
                     'external_geocoder_called': False}
        validation = validate_location(institution, candidate)
        if validation['status'] != 'PASS':
            raise ValueError('reference coordinate/address validation failed')
        candidate['validation'] = validation
        row = by_id[institution_id]
        if 'previous_location_evidence' not in row:
            row['previous_location_evidence'] = deepcopy(row)
        row.update(latitude=lat, longitude=lon, status='GEOCODED', location_status='GEOCODED',
                   location_source='official_address_geocoding', location_source_url=None,
                   provider=candidate['provider'], location_confidence='address_match_user_reference',
                   geocoding_query=address, returned_address=address, geocoded_at=None,
                   evaluated_at=timestamp(), geocoding_result_timestamp_unknown=True,
                   coordinate_reference_source='user_request_phase_4b_1', external_geocoder_called=False,
                   official_address_source_url=institution['source_url'],
                   validation=validation, candidates=[candidate])
        institution['latitude'], institution['longitude'] = lat, lon
    for old, new in zip(master, updated):
        if {k: v for k, v in old.items() if k not in ('latitude', 'longitude')} != {
            k: v for k, v in new.items() if k not in ('latitude', 'longitude')}:
            raise ValueError('non-coordinate metadata change')
        if old['institution_id'] not in REFERENCES and old != new:
            raise ValueError('unrelated institution changed')
    if duplicate_coordinates(evidence):
        raise ValueError('duplicate accepted coordinates')
    return updated, evidence


def fingerprint(settings, bridge):
    pointer, run, _ = bridge.active_run()
    frontend = settings.project_root / 'web/public/web_data'
    return {'current': pointer, 'immutable_run_sha256': tree_digest(run),
            'menus': {name: tree_digest(root / 'menus') for name, root in
                      [('run', run / 'web_data'), ('deploy', bridge.deploy_path), ('frontend', frontend)]},
            'manifests': {name: hashlib.sha256((root / 'manifest.json').read_bytes()).hexdigest()
                          for name, root in [('run', run / 'web_data'), ('deploy', bridge.deploy_path), ('frontend', frontend)]}}


def apply_hotfix():
    settings = Settings()
    root = settings.institutions_path.parent
    with RunLock(settings.project_root / 'data/ops/update.lock', settings.ops_lock_stale_seconds):
        bridge = WebDataBridge(settings)
        recover_location_publication(settings, bridge)
        bridge.validate(bridge.deploy_path)
        bridge.validate(settings.project_root / 'web/public/web_data')
        before = fingerprint(settings, bridge)
        master, audit = read_json(settings.institutions_path), read_json(root / 'location_audit.json')
        updated, evidence = reassess(master, audit)
        apply_location_master(settings, bridge, master, updated)
        after = fingerprint(settings, bridge)
        if before != after:
            raise ValueError('hotfix changed immutable run, current pointer, menus or manifests')
        ready_ids = {r['institution_id'] for r in read_json(bridge.deploy_path / 'manifest.json')['institutions']}
        report = location_report(evidence, [], ready_ids)
        report.update(applied=True, public_institutions='PASS', web_sync='PASS', menu_data_unchanged='PASS',
                      dataset_version=before['current']['dataset_version'], fingerprints_before=before,
                      fingerprints_after=after, phase='4B.1')
        atomic_json(root / 'location_audit.json', evidence)
        atomic_json(root / 'location_review.json', [r for r in evidence if r['status'] in ('REVIEW', 'UNRESOLVED')])
        atomic_json(root / 'institutions_location_candidate.json', updated)
        atomic_json(root / 'location_report.json', report)
        atomic_json(root / 'seoul_south_geocoding.json', {
            'phase': '4B.1', 'coordinate_source_policy': 'user_supplied_official_address_geocoding_reference_not_official_coordinates',
            'external_geocoder_called': False, 'locations': [r for r in evidence if r['institution_id'] in REFERENCES],
            'report': report})
        refresh_portable_public_hash(settings)
        return report
