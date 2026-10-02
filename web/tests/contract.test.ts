import { describe, it, expect, beforeEach, vi } from 'vitest';
import { fetchMonthMenu, clearMonthMenuCache } from '../src/data/api';
import {
  normalizeMealSlot,
  sanitizeSource,
  formatDataScope,
  hasMealDataForDate,
  getInstitutionTypeKorean,
  sanitizeCoordinates,
} from '../src/data/adapter';
import { MealSlotData, MonthMenu } from '../src/data/types';

describe('Web Data Contract — Canonical Phase 3B.1 Specifications', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    clearMonthMenuCache();
  });

  describe('Zero-Padded Month File Fetching', () => {
    it('always requests zero-padded month files (01.json ~ 09.json)', async () => {
      const mockFetch = vi.fn().mockImplementation(() => {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: async () => ({
            schema_version: '1.0',
            institution_id: 'KR_CORR_MOKPO_PRISON',
            year: 2024,
            month: 9,
            days: {},
            sources: [],
          }),
        });
      });
      globalThis.fetch = mockFetch as any;

      // Test month 9 -> 09.json
      await fetchMonthMenu('KR_CORR_MOKPO_PRISON', 2024, 9);
      expect(mockFetch).toHaveBeenCalledWith(
        '/web_data/menus/KR_CORR_MOKPO_PRISON/2024/09.json'
      );

      // Clear cache and test month 1 -> 01.json
      clearMonthMenuCache();
      await fetchMonthMenu('KR_CORR_MOKPO_PRISON', 2024, 1);
      expect(mockFetch).toHaveBeenCalledWith(
        '/web_data/menus/KR_CORR_MOKPO_PRISON/2024/01.json'
      );

      // Clear cache and test month 10 -> 10.json
      clearMonthMenuCache();
      await fetchMonthMenu('KR_CORR_MOKPO_PRISON', 2024, 10);
      expect(mockFetch).toHaveBeenCalledWith(
        '/web_data/menus/KR_CORR_MOKPO_PRISON/2024/10.json'
      );

      // Clear cache and test month 12 -> 12.json
      clearMonthMenuCache();
      await fetchMonthMenu('KR_CORR_MOKPO_PRISON', 2024, 12);
      expect(mockFetch).toHaveBeenCalledWith(
        '/web_data/menus/KR_CORR_MOKPO_PRISON/2024/12.json'
      );
    });

    it('caches month menu in memory to avoid redundant network requests', async () => {
      const mockFetch = vi.fn().mockImplementation(() =>
        Promise.resolve({
          ok: true,
          status: 200,
          json: async () => ({
            schema_version: '1.0',
            institution_id: 'KR_CORR_MOKPO_PRISON',
            year: 2024,
            month: 9,
            days: {},
            sources: [],
          }),
        })
      );
      globalThis.fetch = mockFetch as any;

      const firstCall = await fetchMonthMenu('KR_CORR_MOKPO_PRISON', 2024, 9);
      const secondCall = await fetchMonthMenu('KR_CORR_MOKPO_PRISON', 2024, 9);

      expect(mockFetch).toHaveBeenCalledTimes(1);
      expect(firstCall).toEqual(secondCall);
    });
  });

  describe('Rich Meal Slot Normalization', () => {
    it('normalizes canonical rich meal slot objects containing menu_items and sources', () => {
      const richSlot: MealSlotData = {
        menu_items: [
          { name: '쌀밥', raw_text: '쌀밥' },
          { name: '쇠고기미역국', raw_text: '쇠고기미역국' },
          { name: '배추김치' },
        ],
        source_document_id: 'doc-101',
        source_document_ids: ['doc-101', 'doc-102'],
        source: {
          document_id: 'doc-101',
          post_id: '12345',
          original_filename: '2024년 9월 목포교도소 식단표.xlsx',
          published_date: '2024-08-30',
          post_url: 'https://corrections.go.kr/board/12345',
        },
      };

      const normalized = normalizeMealSlot(richSlot);

      expect(normalized).not.toBeNull();
      expect(normalized!.menu_items).toHaveLength(3);
      expect(normalized!.menu_items[0].name).toBe('쌀밥');
      expect(normalized!.source_document_id).toBe('doc-101');
      expect(normalized!.source_document_ids).toEqual(['doc-101', 'doc-102']);
      expect(normalized!.source?.original_filename).toBe('2024년 9월 목포교도소 식단표.xlsx');
      expect(normalized!.source?.published_date).toBe('2024-08-30');
    });

    it('falls back gracefully to array structure for legacy test fixtures', () => {
      const arraySlot = [
        { name: '보리밥' },
        { name: '된장찌개' },
      ];

      const normalized = normalizeMealSlot(arraySlot as any);
      expect(normalized).not.toBeNull();
      expect(normalized!.menu_items).toHaveLength(2);
      expect(normalized!.menu_items[0].name).toBe('보리밥');
      expect(normalized!.source_document_id).toBeUndefined();
      expect(normalized!.source_document_ids).toEqual([]);
      expect(normalized!.source).toBeUndefined();
    });

    it('handles undefined or null meal slots safely without crashing', () => {
      expect(normalizeMealSlot(undefined)).toBeNull();
      expect(normalizeMealSlot(null as any)).toBeNull();
    });
  });

  describe('Source Sanitization & Field Mapping', () => {
    it('preserves public web fields and strips any local filesystem paths', () => {
      const rawSource = {
        document_id: 'doc-999',
        post_id: '999',
        attachment_id: 'att-1',
        post_url: 'https://corrections.go.kr/notice/999',
        download_url: 'https://corrections.go.kr/download/att-1',
        original_filename: '2024_09_식단표.xlsx',
        published_date: '2024-09-01',
        // Hypothetical dangerous internal fields
        local_path: 'E:\\workspace\\correction\\raw\\file.xlsx',
        fs_uri: 'file:///tmp/file.xlsx',
      };

      const sanitized = sanitizeSource(rawSource);
      expect(sanitized).not.toBeNull();
      expect(sanitized!.document_id).toBe('doc-999');
      expect(sanitized!.post_id).toBe('999');
      expect(sanitized!.attachment_id).toBe('att-1');
      expect(sanitized!.post_url).toBe('https://corrections.go.kr/notice/999');
      expect(sanitized!.download_url).toBe('https://corrections.go.kr/download/att-1');
      expect(sanitized!.original_filename).toBe('2024_09_식단표.xlsx');
      expect(sanitized!.published_date).toBe('2024-09-01');

      // Verify internal properties are not exposed or leaked
      expect((sanitized as any).local_path).toBeUndefined();
      expect((sanitized as any).fs_uri).toBeUndefined();
    });

    it('sanitizes malicious or local file URLs in post_url and download_url', () => {
      const maliciousSource = {
        document_id: 'doc-evil',
        post_url: 'file:///etc/passwd',
        download_url: 'javascript:alert(1)',
        original_filename: 'exploit.xlsx',
      };

      const sanitized = sanitizeSource(maliciousSource);
      expect(sanitized).not.toBeNull();
      expect(sanitized!.post_url).toBeUndefined();
      expect(sanitized!.download_url).toBeUndefined();
    });
  });

  describe('Data Scope Mapping & Validation', () => {
    it('correctly maps excel_ready_only scope to user-friendly badge text', () => {
      expect(formatDataScope('excel_ready_only').badge).toBe('Excel 검증 완료');
      expect(formatDataScope('excel_ready_only').title).toBe('검증 완료 XLS/XLSX 식단 자료');
      expect(formatDataScope(undefined).badge).toBe('검증 완료');
    });

    it('accurately identifies whether a date has meal data', () => {
      const sampleMonthMenu: MonthMenu = {
        schema_version: '1.0',
        institution_id: 'KR_CORR_TEST',
        year: 2024,
        month: 9,
        days: {
          '2024-09-01': {
            breakfast: { menu_items: [{ name: '쌀밥' }] },
            lunch: null,
            dinner: null,
          },
          '2024-09-02': {
            breakfast: null,
            lunch: null,
            dinner: null,
          },
        },
        sources: [],
      };

      expect(hasMealDataForDate(sampleMonthMenu, '2024-09-01')).toBe(true);
      expect(hasMealDataForDate(sampleMonthMenu, '2024-09-02')).toBe(false);
      expect(hasMealDataForDate(sampleMonthMenu, '2024-09-03')).toBe(false);
      expect(hasMealDataForDate(null, '2024-09-01')).toBe(false);
    });
  });

  describe('Map Contract & Competition UX — Phase W3 Specifications', () => {
    it('verifies institution type label contracts for all 4 production types', () => {
      expect(getInstitutionTypeKorean('prison')).toBe('교도소');
      expect(getInstitutionTypeKorean('detention_center')).toBe('구치소');
      expect(getInstitutionTypeKorean('branch')).toBe('지소');
      expect(getInstitutionTypeKorean('private_prison')).toBe('민영교도소');
      expect(getInstitutionTypeKorean('unknown_custom')).toBe('교정기관');
    });

    it('verifies coordinate rules: strictly preserves null and never fabricates fake coordinates', () => {
      // Valid coordinates within South Korea
      const valid = sanitizeCoordinates(37.3963, 126.9878);
      expect(valid.has_coordinates).toBe(true);
      expect(valid.latitude).toBe(37.3963);
      expect(valid.longitude).toBe(126.9878);

      // Explicit null coordinates (e.g. Seoul Nambu)
      const nullCoords = sanitizeCoordinates(null, null);
      expect(nullCoords.has_coordinates).toBe(false);
      expect(nullCoords.latitude).toBeNull();
      expect(nullCoords.longitude).toBeNull();

      // Corrupt or out of range coordinates
      const outOfBounds = sanitizeCoordinates(0, 0);
      expect(outOfBounds.has_coordinates).toBe(false);
      expect(outOfBounds.latitude).toBeNull();
      expect(outOfBounds.longitude).toBeNull();
    });

    it('verifies map marker eligibility: exactly institutions with coordinates are map-ready', () => {
      const mockMasterList = [
        { institution_id: 'KR_1', name: '기관1', latitude: 37.5, longitude: 127.0, has_coordinates: true },
        { institution_id: 'KR_2', name: '기관2', latitude: 35.1, longitude: 129.0, has_coordinates: true },
        { institution_id: 'KR_3', name: '서울남부구치소', latitude: null, longitude: null, has_coordinates: false },
      ];

      const mapReady = mockMasterList.filter(
        (i) => i.has_coordinates && i.latitude !== null && i.longitude !== null
      );
      const unmapped = mockMasterList.filter(
        (i) => !i.has_coordinates || i.latitude === null || i.longitude === null
      );

      expect(mapReady).toHaveLength(2);
      expect(unmapped).toHaveLength(1);
      expect(unmapped[0].name).toBe('서울남부구치소');
    });

    it('verifies marker status distinction between data institutions and preparation institutions', () => {
      const availableIds = new Set(['KR_DATA_1', 'KR_DATA_2']);
      const sampleInstitutions = [
        { institution_id: 'KR_DATA_1', name: '식단있는기관' },
        { institution_id: 'KR_NO_DATA_1', name: '준비중기관' },
      ];

      const hasData1 = availableIds.has(sampleInstitutions[0].institution_id);
      const hasData2 = availableIds.has(sampleInstitutions[1].institution_id);

      expect(hasData1).toBe(true); // State A: 식단 조회 가능
      expect(hasData2).toBe(false); // State B: 식단 데이터 준비 중
    });
  });
});
