import {
  normalizeInstitutions,
  normalizeManifest,
  normalizeMonthMenu,
} from './adapter';
import { Institution, Manifest, MonthMenu } from './types';

// Base URL for static JSON data
const DATA_BASE_URL = (import.meta.env.VITE_DATA_BASE_URL || `${import.meta.env.BASE_URL}web_data`).replace(/\/+$/, '');

// In-memory cache for lazy-loaded month menu JSON files
const monthMenuCache = new Map<string, MonthMenu>();

export class ApiError extends Error {
  status?: number;
  isNotFound?: boolean;

  constructor(message: string, status?: number, isNotFound?: boolean) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.isNotFound = isNotFound;
  }
}

async function fetchJson<T>(url: string): Promise<T> {
  let response: Response;
  try {
    response = await fetch(url);
  } catch (err: any) {
    throw new ApiError(
      `네트워크 연결 상태를 확인해주세요 (${err?.message || 'Network error'})`,
      0,
      false
    );
  }

  if (response.status === 404) {
    throw new ApiError('요청하신 데이터를 찾을 수 없습니다 (404 Not Found)', 404, true);
  }

  if (!response.ok) {
    throw new ApiError(`데이터를 불러오지 못했습니다 (HTTP ${response.status})`, response.status, false);
  }

  try {
    return await response.json();
  } catch (err: any) {
    throw new ApiError('JSON 데이터 파싱에 실패했습니다.', response.status, false);
  }
}

/**
 * Fetches and normalizes dataset manifest
 */
export async function fetchManifest(): Promise<Manifest> {
  const url = `${DATA_BASE_URL}/manifest.json`;
  const raw = await fetchJson<any>(url);
  return normalizeManifest(raw);
}

/**
 * Fetches and normalizes all institutions master list (all 55 institutions)
 */
export async function fetchInstitutions(): Promise<Institution[]> {
  const url = `${DATA_BASE_URL}/institutions.json`;
  const raw = await fetchJson<any[]>(url);
  return normalizeInstitutions(raw);
}

/**
 * Fetches and normalizes a specific month menu for an institution.
 * Uses zero-padded 2-digit month filename (MM.json) per Phase 3B.1 contract.
 * Caches in memory to prevent duplicate network requests.
 */
export async function fetchMonthMenu(
  institutionId: string,
  year: number,
  month: number
): Promise<MonthMenu> {
  const paddedMonth = String(month).padStart(2, '0');
  const cacheKey = `${institutionId}/${year}/${paddedMonth}`;

  if (monthMenuCache.has(cacheKey)) {
    return monthMenuCache.get(cacheKey)!;
  }

  const url = `${DATA_BASE_URL}/menus/${encodeURIComponent(institutionId)}/${year}/${paddedMonth}.json`;
  const raw = await fetchJson<any>(url);
  const normalized = normalizeMonthMenu(raw, institutionId, year, month);

  monthMenuCache.set(cacheKey, normalized);
  return normalized;
}

/**
 * Clears in-memory month menu cache (used in tests or dataset reload)
 */
export function clearMonthMenuCache(): void {
  monthMenuCache.clear();
}
