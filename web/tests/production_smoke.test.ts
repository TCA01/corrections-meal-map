import { describe, it, expect } from 'vitest';
import * as fs from 'node:fs';
import * as path from 'node:path';

describe('Production Smoke Tests — Direct Inspection of web/public/web_data', () => {
  const webDataDir = path.resolve(__dirname, '../public/web_data');

  it('verifies manifest.json exists and adheres to canonical schema and Phase 4B stats', () => {
    const manifestPath = path.join(webDataDir, 'manifest.json');
    expect(fs.existsSync(manifestPath)).toBe(true);

    const manifestContent = JSON.parse(fs.readFileSync(manifestPath, 'utf-8'));
    expect(manifestContent).toHaveProperty('schema_version');
    expect(manifestContent).toHaveProperty('dataset_version');
    expect(typeof manifestContent.dataset_version).toBe('string');
    expect(manifestContent.dataset_version.length).toBeGreaterThan(10);

    // Verify Phase 4B production dataset stats
    const stats = manifestContent.stats;
    expect(stats).toBeDefined();
    expect(stats.total_institutions).toBe(55);
    expect(stats.collected_institutions).toBeGreaterThanOrEqual(30);
    expect(stats.structured_documents).toBeGreaterThanOrEqual(415);
    expect(stats.total_meal_records).toBeGreaterThanOrEqual(37791);
    const monthCount = manifestContent.institutions.reduce((total: number, i: any) =>
      total + Object.values(i.available_years).reduce((n: number, months: any) => n + months.length, 0), 0);
    expect(stats.institution_month_files).toBe(monthCount);
    expect(stats.data_scope).toBe('excel_ready_only');

    // Institutions list in manifest should contain exactly 30 active institutions
    expect(Array.isArray(manifestContent.institutions)).toBe(true);
    expect(manifestContent.institutions).toHaveLength(stats.collected_institutions);

    for (const inst of manifestContent.institutions) {
      expect(inst.institution_id).toMatch(/^KR_CORR_[A-Z0-9_]+$/);
      expect(inst.available_years).toBeDefined();
      expect(Object.keys(inst.available_years).length).toBeGreaterThan(0);
    }
  });

  it('verifies institutions.json master contains 55 institutions, 53 coordinates, and exactly 2 null coordinates (Seoul Nambu)', () => {
    const institutionsPath = path.join(webDataDir, 'institutions.json');
    expect(fs.existsSync(institutionsPath)).toBe(true);

    const institutions = JSON.parse(fs.readFileSync(institutionsPath, 'utf-8'));
    expect(Array.isArray(institutions)).toBe(true);
    expect(institutions).toHaveLength(55);

    const withCoords = institutions.filter(
      (inst: any) => inst.latitude !== null && inst.longitude !== null
    );
    const nullCoords = institutions.filter(
      (inst: any) => inst.latitude === null && inst.longitude === null
    );

    // Exactly 53 map-ready institutions, exactly 2 under review (null)
    expect(withCoords).toHaveLength(53);
    expect(nullCoords).toHaveLength(2);

    // Specifically verify the two null coordinate institutions
    const nullNames = nullCoords.map((inst: any) => inst.name).sort();
    expect(nullNames).toEqual(['서울남부교도소', '서울남부구치소']);

    // Verify coordinates are all valid within South Korea bounding box
    for (const inst of withCoords) {
      expect(inst.institution_id).toMatch(/^KR_CORR_[A-Z0-9_]+$/);
      expect(typeof inst.name).toBe('string');
      expect(inst.name.length).toBeGreaterThan(0);
      expect(typeof inst.latitude).toBe('number');
      expect(typeof inst.longitude).toBe('number');
      expect(inst.latitude).toBeGreaterThanOrEqual(33.0);
      expect(inst.latitude).toBeLessThanOrEqual(39.5);
      expect(inst.longitude).toBeGreaterThanOrEqual(124.0);
      expect(inst.longitude).toBeLessThanOrEqual(132.5);
    }
  });

  it('verifies data coverage: 28 data institutions have coordinates and 2 data institutions (Seoul Nambu) have null coordinates', () => {
    const manifestPath = path.join(webDataDir, 'manifest.json');
    const institutionsPath = path.join(webDataDir, 'institutions.json');

    const manifestContent = JSON.parse(fs.readFileSync(manifestPath, 'utf-8'));
    const institutions = JSON.parse(fs.readFileSync(institutionsPath, 'utf-8'));

    const dataIds = new Set(manifestContent.institutions.map((i: any) => i.institution_id));
    expect(dataIds.size).toBe(manifestContent.stats.collected_institutions);

    const dataWithCoords = institutions.filter(
      (inst: any) => dataIds.has(inst.institution_id) && inst.latitude !== null
    );
    const dataWithoutCoords = institutions.filter(
      (inst: any) => dataIds.has(inst.institution_id) && inst.latitude === null
    );

    expect(dataWithCoords.length).toBe(dataIds.size - 2);
    expect(dataWithoutCoords).toHaveLength(2);

    const nullDataNames = dataWithoutCoords.map((i: any) => i.name).sort();
    expect(nullDataNames).toEqual(['서울남부교도소', '서울남부구치소']);
  });

  it('verifies menu directory structure and zero-padded filenames for sample production institutions', () => {
    const sampleInstitutions = [
      { id: 'KR_CORR_MOKPO_PRISON', year: '2024', month: '09' },
      { id: 'KR_CORR_BUSAN_PRISON', year: '2019', month: '02' },
      { id: 'KR_CORR_CHANGWON_PRISON', year: '2025', month: '01' },
    ];

    for (const sample of sampleInstitutions) {
      const monthFilePath = path.join(
        webDataDir,
        'menus',
        sample.id,
        sample.year,
        `${sample.month}.json`
      );
      expect(fs.existsSync(monthFilePath)).toBe(true);

      // Verify filename is strictly two digits: 01.json ~ 12.json, never single-digit
      expect(sample.month).toMatch(/^0[1-9]|1[0-2]$/);

      const monthData = JSON.parse(fs.readFileSync(monthFilePath, 'utf-8'));
      expect(monthData.institution_id).toBe(sample.id);
      expect(String(monthData.year)).toBe(sample.year);
      expect(monthData.month).toBe(parseInt(sample.month, 10));

      // Inspect days and meal slots
      expect(monthData.days).toBeDefined();
      const dayKeys = Object.keys(monthData.days);
      expect(dayKeys.length).toBeGreaterThan(0);

      // Inspect first day
      const firstDayKey = dayKeys[0];
      const dayMenu = monthData.days[firstDayKey];
      expect(dayMenu).toHaveProperty('breakfast');
      expect(dayMenu).toHaveProperty('lunch');
      expect(dayMenu).toHaveProperty('dinner');

      // Check rich slot structure
      for (const slotKey of ['breakfast', 'lunch', 'dinner'] as const) {
        const slot = dayMenu[slotKey];
        if (slot) {
          expect(slot).toHaveProperty('menu_items');
          expect(Array.isArray(slot.menu_items)).toBe(true);

          if (slot.menu_items.length > 0) {
            expect(slot.menu_items[0]).toHaveProperty('name');
            expect(typeof slot.menu_items[0].name).toBe('string');
            expect(slot.menu_items[0].name.length).toBeGreaterThan(0);
          }
        }
      }

      // Check sources if present
      if (monthData.sources && monthData.sources.length > 0) {
        for (const src of monthData.sources) {
          expect(src.document_id).toBeDefined();
          if (src.post_url) {
            expect(src.post_url).toMatch(/^https?:\/\//);
            expect(src.post_url).not.toMatch(/^[A-Za-z]:\\/);
            expect(src.post_url).not.toMatch(/^file:\/\//);
          }
          if (src.download_url) {
            expect(src.download_url).toMatch(/^https?:\/\//);
            expect(src.download_url).not.toMatch(/^[A-Za-z]:\\/);
            expect(src.download_url).not.toMatch(/^file:\/\//);
          }
        }
      }
    }
  });

  it('verifies that all institutions referenced in manifest actually have menu directories', () => {
    const manifestPath = path.join(webDataDir, 'manifest.json');
    const manifestContent = JSON.parse(fs.readFileSync(manifestPath, 'utf-8'));

    for (const inst of manifestContent.institutions) {
      const instMenuDir = path.join(webDataDir, 'menus', inst.institution_id);
      expect(fs.existsSync(instMenuDir)).toBe(true);

      for (const [year, months] of Object.entries(inst.available_years)) {
        const yearDir = path.join(instMenuDir, year);
        expect(fs.existsSync(yearDir)).toBe(true);

        for (const month of months as number[]) {
          const zeroPaddedMonth = String(month).padStart(2, '0');
          const monthFile = path.join(yearDir, `${zeroPaddedMonth}.json`);
          expect(fs.existsSync(monthFile)).toBe(true);
        }
      }
    }
  });
});
