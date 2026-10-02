import {
  DatasetStats,
  DayMenu,
  Institution,
  Manifest,
  ManifestInstitution,
  MenuItem,
  MenuSource,
  MealSlotData,
  MonthMenu,
  RawInstitution,
} from './types';

/**
 * Maps raw backend/pipeline institution types to friendly Korean labels
 */
export function getInstitutionTypeKorean(type?: string): string {
  switch (type?.toLowerCase()) {
    case 'detention_center':
      return '구치소';
    case 'prison':
      return '교도소';
    case 'branch':
    case 'branch_prison':
      return '지소';
    case 'private_prison':
      return '민영교도소';
    case 'juvenile_reformatory':
      return '소년원';
    case 'vocational_training_prison':
      return '직업훈련교도소';
    default:
      if (type && type.includes('구치소')) return '구치소';
      if (type && type.includes('교도소')) return '교도소';
      if (type && type.includes('지소')) return '지소';
      return '교정기관';
  }
}

/**
 * Validates and normalizes geographical coordinates.
 * Strictly returns null for invalid, out-of-range, or missing coordinates.
 * NEVER fabricates or guesses random coordinates.
 */
export function sanitizeCoordinates(
  lat: unknown,
  lng: unknown
): { latitude: number | null; longitude: number | null; has_coordinates: boolean } {
  if (typeof lat !== 'number' || typeof lng !== 'number') {
    return { latitude: null, longitude: null, has_coordinates: false };
  }
  if (isNaN(lat) || isNaN(lng)) {
    return { latitude: null, longitude: null, has_coordinates: false };
  }

  // South Korea bounding box sanity check (~lat 33.0 to 39.5, ~lng 124.0 to 132.5)
  if (lat < 33.0 || lat > 39.5 || lng < 124.0 || lng > 132.5) {
    return { latitude: null, longitude: null, has_coordinates: false };
  }

  return {
    latitude: lat,
    longitude: lng,
    has_coordinates: true,
  };
}

/**
 * Strips or filters unsafe URLs or local file paths from display
 */
export function sanitizeUrl(url?: string): string | undefined {
  if (!url) return undefined;
  const trimmed = url.trim();
  // Prevent exposing local filesystem paths or Windows paths
  if (
    trimmed.startsWith('file://') ||
    trimmed.startsWith('C:\\') ||
    trimmed.startsWith('/data/') ||
    trimmed.includes('\\data\\') ||
    trimmed.includes('data/raw') ||
    trimmed.includes('data/production')
  ) {
    return undefined;
  }
  if (trimmed.startsWith('http://') || trimmed.startsWith('https://')) {
    return trimmed;
  }
  return undefined;
}

/**
 * Normalizes a source object according to docs/web_data_contract.md
 */
export function sanitizeSource(src: any): MenuSource | null {
  if (!src || typeof src !== 'object') return null;

  let filename = src.original_filename || src.title || '수용자 식단표 원본';
  // Strip out any accidental directory separators from filename
  if (filename.includes('/') || filename.includes('\\')) {
    const parts = filename.split(/[/\\]/);
    filename = parts[parts.length - 1];
  }

  const postUrl = sanitizeUrl(src.post_url || src.url);
  const downloadUrl = sanitizeUrl(src.download_url);
  const publishedDate = src.published_date || src.published_at || undefined;
  const docId = src.document_id || src.source_id || undefined;

  return {
    document_id: docId ? String(docId) : undefined,
    post_id: src.post_id ? String(src.post_id) : undefined,
    attachment_id: src.attachment_id ? String(src.attachment_id) : undefined,
    post_url: postUrl,
    download_url: downloadUrl,
    original_filename: filename,
    published_date: publishedDate ? String(publishedDate) : undefined,

    // Backward compatibility aliases
    title: filename,
    url: postUrl || downloadUrl,
    published_at: publishedDate ? String(publishedDate) : undefined,
    source_id: docId ? String(docId) : undefined,
  };
}

/**
 * Sanitizes menu item list
 */
export function sanitizeMenuItems(items: any): MenuItem[] {
  if (!Array.isArray(items)) return [];
  const results: MenuItem[] = [];
  for (const it of items) {
    if (typeof it === 'string' && it.trim()) {
      results.push({ name: it.trim() });
    } else if (it && typeof it.name === 'string' && it.name.trim()) {
      results.push({
        name: it.name.trim(),
        raw_text: typeof it.raw_text === 'string' ? it.raw_text.trim() : undefined,
      });
    }
  }
  return results;
}

/**
 * Normalizes a meal slot (handles Phase 3B.1 Rich Object and legacy Array)
 */
export function normalizeMealSlot(rawSlot: any): MealSlotData | null {
  if (!rawSlot) return null;

  // Case 1: Phase 3B.1 Rich Meal Slot { menu_items, source_document_id, ... }
  if (rawSlot && typeof rawSlot === 'object' && !Array.isArray(rawSlot)) {
    const items = sanitizeMenuItems(rawSlot.menu_items);
    if (items.length === 0) return null;

    let sourceObj: MenuSource | undefined = undefined;
    if (rawSlot.source && typeof rawSlot.source === 'object') {
      const sanitized = sanitizeSource(rawSlot.source);
      if (sanitized) sourceObj = sanitized;
    }

    const docIds: string[] = [];
    if (Array.isArray(rawSlot.source_document_ids)) {
      docIds.push(...rawSlot.source_document_ids.map(String));
    } else if (rawSlot.source_document_id) {
      docIds.push(String(rawSlot.source_document_id));
    }

    return {
      menu_items: items,
      source_document_id: rawSlot.source_document_id ? String(rawSlot.source_document_id) : undefined,
      source_document_ids: docIds,
      source: sourceObj,
    };
  }

  // Case 2: Legacy Array format [ MenuItem, ... ]
  if (Array.isArray(rawSlot)) {
    const items = sanitizeMenuItems(rawSlot);
    if (items.length === 0) return null;
    return {
      menu_items: items,
      source_document_ids: [],
    };
  }

  return null;
}

/**
 * Normalizes Manifest data from raw JSON
 */
export function normalizeManifest(raw: any): Manifest {
  if (!raw || typeof raw !== 'object') {
    throw new Error('유효하지 않은 Manifest 데이터입니다.');
  }

  const schema_version = String(raw.schema_version || '1.0');
  const web_contract_version = raw.web_contract_version ? String(raw.web_contract_version) : undefined;
  const dataset_version = raw.dataset_version ? String(raw.dataset_version) : undefined;
  const generated_at = raw.generated_at ? String(raw.generated_at) : undefined;
  const is_mock_fixture = Boolean(raw.is_mock_fixture);
  const fixture_notice = raw.fixture_notice ? String(raw.fixture_notice) : undefined;

  let stats: DatasetStats | undefined = undefined;
  if (raw.stats && typeof raw.stats === 'object') {
    stats = {
      total_institutions: typeof raw.stats.total_institutions === 'number' ? raw.stats.total_institutions : undefined,
      collected_institutions: typeof raw.stats.collected_institutions === 'number' ? raw.stats.collected_institutions : undefined,
      structured_documents: typeof raw.stats.structured_documents === 'number' ? raw.stats.structured_documents : undefined,
      total_meal_records: typeof raw.stats.total_meal_records === 'number' ? raw.stats.total_meal_records : undefined,
      institution_month_files: typeof raw.stats.institution_month_files === 'number' ? raw.stats.institution_month_files : undefined,
      last_updated: raw.stats.last_updated ? String(raw.stats.last_updated) : undefined,
      data_scope: raw.stats.data_scope ? String(raw.stats.data_scope) : undefined,
    };
  }

  const institutions: ManifestInstitution[] = [];
  if (Array.isArray(raw.institutions)) {
    for (const inst of raw.institutions) {
      if (inst && typeof inst.institution_id === 'string') {
        const availableYearsObj: Record<string, number[]> = {};
        if (inst.available_years && typeof inst.available_years === 'object') {
          for (const [y, months] of Object.entries(inst.available_years)) {
            if (Array.isArray(months)) {
              availableYearsObj[y] = months
                .map((m) => Number(m))
                .filter((m) => !isNaN(m) && m >= 1 && m <= 12)
                .sort((a, b) => a - b);
            }
          }
        }
        institutions.push({
          institution_id: inst.institution_id,
          available_years: availableYearsObj,
        });
      }
    }
  }

  return {
    schema_version,
    web_contract_version,
    dataset_version,
    generated_at,
    is_mock_fixture,
    fixture_notice,
    stats,
    institutions,
  };
}

/**
 * Normalizes list of Institutions
 */
export function normalizeInstitutions(rawList: unknown): Institution[] {
  if (!Array.isArray(rawList)) {
    return [];
  }

  return rawList.map((item: RawInstitution): Institution => {
    const rawName = item.canonical_name || item.name || item.short_name || '이름 미상';
    const rawType = item.institution_type || item.type || '';
    const rawAddress = item.address || '주소 정보 없음';
    const coords = sanitizeCoordinates(item.latitude, item.longitude);

    return {
      institution_id: item.institution_id || '',
      name: rawName,
      short_name: item.short_name || rawName,
      type: rawType,
      type_korean: getInstitutionTypeKorean(rawType),
      address: rawAddress,
      latitude: coords.latitude,
      longitude: coords.longitude,
      has_coordinates: coords.has_coordinates,
      postal_code: item.postal_code,
      phone: item.phone,
      source_url: sanitizeUrl(item.source_url),
    };
  });
}

/**
 * Normalizes Month Menu data.
 * Accepts Phase 3B.1 rich slots, W1 contract (raw.days array slots), and flat record structures.
 */
export function normalizeMonthMenu(raw: any, institutionId: string, year: number, month: number): MonthMenu {
  if (!raw || typeof raw !== 'object') {
    throw new Error('식단 데이터 형식 오류');
  }

  const days: Record<string, DayMenu> = {};

  // Case 1: Standard data contract with 'days' object
  if (raw.days && typeof raw.days === 'object') {
    for (const [dateStr, dayData] of Object.entries(raw.days)) {
      if (dayData && typeof dayData === 'object') {
        const d = dayData as any;
        days[dateStr] = {
          breakfast: normalizeMealSlot(d.breakfast),
          lunch: normalizeMealSlot(d.lunch),
          dinner: normalizeMealSlot(d.dinner),
        };
      }
    }
  }
  // Case 2: Intermediate sample list structure (raw.records)
  else if (Array.isArray(raw.records)) {
    for (const rec of raw.records) {
      if (rec && rec.meal_date && rec.meal_type) {
        const dateStr = String(rec.meal_date);
        if (!days[dateStr]) {
          days[dateStr] = { breakfast: null, lunch: null, dinner: null };
        }
        const mType = rec.meal_type as 'breakfast' | 'lunch' | 'dinner';
        if (['breakfast', 'lunch', 'dinner'].includes(mType)) {
          days[dateStr][mType] = {
            menu_items: sanitizeMenuItems(rec.menu_items),
            source_document_ids: [],
          };
        }
      }
    }
  }

  // Sanitize sources - never expose local file paths
  const sources: MenuSource[] = [];
  if (Array.isArray(raw.sources)) {
    for (const src of raw.sources) {
      const sanitized = sanitizeSource(src);
      if (sanitized) {
        sources.push(sanitized);
      }
    }
  }

  return {
    schema_version: String(raw.schema_version || '1.0'),
    institution_id: String(raw.institution_id || institutionId),
    year: Number(raw.year || raw.meal_year || year),
    month: Number(raw.month || raw.meal_month || month),
    days,
    sources,
    is_mock_fixture: Boolean(raw.is_mock_fixture),
    fixture_notice: raw.fixture_notice ? String(raw.fixture_notice) : undefined,
  };
}

/**
 * Returns available years for a given institution from Manifest
 */
export function getAvailableYears(manifest: Manifest | null, institutionId: string): number[] {
  if (!manifest) return [];
  const inst = manifest.institutions.find((i) => i.institution_id === institutionId);
  if (!inst || !inst.available_years) return [];

  return Object.keys(inst.available_years)
    .map(Number)
    .filter((y) => !isNaN(y))
    .sort((a, b) => b - a); // Descending (latest year first)
}

/**
 * Returns available months for a given institution and year from Manifest
 */
export function getAvailableMonths(manifest: Manifest | null, institutionId: string, year: number): number[] {
  if (!manifest) return [];
  const inst = manifest.institutions.find((i) => i.institution_id === institutionId);
  if (!inst || !inst.available_years) return [];

  const months = inst.available_years[String(year)];
  if (!Array.isArray(months)) return [];

  return [...months].sort((a, b) => a - b);
}

/**
 * Checks if a specific date has any meal data recorded
 */
export function hasMealDataForDate(monthMenu: MonthMenu | null, dateStr: string): boolean {
  if (!monthMenu || !monthMenu.days || !monthMenu.days[dateStr]) return false;
  const day = monthMenu.days[dateStr];

  const bCount = day.breakfast?.menu_items?.length ?? (Array.isArray(day.breakfast) ? (day.breakfast as any).length : 0);
  const lCount = day.lunch?.menu_items?.length ?? (Array.isArray(day.lunch) ? (day.lunch as any).length : 0);
  const dCount = day.dinner?.menu_items?.length ?? (Array.isArray(day.dinner) ? (day.dinner as any).length : 0);

  return bCount > 0 || lCount > 0 || dCount > 0;
}

/**
 * Interprets data_scope from manifest for public display
 */
export function formatDataScope(scope?: string): { title: string; badge: string; description: string } {
  switch (scope) {
    case 'excel_ready_only':
      return {
        title: '검증 완료 XLS/XLSX 식단 자료',
        badge: 'Excel 검증 완료',
        description:
          '현재 엄격한 무결성 검증을 통과한 Excel(XLS/XLSX) 기반 수용자 식단표를 우선 제공합니다. 향후 PDF·HWP·HWPX 등 다양한 형식으로 점진 확대될 예정입니다.',
      };
    default:
      return {
        title: '공식 수용자 식단 데이터',
        badge: '검증 완료',
        description: '전국 교정기관이 공식 공개한 수용자 식단표 정규화 데이터입니다.',
      };
  }
}
