import React, { useEffect, useRef, useState, useMemo } from 'react';
import L from 'leaflet';
import { Institution } from '../data/types';
import { MapPin, MapPinOff, Layers, RefreshCw, AlertTriangle } from 'lucide-react';

interface KoreaMapProps {
  institutions: Institution[];
  selectedInstitutionId: string | null;
  onSelectInstitution: (institutionId: string) => void;
  availableInstitutionIds?: Set<string>;
}

// Center of South Korea (Daejeon overview)
const DEFAULT_CENTER: [number, number] = [36.2, 127.8];
const DEFAULT_ZOOM = 7;

function createMarkerIcon(isSelected: boolean, hasMealData: boolean, name: string) {
  const bgClass = isSelected
    ? 'bg-blue-600 ring-4 ring-blue-300 ring-offset-2 z-40 scale-125 shadow-xl'
    : hasMealData
    ? 'bg-blue-600 hover:bg-blue-700 shadow-md z-20 hover:scale-110'
    : 'bg-slate-500 hover:bg-slate-600 shadow-sm z-10 hover:scale-105 opacity-90';

  const statusDot = hasMealData
    ? '<span class="absolute -top-1 -right-1 w-2.5 h-2.5 bg-emerald-400 border-2 border-white rounded-full"></span>'
    : '<span class="absolute -top-1 -right-1 w-2.5 h-2.5 bg-slate-300 border-2 border-white rounded-full"></span>';

  return L.divIcon({
    className: 'custom-map-marker',
    html: `
      <div class="relative flex items-center justify-center transition-transform" title="${name} (${hasMealData ? '식단 조회 가능' : '식단 준비 중'})">
        <div class="w-7 h-7 rounded-full ${bgClass} text-white flex items-center justify-center cursor-pointer transition">
          <svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
            <path d="M20 10c0 6-8 12-8 12s-8-6-8-12a8 8 0 0 1 16 0Z"></path>
            <circle cx="12" cy="10" r="3"></circle>
          </svg>
          ${statusDot}
        </div>
      </div>
    `,
    iconSize: [28, 28],
    iconAnchor: [14, 28],
    popupAnchor: [0, -28],
  });
}

export const KoreaMap: React.FC<KoreaMapProps> = ({
  institutions,
  selectedInstitutionId,
  onSelectInstitution,
  availableInstitutionIds,
}) => {
  const mapContainerRef = useRef<HTMLDivElement>(null);
  const mapInstanceRef = useRef<L.Map | null>(null);
  const markersRef = useRef<Map<string, L.Marker>>(new Map());
  const [tileError, setTileError] = useState(false);

  // Filter institutions that have valid non-null coordinates (strictly 53 institutions)
  const validInstitutions = useMemo(() => {
    return institutions.filter(
      (inst) => inst.has_coordinates && inst.latitude !== null && inst.longitude !== null
    );
  }, [institutions]);

  // Statistics for map legend
  const stats = useMemo(() => {
    let dataWithCoords = 0;
    let noDataWithCoords = 0;
    validInstitutions.forEach((inst) => {
      if (availableInstitutionIds?.has(inst.institution_id)) {
        dataWithCoords++;
      } else {
        noDataWithCoords++;
      }
    });
    const nullCoords = institutions.length - validInstitutions.length;
    return {
      dataWithCoords,
      noDataWithCoords,
      nullCoords,
      total: institutions.length,
      rendered: validInstitutions.length,
    };
  }, [validInstitutions, institutions, availableInstitutionIds]);

  const selectedInst = institutions.find((i) => i.institution_id === selectedInstitutionId);
  const selectedHasNoCoords = selectedInst && !selectedInst.has_coordinates;

  // Initialize Leaflet Map
  useEffect(() => {
    if (!mapContainerRef.current) return;
    if (mapInstanceRef.current) return;

    try {
      const map = L.map(mapContainerRef.current, {
        center: DEFAULT_CENTER,
        zoom: DEFAULT_ZOOM,
        minZoom: 6,
        maxZoom: 17,
        zoomControl: true,
      });

      // CartoDB Positron tiles: clean, accessible, and fast
      const tileLayer = L.tileLayer(
        'https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png',
        {
          attribution:
            '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>',
          subdomains: 'abcd',
          maxZoom: 19,
        }
      );

      if (typeof (tileLayer as any).on === 'function') {
        (tileLayer as any).on('tileerror', () => {
          setTileError(true);
        });
      }

      tileLayer.addTo(map);
      mapInstanceRef.current = map;
    } catch (err) {
      console.warn('Map initialization skipped (e.g. test environment):', err);
    }

    return () => {
      if (mapInstanceRef.current) {
        mapInstanceRef.current.remove();
        mapInstanceRef.current = null;
      }
    };
  }, []);

  // Update Markers when validInstitutions, selectedInstitutionId, or available IDs change
  useEffect(() => {
    const map = mapInstanceRef.current;
    if (!map) return;

    // Clear previous markers
    markersRef.current.forEach((marker) => marker.remove());
    markersRef.current.clear();

    validInstitutions.forEach((inst) => {
      if (inst.latitude === null || inst.longitude === null) return;

      const isSelected = inst.institution_id === selectedInstitutionId;
      const hasMealData = Boolean(availableInstitutionIds?.has(inst.institution_id));
      const icon = createMarkerIcon(isSelected, hasMealData, inst.name);

      const marker = L.marker([inst.latitude, inst.longitude], { icon }).addTo(map);

      // Bind accessible popup
      const popupHtml = `
        <div style="font-family: inherit; font-size: 13px; line-height: 1.4; padding: 2px;">
          <div style="display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 4px;">
            <span style="font-weight: 700; color: #0f172a; font-size: 14px;">${inst.name}</span>
            <span style="font-size: 10px; padding: 2px 6px; border-radius: 9999px; font-weight: 700; ${
              hasMealData
                ? 'background-color: #ecfdf5; color: #047857; border: 1px solid #a7f3d0;'
                : 'background-color: #f1f5f9; color: #64748b; border: 1px solid #e2e8f0;'
            }">
              ${hasMealData ? '식단 있음' : '준비 중'}
            </span>
          </div>
          <div style="color: #64748b; font-size: 11px; margin-bottom: 8px;">
            <span style="font-weight: 600; color: #334155;">${inst.type_korean}</span> · ${inst.address}
          </div>
          <button
            id="map-popup-btn-${inst.institution_id}"
            style="display: block; width: 100%; text-align: center; padding: 6px 10px; font-size: 11px; font-weight: 600; color: #ffffff; background-color: ${
              hasMealData ? '#2563eb' : '#475569'
            }; border: none; border-radius: 6px; cursor: pointer; transition: background 0.2s;"
          >
            ${hasMealData ? '식단 조회하기' : '기관 상세 정보'}
          </button>
        </div>
      `;

      marker.bindPopup(popupHtml);

      // Handle popup button click
      marker.on('popupopen', () => {
        const btn = document.getElementById(`map-popup-btn-${inst.institution_id}`);
        if (btn) {
          btn.onclick = () => {
            onSelectInstitution(inst.institution_id);
          };
        }
      });

      marker.on('click', () => {
        onSelectInstitution(inst.institution_id);
      });

      markersRef.current.set(inst.institution_id, marker);
    });
  }, [validInstitutions, selectedInstitutionId, onSelectInstitution, availableInstitutionIds]);

  // Center map on selected institution smoothly
  useEffect(() => {
    const map = mapInstanceRef.current;
    if (!map || !selectedInstitutionId) return;

    const inst = validInstitutions.find((i) => i.institution_id === selectedInstitutionId);
    if (inst && inst.latitude !== null && inst.longitude !== null) {
      const currentZoom = typeof map.getZoom === 'function' ? map.getZoom() : DEFAULT_ZOOM;
      const targetZoom = Math.max(currentZoom, 10);
      map.setView([inst.latitude, inst.longitude], targetZoom, { animate: true });
      const marker = markersRef.current.get(inst.institution_id);
      if (marker) {
        marker.openPopup();
      }
    }
  }, [selectedInstitutionId, validInstitutions]);

  // Reset to default viewport
  const handleResetViewport = () => {
    const map = mapInstanceRef.current;
    if (map) {
      map.setView(DEFAULT_CENTER, DEFAULT_ZOOM, { animate: true });
    }
  };

  return (
    <div className="relative w-full h-[360px] sm:h-[460px] lg:h-[600px] bg-slate-100 rounded-2xl overflow-hidden border border-slate-200 shadow-sm flex flex-col">
      {/* Top Map Header & Viewport Controls */}
      <div className="absolute top-3 left-3 right-3 z-[1000] flex flex-wrap items-center justify-between gap-2 pointer-events-none">
        <div className="bg-white/95 backdrop-blur-sm border border-slate-200/90 rounded-xl px-3 py-1.5 shadow-sm text-xs pointer-events-auto flex items-center gap-2 text-slate-700">
          <Layers className="w-3.5 h-3.5 text-blue-600" />
          <span>
            지도 위치: <strong className="text-slate-900">{stats.rendered}</strong>개소 / 전체{' '}
            {stats.total}개소
          </span>
        </div>

        <button
          type="button"
          onClick={handleResetViewport}
          className="bg-white/95 backdrop-blur-sm border border-slate-200/90 rounded-xl px-2.5 py-1.5 shadow-sm text-xs text-slate-700 hover:text-blue-600 hover:bg-slate-50 transition pointer-events-auto flex items-center gap-1.5"
          title="전국 지도 전체 보기"
        >
          <RefreshCw className="w-3 h-3 text-slate-500" />
          <span className="hidden sm:inline">전국 전체 보기</span>
        </button>
      </div>

      {/* Tile Failure Fallback Notice */}
      {tileError && (
        <div className="absolute top-12 left-3 right-3 z-[1000] pointer-events-auto">
          <div className="bg-amber-50 border border-amber-200 rounded-xl p-2.5 text-xs text-amber-800 flex items-center gap-2 shadow-sm">
            <AlertTriangle className="w-4 h-4 text-amber-600 shrink-0" />
            <span>지도를 불러오지 못했습니다. 상단 기관 검색을 이용해 주세요.</span>
          </div>
        </div>
      )}

      {/* Selected Institution without Coordinates Notice Overlay */}
      {selectedHasNoCoords && (
        <div className="absolute bottom-16 left-3 right-3 sm:left-4 sm:right-4 z-[1000] pointer-events-auto">
          <div className="bg-white/95 backdrop-blur-sm border-2 border-amber-300 rounded-xl p-3 shadow-lg flex items-start gap-2.5 text-amber-950 text-xs">
            <MapPinOff className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" />
            <div className="space-y-0.5">
              <p className="font-bold text-amber-900">
                위치 좌표 확인 중 (지도 미표시) — [{selectedInst?.name}]
              </p>
              <p className="text-slate-700 leading-relaxed">
                해당 기관은 공식 좌표 확인 중으로 지도에 임의 마커를 생성하지 않았습니다.
                우측 상세 패널에서 식단 데이터 조회는 정상 이용하실 수 있습니다.
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Leaflet Map DOM Target */}
      <div ref={mapContainerRef} className="w-full flex-1" style={{ minHeight: '280px' }} />

      {/* Bottom Accessible Status & Legend */}
      <div className="bg-white/95 backdrop-blur-sm border-t border-slate-200 px-3 py-2 text-xs text-slate-600 flex flex-wrap items-center justify-between gap-y-1.5 gap-x-3 z-[1000]">
        <div className="flex flex-wrap items-center gap-3">
          <span className="font-semibold text-slate-700 flex items-center gap-1">
            <MapPin className="w-3.5 h-3.5 text-blue-600" /> 범례:
          </span>
          <span className="inline-flex items-center gap-1 text-[11px] text-slate-700">
            <span className="w-2.5 h-2.5 rounded-full bg-blue-600 inline-block"></span>
            <span>식단 조회 가능 ({stats.dataWithCoords}개소)</span>
          </span>
          <span className="inline-flex items-center gap-1 text-[11px] text-slate-500">
            <span className="w-2.5 h-2.5 rounded-full bg-slate-400 inline-block"></span>
            <span>데이터 준비 중 ({stats.noDataWithCoords}개소)</span>
          </span>
          <span className="inline-flex items-center gap-1 text-[11px] text-amber-700">
            <MapPinOff className="w-3 h-3 text-amber-600 inline-block" />
            <span>위치 확인 중 ({stats.nullCoords}개소: 서울남부)</span>
          </span>
        </div>

        <div className="text-[11px] text-slate-400 hidden md:block">
          마커 클릭 시 식단 조회 화면으로 바로 이동합니다
        </div>
      </div>
    </div>
  );
};
