import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fetchManifest, fetchInstitutions, fetchMonthMenu, clearMonthMenuCache, ApiError } from '../src/data/api';

describe('Data API Client', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    clearMonthMenuCache();
  });

  it('fetchManifest parses and returns normalized manifest', async () => {
    const mockJson = {
      schema_version: '1.0',
      dataset_version: '2026.09-test',
      institutions: [
        {
          institution_id: 'KR_CORR_MOKPO_PRISON',
          available_years: { '2026': [9, 10] },
        },
      ],
      stats: {
        total_institutions: 55,
      },
    };

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => mockJson,
    } as Response);

    const manifest = await fetchManifest();
    expect(manifest.dataset_version).toBe('2026.09-test');
    expect(manifest.institutions).toHaveLength(1);
    expect(manifest.stats?.total_institutions).toBe(55);
  });

  it('fetchInstitutions parses and returns normalized institutions', async () => {
    const mockList = [
      {
        institution_id: 'KR_CORR_SEOUL_DETENTION',
        name: '서울구치소',
        type: 'detention_center',
        address: '경기도 의왕시',
        latitude: null,
        longitude: null,
      },
    ];

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => mockList,
    } as Response);

    const list = await fetchInstitutions();
    expect(list).toHaveLength(1);
    expect(list[0].name).toBe('서울구치소');
    expect(list[0].type_korean).toBe('구치소');
    expect(list[0].has_coordinates).toBe(false);
  });

  it('fetchMonthMenu parses and returns month menu', async () => {
    const mockMenu = {
      schema_version: '1.0',
      institution_id: 'KR_CORR_MOKPO_PRISON',
      year: 2026,
      month: 9,
      days: {
        '2026-09-01': {
          breakfast: [{ name: '쌀밥' }],
        },
      },
      sources: [],
    };

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => mockMenu,
    } as Response);

    const menu = await fetchMonthMenu('KR_CORR_MOKPO_PRISON', 2026, 9);
    expect(global.fetch).toHaveBeenCalledWith(expect.stringContaining('/menus/KR_CORR_MOKPO_PRISON/2026/09.json'));
    expect(menu.year).toBe(2026);
    expect(menu.month).toBe(9);
    expect(menu.days['2026-09-01'].breakfast?.menu_items[0].name).toBe('쌀밥');
  });

  it('handles 404 Not Found error properly with ApiError', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 404,
    } as Response);

    await expect(fetchMonthMenu('NON_EXISTENT', 2026, 1)).rejects.toThrow(ApiError);
  });

  it('handles network failure properly with ApiError', async () => {
    global.fetch = vi.fn().mockRejectedValue(new Error('Failed to fetch'));

    await expect(fetchManifest()).rejects.toThrow(ApiError);
  });
});
