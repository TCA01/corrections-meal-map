/**
 * Core domain types for Corrections Meal Data Map
 * (교정 식단 데이터맵) — Phase 3B.1 Web Contract
 */

export interface DatasetStats {
  total_institutions?: number;
  collected_institutions?: number;
  structured_documents?: number;
  total_meal_records?: number;
  institution_month_files?: number;
  last_updated?: string;
  data_scope?: string; // e.g. "excel_ready_only"
}

export interface ManifestInstitution {
  institution_id: string;
  available_years: Record<string, number[]>; // e.g. { "2024": [1, 2, 3] }
}

export interface Manifest {
  schema_version: string;
  web_contract_version?: string; // e.g. "3B.1"
  dataset_version?: string;
  generated_at?: string;
  is_mock_fixture?: boolean;
  fixture_notice?: string;
  stats?: DatasetStats;
  institutions: ManifestInstitution[];
}

export interface RawInstitution {
  institution_id: string;
  name?: string;
  canonical_name?: string;
  short_name?: string;
  type?: string;
  institution_type?: string;
  address?: string;
  latitude?: number | null;
  longitude?: number | null;
  postal_code?: string;
  phone?: string;
  source_url?: string;
  aliases?: string[];
  active?: boolean;
}

export interface Institution {
  institution_id: string;
  name: string;
  short_name: string;
  type: string;
  type_korean: string;
  address: string;
  latitude: number | null;
  longitude: number | null;
  has_coordinates: boolean;
  postal_code?: string;
  phone?: string;
  source_url?: string;
}

export interface MenuItem {
  name: string;
  raw_text?: string;
}

/**
 * Canonical public source object per docs/web_data_contract.md
 */
export interface MenuSource {
  document_id?: string;
  post_id?: string;
  attachment_id?: string;
  post_url?: string;
  download_url?: string;
  original_filename?: string;
  published_date?: string;

  // Compatibility aliases for legacy/W1 test fixtures
  title?: string;
  url?: string;
  published_at?: string;
  source_id?: string;
}

/**
 * Rich meal slot object per Phase 3B.1 contract
 */
export interface MealSlotData {
  menu_items: MenuItem[];
  source_document_id?: string;
  source_document_ids?: string[];
  source?: MenuSource;
}

export interface DayMenu {
  breakfast?: MealSlotData | null;
  lunch?: MealSlotData | null;
  dinner?: MealSlotData | null;
}

export interface MonthMenu {
  schema_version: string;
  institution_id: string;
  year: number;
  month: number;
  days: Record<string, DayMenu>; // key format: YYYY-MM-DD
  sources: MenuSource[];
  is_mock_fixture?: boolean;
  fixture_notice?: string;
}

export interface MealSlotInfo {
  mealType: 'breakfast' | 'lunch' | 'dinner';
  title: string;
  items: MenuItem[];
  source?: MenuSource;
  sourceDocumentIds?: string[];
  isEmpty: boolean;
}
