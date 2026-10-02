from copy import deepcopy
from pathlib import Path
import pytest
from production.validation import read_json
from institutions.seoul_south_hotfix import reassess, REFERENCES

ROOT = Path(__file__).resolve().parents[1]


def baseline():
    master = read_json(ROOT / 'data/institutions/institutions.json')
    audit = [{'institution_id': i['institution_id'], 'official_address': i['address'],
              'latitude': i['latitude'], 'longitude': i['longitude'], 'status': 'VERIFIED'} for i in master]
    for i in master:
        if i['institution_id'] in REFERENCES:
            i['latitude'] = i['longitude'] = None
    return master, audit


def test_only_two_coordinates_change_without_mutating_inputs():
    master, audit = baseline()
    original = deepcopy(master)
    updated, rows = reassess(master, audit)
    assert master == original
    assert sum(i != j for i, j in zip(master, updated)) == 2
    for i, j in zip(master, updated):
        assert {k: v for k, v in i.items() if k not in ('latitude', 'longitude')} == {
            k: v for k, v in j.items() if k not in ('latitude', 'longitude')}
    assert sum(i['latitude'] is not None for i in updated) == 55
    for row in rows:
        if row['institution_id'] in REFERENCES:
            assert row['status'] == row['location_status'] == 'GEOCODED'
            assert row['location_source'] == 'official_address_geocoding'
            assert row['external_geocoder_called'] is False
            assert row['candidates'][0]['official'] is False
            assert row['geocoded_at'] is None
            assert row['validation']['status'] == 'PASS'


def test_reference_cannot_override_changed_official_address():
    master, audit = baseline()
    next(i for i in master if i['institution_id'] in REFERENCES)['address'] = '서울특별시 구로구 금오로 999'
    with pytest.raises(ValueError, match='address differs'):
        reassess(master, audit)


def test_reference_does_not_erase_previous_duplicate_marker_evidence():
    master, audit = baseline()
    row = next(r for r in audit if r['institution_id'] in REFERENCES)
    row.update(status='REVIEW', candidates=[{'latitude': 37.4825248, 'longitude': 126.8317231, 'official': True}])
    _, rows = reassess(master, audit)
    updated = next(r for r in rows if r['institution_id'] == row['institution_id'])
    assert updated['previous_location_evidence'] == row


def test_public_hash_refresh_preserves_latest_operational_archive(tmp_path):
    import hashlib
    from dataclasses import replace
    from config.settings import Settings
    from production.io import atomic_json
    from production.web_bridge import tree_digest
    from institutions.seoul_south_hotfix import refresh_portable_public_hash
    folder = tmp_path / 'data/github'
    folder.mkdir(parents=True)
    archive = b'latest committed operational archive'
    (folder / 'state.zip').write_bytes(archive)
    state = {'dataset_version': 'same-version', 'archive_sha256': hashlib.sha256(archive).hexdigest(),
             'members': 1216, 'public_tree_sha256': 'old-public-hash'}
    atomic_json(folder / 'state.json', state)
    atomic_json(tmp_path / 'data/production/current.json', {'dataset_version': 'same-version'})
    atomic_json(tmp_path / 'web/public/web_data/institutions.json', [{'latitude': 37.4771593}])
    refresh_portable_public_hash(replace(Settings(), project_root=tmp_path, production_root=tmp_path / 'data/production'))
    updated = read_json(folder / 'state.json')
    assert (folder / 'state.zip').read_bytes() == archive
    assert {k: v for k, v in state.items() if k != 'public_tree_sha256'} == {
        k: v for k, v in updated.items() if k != 'public_tree_sha256'}
    assert updated['public_tree_sha256'] == tree_digest(tmp_path / 'web/public/web_data')
