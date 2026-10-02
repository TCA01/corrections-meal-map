import React from 'react';
import {
  Building2,
  MapPin,
  MapPinOff,
  Phone,
  Calendar,
  AlertCircle,
  ExternalLink,
  RotateCw,
  X,
} from 'lucide-react';
import { Institution, Manifest, MonthMenu } from '../data/types';
import { getAvailableMonths, getAvailableYears } from '../data/adapter';
import { YearMonthSelector } from './YearMonthSelector';
import { CalendarView } from './CalendarView';
import { MealView } from './MealView';
import { SourceCard } from './SourceCard';

interface InstitutionDetailProps {
  institution: Institution;
  manifest: Manifest | null;
  selectedYear: number | null;
  onSelectYear: (year: number) => void;
  selectedMonth: number | null;
  onSelectMonth: (month: number) => void;
  monthMenu: MonthMenu | null;
  isMonthMenuLoading: boolean;
  monthMenuError: string | null;
  onRetryMonthMenu: () => void;
  selectedDate: string | null;
  onSelectDate: (dateStr: string) => void;
  onClose: () => void;
  onSelectSampleMeal?: () => void;
}

export const InstitutionDetail: React.FC<InstitutionDetailProps> = ({
  institution,
  manifest,
  selectedYear,
  onSelectYear,
  selectedMonth,
  onSelectMonth,
  monthMenu,
  isMonthMenuLoading,
  monthMenuError,
  onRetryMonthMenu,
  selectedDate,
  onSelectDate,
  onClose,
  onSelectSampleMeal,
}) => {
  const dataInstitutionsCount = manifest?.stats?.collected_institutions;
  const availableYears = getAvailableYears(manifest, institution.institution_id);
  const availableMonths = selectedYear
    ? getAvailableMonths(manifest, institution.institution_id, selectedYear)
    : [];

  const hasDataInManifest = availableYears.length > 0;
  const currentDayMenu =
    selectedDate && monthMenu?.days ? monthMenu.days[selectedDate] || null : null;

  return (
    <div className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden flex flex-col">
      {/* Top Header Card */}
      <div className="p-4 sm:p-5 border-b border-slate-100 bg-gradient-to-b from-slate-50 to-white">
        <div className="flex items-start justify-between gap-3">
          <div className="space-y-1">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-xs font-semibold px-2 py-0.5 rounded-full bg-blue-100 text-blue-800">
                {institution.type_korean}
              </span>
              {institution.has_coordinates ? (
                <span className="text-[11px] font-medium px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200 flex items-center gap-1">
                  <MapPin className="w-3 h-3 text-emerald-600" />
                  지도 마커 등록
                </span>
              ) : (
                <span
                  className="text-[11px] font-medium px-2 py-0.5 rounded-full bg-amber-50 text-amber-700 border border-amber-200 flex items-center gap-1"
                  title="위치 좌표 확인 중 (식단 조회 정상 가능)"
                >
                  <MapPinOff className="w-3 h-3 text-amber-600" />
                  위치 좌표 확인 중 (식단 조회 가능)
                </span>
              )}
            </div>

            <h2 className="text-xl font-bold text-slate-900 tracking-tight flex items-center gap-2">
              <Building2 className="w-5 h-5 text-blue-600 shrink-0" />
              <span>{institution.name}</span>
            </h2>
          </div>

          <button
            type="button"
            onClick={onClose}
            aria-label="기관 선택 해제"
            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition focus:outline-none focus:ring-2 focus:ring-blue-600"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Institution Metadata */}
        <div className="mt-3 pt-3 border-t border-slate-100/80 text-xs text-slate-600 space-y-1.5">
          <div className="flex items-start gap-1.5">
            <MapPin className="w-3.5 h-3.5 text-slate-400 shrink-0 mt-0.5" />
            <span>{institution.address}</span>
            {institution.postal_code && (
              <span className="text-slate-400">({institution.postal_code})</span>
            )}
          </div>
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-slate-500">
            {institution.phone && (
              <span className="flex items-center gap-1">
                <Phone className="w-3.5 h-3.5 text-slate-400" />
                {institution.phone}
              </span>
            )}
            {institution.source_url && (
              <a
                href={institution.source_url}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-1 text-blue-600 hover:underline"
              >
                <span>교정본부 기관 안내</span>
                <ExternalLink className="w-3 h-3" />
              </a>
            )}
          </div>
        </div>
      </div>

      {/* Main Body */}
      <div className="p-4 sm:p-5 space-y-5">
        {!hasDataInManifest ? (
          /* Empty state for institution without data */
          <div className="py-12 px-4 bg-slate-50 border border-dashed border-slate-200 rounded-xl text-center space-y-4">
            <div className="w-12 h-12 rounded-full bg-slate-100 flex items-center justify-center mx-auto text-slate-400">
              <Calendar className="w-6 h-6" />
            </div>
            <div className="space-y-1">
              <h3 className="text-sm font-bold text-slate-700">현재 구조화된 식단 데이터가 없습니다</h3>
              <p className="text-xs text-slate-500 max-w-sm mx-auto leading-relaxed">
                식단 데이터 수집·구조화 대기 중인 기관입니다. 현재 검증 완료된 {dataInstitutionsCount ? `${dataInstitutionsCount}개 ` : ''}교정기관의 식단 데이터를 우선
                제공하고 있으며, 본 기관의 식단표는 후속 파이프라인 연동 시 순차 업데이트됩니다.
              </p>
            </div>
            {onSelectSampleMeal && (
              <div className="pt-1">
                <button
                  type="button"
                  onClick={onSelectSampleMeal}
                  className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl bg-blue-600 text-white text-xs font-semibold hover:bg-blue-700 transition shadow-sm cursor-pointer"
                >
                  식단 있는 기관 바로 보기
                </button>
              </div>
            )}
          </div>
        ) : (
          <>
            {/* Year & Month Selection */}
            <YearMonthSelector
              availableYears={availableYears}
              selectedYear={selectedYear}
              onSelectYear={onSelectYear}
              availableMonths={availableMonths}
              selectedMonth={selectedMonth}
              onSelectMonth={onSelectMonth}
            />

            {/* Month Menu Content */}
            {isMonthMenuLoading ? (
              <div className="py-12 text-center space-y-3 bg-slate-50 rounded-xl border border-slate-200">
                <RotateCw className="w-6 h-6 text-blue-600 animate-spin mx-auto" />
                <p className="text-xs font-semibold text-slate-700">식단 데이터를 불러오는 중입니다...</p>
              </div>
            ) : monthMenuError ? (
              <div className="p-4 bg-red-50 border border-red-200 rounded-xl text-xs text-red-700 space-y-2">
                <div className="flex items-center gap-1.5 font-bold">
                  <AlertCircle className="w-4 h-4 text-red-600" />
                  <span>식단 데이터 조회 실패</span>
                </div>
                <p>{monthMenuError}</p>
                <button
                  type="button"
                  onClick={onRetryMonthMenu}
                  className="px-3 py-1.5 rounded-lg bg-red-600 text-white font-medium hover:bg-red-700 transition"
                >
                  다시 시도
                </button>
              </div>
            ) : selectedYear && selectedMonth && monthMenu ? (
              <div className="space-y-5">
                {/* Calendar View */}
                <CalendarView
                  year={selectedYear}
                  month={selectedMonth}
                  monthMenu={monthMenu}
                  selectedDate={selectedDate}
                  onSelectDate={onSelectDate}
                />

                {/* Meal View */}
                {selectedDate ? (
                  <div className="space-y-4">
                    <MealView dateStr={selectedDate} dayMenu={currentDayMenu} />
                    <SourceCard
                      sources={monthMenu.sources}
                      dayMenu={currentDayMenu}
                      institutionName={institution.name}
                      year={selectedYear}
                      month={selectedMonth}
                    />
                  </div>
                ) : (
                  <div className="p-4 bg-blue-50/60 border border-blue-200 rounded-xl text-center text-xs text-blue-900 space-y-1">
                    <p className="font-semibold">달력에서 확인하실 날짜를 선택해주세요.</p>
                    <p className="text-blue-700 text-[11px]">
                      점(●) 또는 색상으로 표시된 날짜에 수용자 식단 데이터가 등록되어 있습니다.
                    </p>
                  </div>
                )}
              </div>
            ) : (
              <div className="p-4 bg-slate-50 rounded-xl text-center text-xs text-slate-500">
                연도 및 월을 선택해주세요.
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
};
