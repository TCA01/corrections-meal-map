import { describe, it, expect, vi, afterEach } from 'vitest';

afterEach(() => { vi.unstubAllEnvs(); vi.unstubAllGlobals(); vi.resetModules(); });
describe('Static data base paths', () => {
  it.each(['/', '/corrections-meal-map/'])('follows Vite BASE_URL %s', async (base) => {
    vi.stubEnv('BASE_URL', base);
    vi.stubEnv('VITE_DATA_BASE_URL', '');
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => ({ dataset_version: 'fixture', institutions: [] }) }));
    vi.resetModules();
    const api = await import('../src/data/api');
    await api.fetchManifest();
    expect(fetch).toHaveBeenCalledWith(`${base}web_data/manifest.json`);
  });
  it('preserves an explicit data URL override', async () => {
    vi.stubEnv('VITE_DATA_BASE_URL', '/custom-data/');
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => [] }));
    vi.resetModules();
    const api = await import('../src/data/api');
    await api.fetchInstitutions();
    expect(fetch).toHaveBeenCalledWith('/custom-data/institutions.json');
  });
});
