import { describe, it, expect } from 'vitest';
import {
  normalizeManifest,
  normalizeInstitutions,
  normalizeMonthMenu,
  sanitizeCoordinates,
  sanitizeUrl,
  getInstitutionTypeKorean,
  getAvailableYears,
  getAvailableMonths,
  hasMealDataForDate,
} from '../src/data/adapter';

describe('Data Adapter - sanitizeCoordinates', () => {
  it('strictly validates coordinates and returns null for invalid values', () => {
    // Missing / null
    expect(sanitizeCoordinates(null, null)).toEqual({
      latitude: null,
      longitude: null,
      has_coordinates: false,
    });
    expect(sanitizeCoordinates(undefined, undefined)).toEqual({
      latitude: null,
      longitude: null,
      has_coordinates: false,
    });

    // NaN
    expect(sanitizeCoordinates(NaN, 127.0)).toEqual({
      latitude: null,
      longitude: null,
      has_coordinates: false,
    });

    // Out of South Korea bounds
    expect(sanitizeCoordinates(10.0, 10.0)).toEqual({
      latitude: null,
      longitude: null,
      has_coordinates: false,
    });

    // Valid South Korea coordinates
    expect(sanitizeCoordinates(37.5665, 126.978)).toEqual({
      latitude: 37.5665,
      longitude: 126.978,
      has_coordinates: true,
    });
  });
});

describe('Data Adapter - sanitizeUrl', () => {
  it('blocks local file paths and only allows http/https URLs', () => {
    expect(sanitizeUrl('C:\\data\\raw\\menu.xlsx')).toBeUndefined();
    expect(sanitizeUrl('/data/raw/menu.pdf')).toBeUndefined();
    expect(sanitizeUrl('file:///tmp/secret.xlsx')).toBeUndefined();
    expect(sanitizeUrl('https://www.corrections.go.kr/notice/123')).toBe(
      'https://www.corrections.go.kr/notice/123'
    );
    expect(sanitizeUrl('http://www.corrections.go.kr/notice/123')).toBe(
      'http://www.corrections.go.kr/notice/123'
    );
  });
});

describe('Data Adapter - getInstitutionTypeKorean', () => {
  it('correctly maps institution type to friendly Korean', () => {
    expect(getInstitutionTypeKorean('detention_center')).toBe('구치소');
    expect(getInstitutionTypeKorean('prison')).toBe('교도소');
    expect(getInstitutionTypeKorean('branch')).toBe('지소');
    expect(getInstitutionTypeKorean('branch_prison')).toBe('지소');
    expect(getInstitutionTypeKorean('private_prison')).toBe('민영교도소');
    expect(getInstitutionTypeKorean('juvenile_reformatory')).toBe('소년원');
    expect(getInstitutionTypeKorean('vocational_training_prison')).toBe('직업훈련교도소');
    expect(getInstitutionTypeKorean('unknown')).toBe('교정기관');
  });
});

describe('Data Adapter - normalizeManifest', () => {
  it('normalizes manifest and preserves stats without fabricating fake numbers', () => {
    const raw = {
      schema_version: '1.0',
      dataset_version: 'v1.0.0',
      stats: {
        total_institutions: 55,
        collected_institutions: 3,
        structured_documents: 19,
      },
      institutions: [
        {
          institution_id: 'KR_CORR_MOKPO_PRISON',
          available_years: {
            '2026': [9, 10],
            '2025': [1, 2, 3],
          },
        },
      ],
    };

    const manifest = normalizeManifest(raw);
    expect(manifest.schema_version).toBe('1.0');
    expect(manifest.stats?.total_institutions).toBe(55);
    expect(manifest.stats?.collected_institutions).toBe(3);
    expect(manifest.institutions).toHaveLength(1);
    expect(manifest.institutions[0].available_years['2026']).toEqual([9, 10]);

    // Test helper functions
    const years = getAvailableYears(manifest, 'KR_CORR_MOKPO_PRISON');
    expect(years).toEqual([2026, 2025]);

    const months = getAvailableMonths(manifest, 'KR_CORR_MOKPO_PRISON', 2026);
    expect(months).toEqual([9, 10]);
  });

  it('handles manifest with missing stats gracefully without crashing', () => {
    const raw = {
      schema_version: '1.0',
      institutions: [],
    };
    const manifest = normalizeManifest(raw);
    expect(manifest.stats).toBeUndefined();
    expect(manifest.institutions).toEqual([]);
  });
});

describe('Data Adapter - normalizeInstitutions', () => {
  it('normalizes institution records and handles missing coordinates without crashing', () => {
    const rawList = [
      {
        institution_id: 'KR_CORR_SEOUL_DETENTION',
        canonical_name: '서울구치소',
        institution_type: 'detention_center',
        address: '경기도 의왕시',
        latitude: null,
        longitude: null,
      },
      {
        institution_id: 'KR_CORR_MOKPO_PRISON',
        name: '목포교도소',
        type: 'prison',
        address: '전라남도 목포시',
        latitude: 34.8028,
        longitude: 126.3986,
      },
    ];

    const normalized = normalizeInstitutions(rawList);
    expect(normalized).toHaveLength(2);

    expect(normalized[0].name).toBe('서울구치소');
    expect(normalized[0].type_korean).toBe('구치소');
    expect(normalized[0].has_coordinates).toBe(false);
    expect(normalized[0].latitude).toBeNull();
    expect(normalized[0].longitude).toBeNull();

    expect(normalized[1].name).toBe('목포교도소');
    expect(normalized[1].type_korean).toBe('교도소');
    expect(normalized[1].has_coordinates).toBe(true);
    expect(normalized[1].latitude).toBe(34.8028);
    expect(normalized[1].longitude).toBe(126.3986);
  });
});

describe('Data Adapter - normalizeMonthMenu', () => {
  it('normalizes day menus and filters out local paths from sources', () => {
    const raw = {
      schema_version: '1.0',
      institution_id: 'KR_CORR_MOKPO_PRISON',
      year: 2026,
      month: 9,
      days: {
        '2026-09-01': {
          breakfast: [{ name: '쌀밥' }, { name: '된장국' }],
          lunch: [{ name: '비빔밥' }],
          dinner: [],
        },
      },
      sources: [
        {
          source_id: 'post-1',
          title: 'C:\\data\\raw\\2026-09-menu.xlsx', // Path should be sanitized to filename or clean title
          url: 'https://corrections.go.kr/post/1',
        },
        {
          source_id: 'post-2',
          title: '식단표 원본',
          url: 'C:\\Users\\admin\\secret.xlsx', // Unsafe url should be filtered
        },
      ],
    };

    const menu = normalizeMonthMenu(raw, 'KR_CORR_MOKPO_PRISON', 2026, 9);
    expect(menu.days['2026-09-01'].breakfast?.menu_items).toHaveLength(2);
    expect(menu.days['2026-09-01'].lunch?.menu_items).toHaveLength(1);
    expect(menu.days['2026-09-01'].dinner).toBeNull();

    // Source verification
    expect(menu.sources[0].title).toBe('2026-09-menu.xlsx');
    expect(menu.sources[0].url).toBe('https://corrections.go.kr/post/1');
    expect(menu.sources[1].url).toBeUndefined(); // Local path stripped!

    // Helper verification
    expect(hasMealDataForDate(menu, '2026-09-01')).toBe(true);
    expect(hasMealDataForDate(menu, '2026-09-02')).toBe(false);
  });

  it('normalizes Phase 3B.1 rich meal slot format with sources', () => {
    const raw = {
      schema_version: '1.0',
      institution_id: 'KR_CORR_MOKPO_PRISON',
      year: 2024,
      month: 9,
      days: {
        '2024-09-01': {
          breakfast: {
            menu_items: [{ name: '소고기미역국', raw_text: '소고기미역국' }],
            source_document_id: '74840-76967',
            source_document_ids: ['74840-76967'],
            source: {
              document_id: '74840-76967',
              post_id: '74840',
              attachment_id: '76967',
              post_url: 'https://www.corrections.go.kr/policyOpen/corrections/74840/artclView.do',
              download_url: 'https://www.corrections.go.kr/policyOpen/corrections/76967/download.do',
              original_filename: '2024년_9월_수용자_부식물_차림표.xlsx',
              published_date: '2024-09-03',
            },
          },
        },
      },
      sources: [
        {
          document_id: '74840-76967',
          post_id: '74840',
          attachment_id: '76967',
          post_url: 'https://www.corrections.go.kr/policyOpen/corrections/74840/artclView.do',
          download_url: 'https://www.corrections.go.kr/policyOpen/corrections/76967/download.do',
          original_filename: '2024년_9월_수용자_부식물_차림표.xlsx',
          published_date: '2024-09-03',
        },
      ],
    };

    const menu = normalizeMonthMenu(raw, 'KR_CORR_MOKPO_PRISON', 2024, 9);
    expect(menu.days['2024-09-01'].breakfast?.menu_items).toHaveLength(1);
    expect(menu.days['2024-09-01'].breakfast?.menu_items[0].name).toBe('소고기미역국');
    expect(menu.days['2024-09-01'].breakfast?.source_document_id).toBe('74840-76967');
    expect(menu.days['2024-09-01'].breakfast?.source?.original_filename).toBe('2024년_9월_수용자_부식물_차림표.xlsx');
    expect(menu.sources[0].post_url).toBe('https://www.corrections.go.kr/policyOpen/corrections/74840/artclView.do');
    expect(menu.sources[0].download_url).toBe('https://www.corrections.go.kr/policyOpen/corrections/76967/download.do');
  });

  it('handles intermediate sample list format (raw.records)', () => {
    const raw = {
      schema_version: '1.0',
      institution_id: 'KR_CORR_MOKPO_PRISON',
      meal_year: 2026,
      meal_month: 9,
      records: [
        {
          institution_id: 'KR_CORR_MOKPO_PRISON',
          meal_date: '2026-09-05',
          meal_type: 'breakfast',
          menu_items: [{ name: '현미밥' }, { name: '미역국' }],
        },
      ],
    };

    const menu = normalizeMonthMenu(raw, 'KR_CORR_MOKPO_PRISON', 2026, 9);
    expect(menu.days['2026-09-05'].breakfast?.menu_items).toHaveLength(2);
    expect(menu.days['2026-09-05'].breakfast?.menu_items[0].name).toBe('현미밥');
  });
});
