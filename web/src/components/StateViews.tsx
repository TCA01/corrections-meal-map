import React from 'react';
import { RotateCw, AlertTriangle, Compass, MapPinOff, Utensils, Sparkles } from 'lucide-react';

interface LoadingStateProps {
  message?: string;
}

export const LoadingState: React.FC<LoadingStateProps> = ({
  message = '교정기관 및 식단 기준정보를 불러오는 중입니다...',
}) => {
  return (
    <div
      role="status"
      aria-live="polite"
      className="min-h-[400px] flex flex-col items-center justify-center p-8 bg-white border border-slate-200 rounded-2xl shadow-sm text-center space-y-3"
    >
      <div className="p-3 bg-blue-50 text-blue-600 rounded-full animate-spin">
        <RotateCw className="w-8 h-8" />
      </div>
      <div className="space-y-1">
        <h3 className="text-base font-bold text-slate-900">데이터 로딩 중</h3>
        <p className="text-xs sm:text-sm text-slate-500 max-w-sm">{message}</p>
      </div>
    </div>
  );
};

interface ErrorStateProps {
  title?: string;
  message: string;
  onRetry?: () => void;
}

export const ErrorState: React.FC<ErrorStateProps> = ({
  title = '데이터셋을 불러올 수 없습니다',
  message,
  onRetry,
}) => {
  return (
    <div
      role="alert"
      className="min-h-[350px] flex flex-col items-center justify-center p-8 bg-white border border-red-200 rounded-2xl shadow-sm text-center space-y-4"
    >
      <div className="p-3 bg-red-50 text-red-600 rounded-full">
        <AlertTriangle className="w-8 h-8" />
      </div>
      <div className="space-y-1.5 max-w-md">
        <h3 className="text-base font-bold text-slate-900">{title}</h3>
        <p className="text-xs sm:text-sm text-slate-600 leading-relaxed">{message}</p>
      </div>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="px-4 py-2 bg-blue-600 text-white text-xs sm:text-sm font-semibold rounded-xl hover:bg-blue-700 transition focus:outline-none focus:ring-2 focus:ring-blue-600 shadow-sm cursor-pointer"
        >
          데이터 다시 불러오기
        </button>
      )}
    </div>
  );
};

interface EmptyInstitutionStateProps {
  onQuickSelect?: (institutionId: string) => void;
  sampleInstitutionName?: string;
  onSelectSampleMeal?: () => void;
  onlyWithMeals?: boolean;
  onToggleOnlyWithMeals?: (val: boolean) => void;
  availableCount?: number;
}

export const EmptyInstitutionState: React.FC<EmptyInstitutionStateProps> = ({
  sampleInstitutionName,
  onSelectSampleMeal,
  onlyWithMeals = false,
  onToggleOnlyWithMeals,
  availableCount,
}) => {
  return (
    <div className="min-h-[460px] flex flex-col items-center justify-center p-6 sm:p-8 bg-white border border-slate-200 rounded-2xl shadow-sm text-center space-y-5">
      <div className="w-16 h-16 rounded-2xl bg-blue-50 flex items-center justify-center text-blue-600 shadow-inner">
        <Compass className="w-8 h-8" />
      </div>

      <div className="space-y-1.5 max-w-sm">
        <h3 className="text-base font-bold text-slate-900">지도에서 교정기관을 선택하세요</h3>
        <p className="text-xs text-slate-500 leading-relaxed">
          좌측 대한민국 지도에서 마커를 클릭하거나, 상단 검색창에서 원하는 교정기관명(예: 목포교도소,
          부산교도소)을 입력하여 식단을 조회할 수 있습니다.
        </p>
      </div>

      {/* Quick Demonstration Actions */}
      <div className="w-full max-w-xs space-y-2 pt-1">
        {onSelectSampleMeal && (
          <button
            type="button"
            onClick={onSelectSampleMeal}
            className="w-full py-2.5 px-4 bg-blue-600 hover:bg-blue-700 text-white rounded-xl text-xs sm:text-sm font-bold shadow-md hover:shadow-lg transition flex items-center justify-center gap-2 cursor-pointer"
          >
            <Sparkles className="w-4 h-4 text-amber-300" />
            <span>예시 식단 바로 보기{sampleInstitutionName ? ` (${sampleInstitutionName})` : ''}</span>
          </button>
        )}

        {onToggleOnlyWithMeals && (
          <button
            type="button"
            onClick={() => onToggleOnlyWithMeals(!onlyWithMeals)}
            className={`w-full py-2 px-3 rounded-xl text-xs font-semibold border transition flex items-center justify-center gap-1.5 cursor-pointer ${
              onlyWithMeals
                ? 'bg-emerald-50 text-emerald-800 border-emerald-300 hover:bg-emerald-100'
                : 'bg-slate-50 text-slate-700 border-slate-200 hover:bg-slate-100'
            }`}
          >
            <Utensils className="w-3.5 h-3.5 text-blue-600" />
            <span>
              {onlyWithMeals
                ? '전체 기관 보기 (준비 중 포함)'
                : `식단 있는 기관만 보기${availableCount ? ` (${availableCount}개소)` : ''}`}
            </span>
          </button>
        )}
      </div>

      <div className="pt-2 text-xs text-slate-400 flex items-center gap-1.5">
        <MapPinOff className="w-3.5 h-3.5" />
        <span>전국 55개 교정기관의 기준정보를 검색창에서 확인 가능합니다.</span>
      </div>
    </div>
  );
};
