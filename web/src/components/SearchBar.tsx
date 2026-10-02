import React, { useState, useRef, useEffect, useMemo } from 'react';
import { Search, X, MapPin, MapPinOff } from 'lucide-react';
import { Institution } from '../data/types';

interface SearchBarProps {
  institutions: Institution[];
  selectedInstitutionId: string | null;
  onSelectInstitution: (institutionId: string) => void;
  availableInstitutionIds?: Set<string>;
  onlyWithMeals?: boolean;
}

function extractRegion(address?: string): string {
  if (!address) return '';
  const parts = address.trim().split(/\s+/);
  if (parts.length > 0) {
    const first = parts[0];
    // Shorten full province/city names if appropriate for compact badges
    if (first === '서울특별시') return '서울';
    if (first === '부산광역시') return '부산';
    if (first === '대구광역시') return '대구';
    if (first === '인천광역시') return '인천';
    if (first === '광주광역시') return '광주';
    if (first === '대전광역시') return '대전';
    if (first === '울산광역시') return '울산';
    if (first === '세종특별자치시') return '세종';
    if (first === '경기도') return '경기';
    if (first === '강원특별자치도' || first === '강원도') return '강원';
    if (first === '충청북도') return '충북';
    if (first === '충청남도') return '충남';
    if (first === '전라북도' || first === '전북특별자치도') return '전북';
    if (first === '전라남도') return '전남';
    if (first === '경상북도') return '경북';
    if (first === '경상남도') return '경남';
    if (first === '제주특별자치도') return '제주';
    return first;
  }
  return '';
}

export const SearchBar: React.FC<SearchBarProps> = ({
  institutions,
  selectedInstitutionId,
  onSelectInstitution,
  availableInstitutionIds,
  onlyWithMeals = false,
}) => {
  const [query, setQuery] = useState('');
  const [isOpen, setIsOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);
  const containerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const trimmed = query.trim().toLowerCase();

  // Filter institutions based on search query and onlyWithMeals flag
  // Crucial: always prioritize meal data institutions first so users discover meals immediately!
  const filtered = useMemo(() => {
    const baseList = onlyWithMeals
      ? institutions.filter((inst) => Boolean(availableInstitutionIds?.has(inst.institution_id)))
      : institutions;

    if (!trimmed) {
      // Prioritize data institutions first
      return [...baseList].sort((a, b) => {
        const aHasData = availableInstitutionIds?.has(a.institution_id) ? 1 : 0;
        const bHasData = availableInstitutionIds?.has(b.institution_id) ? 1 : 0;
        if (bHasData !== aHasData) return bHasData - aHasData;
        return a.name.localeCompare(b.name, 'ko');
      });
    }

    const matches = baseList.filter((inst) => {
      const region = extractRegion(inst.address).toLowerCase();
      return (
        inst.name.toLowerCase().includes(trimmed) ||
        inst.short_name.toLowerCase().includes(trimmed) ||
        inst.type_korean.toLowerCase().includes(trimmed) ||
        inst.address.toLowerCase().includes(trimmed) ||
        region.includes(trimmed)
      );
    });

    return [...matches].sort((a, b) => {
      const aHasData = availableInstitutionIds?.has(a.institution_id) ? 1 : 0;
      const bHasData = availableInstitutionIds?.has(b.institution_id) ? 1 : 0;
      if (bHasData !== aHasData) return bHasData - aHasData;
      return a.name.localeCompare(b.name, 'ko');
    });
  }, [institutions, trimmed, availableInstitutionIds, onlyWithMeals]);

  // Close dropdown on click outside
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleSelect = (inst: Institution) => {
    onSelectInstitution(inst.institution_id);
    setQuery(inst.name);
    setIsOpen(false);
    setActiveIndex(-1);
  };

  const handleClear = () => {
    setQuery('');
    setActiveIndex(-1);
    inputRef.current?.focus();
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (!isOpen || filtered.length === 0) {
      if (e.key === 'ArrowDown' && filtered.length > 0) {
        setIsOpen(true);
      }
      return;
    }

    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setActiveIndex((prev) => (prev < filtered.length - 1 ? prev + 1 : 0));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setActiveIndex((prev) => (prev > 0 ? prev - 1 : filtered.length - 1));
    } else if (e.key === 'Enter') {
      e.preventDefault();
      if (activeIndex >= 0 && activeIndex < filtered.length) {
        handleSelect(filtered[activeIndex]);
      } else if (filtered.length > 0) {
        handleSelect(filtered[0]);
      }
    } else if (e.key === 'Escape') {
      setIsOpen(false);
      setActiveIndex(-1);
    }
  };

  return (
    <div ref={containerRef} className="relative w-full">
      <div className="relative flex items-center">
        <div className="absolute left-3.5 pointer-events-none text-slate-400">
          <Search className="w-5 h-5 text-blue-600" aria-hidden="true" />
        </div>
        <input
          ref={inputRef}
          type="text"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setIsOpen(true);
            setActiveIndex(-1);
          }}
          onFocus={() => {
            setIsOpen(true);
          }}
          onKeyDown={handleKeyDown}
          placeholder="교정기관 검색 (예: 목포교도소, 부산교도소, 서울남부교도소, 서울구치소)"
          aria-label="교정기관 검색"
          aria-expanded={isOpen}
          aria-autocomplete="list"
          role="combobox"
          className="w-full pl-11 pr-10 py-3 bg-white border-2 border-slate-300 rounded-xl text-sm sm:text-base placeholder:text-slate-400 text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-600 focus:border-blue-600 shadow-sm transition"
        />
        {query && (
          <button
            type="button"
            onClick={handleClear}
            className="absolute right-3 p-1 rounded-full text-slate-400 hover:text-slate-600 focus:outline-none focus:ring-2 focus:ring-blue-600"
            aria-label="검색어 지우기"
          >
            <X className="w-4 h-4" />
          </button>
        )}
      </div>

      {/* Dropdown Results */}
      {isOpen && (
        <div
          role="listbox"
          className="absolute left-0 right-0 mt-1.5 max-h-80 overflow-y-auto bg-white border border-slate-200 rounded-xl shadow-xl z-50 divide-y divide-slate-100"
        >
          {filtered.length === 0 ? (
            <div className="p-4 text-center text-sm text-slate-500">
              검색된 교정기관이 없습니다. (전국 55개 교정기관 대상)
            </div>
          ) : (
            filtered.map((inst, index) => {
              const isSelected = inst.institution_id === selectedInstitutionId;
              const isHighlighted = index === activeIndex;
              const hasMealData = availableInstitutionIds?.has(inst.institution_id);
              const region = extractRegion(inst.address);

              return (
                <div
                  key={inst.institution_id}
                  role="option"
                  aria-selected={isSelected}
                  onClick={() => handleSelect(inst)}
                  onMouseEnter={() => setActiveIndex(index)}
                  className={`p-3 sm:p-3.5 cursor-pointer transition flex items-center justify-between gap-3 ${
                    isHighlighted ? 'bg-blue-50/80 text-blue-950' : 'hover:bg-slate-50 text-slate-900'
                  }`}
                >
                  <div className="space-y-1 min-w-0">
                    <div className="flex flex-wrap items-center gap-1.5">
                      <span className="font-bold text-sm text-slate-900">{inst.name}</span>
                      <span className="text-[11px] px-2 py-0.5 rounded-full bg-slate-100 text-slate-700 font-medium">
                        {inst.type_korean}
                      </span>
                      {region && (
                        <span className="text-[11px] px-1.5 py-0.5 rounded bg-blue-50 text-blue-700 font-medium">
                          {region}
                        </span>
                      )}
                      {hasMealData ? (
                        <span className="text-[10px] px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-800 font-bold border border-emerald-200">
                          식단 있음
                        </span>
                      ) : (
                        <span className="text-[10px] px-2 py-0.5 rounded-full bg-slate-100 text-slate-500 font-medium border border-slate-200">
                          준비 중
                        </span>
                      )}
                    </div>
                    <p className="text-xs text-slate-500 truncate">{inst.address}</p>
                  </div>

                  <div className="shrink-0 flex items-center gap-1.5 text-xs">
                    {inst.has_coordinates ? (
                      <span className="inline-flex items-center gap-1 text-slate-500" title="지도 마커 등록됨">
                        <MapPin className="w-3.5 h-3.5 text-blue-600" />
                        <span className="hidden sm:inline text-[11px]">좌표 보유</span>
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 text-amber-700 bg-amber-50 px-2 py-0.5 rounded border border-amber-200" title="좌표 확인 중 (상세 패널로 식단 조회 가능)">
                        <MapPinOff className="w-3.5 h-3.5 text-amber-600" />
                        <span className="text-[11px] font-semibold">위치 확인 중</span>
                      </span>
                    )}
                  </div>
                </div>
              );
            })
          )}
        </div>
      )}
    </div>
  );
};
