import React from 'react';
import { RotateCw, AlertTriangle, Compass, MapPinOff } from 'lucide-react';

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
}

export const EmptyInstitutionState: React.FC<EmptyInstitutionStateProps> = () => {
  return (
    <div className="min-h-[460px] flex flex-col items-center justify-center p-8 bg-white border border-slate-200 rounded-2xl shadow-sm text-center space-y-4">
      <div className="w-16 h-16 rounded-2xl bg-slate-100 flex items-center justify-center text-slate-400">
        <Compass className="w-8 h-8 text-blue-600" />
      </div>
      <div className="space-y-1.5 max-w-sm">
        <h3 className="text-base font-bold text-slate-900">지도에서 교정기관을 선택하세요</h3>
        <p className="text-xs text-slate-500 leading-relaxed">
          좌측 대한민국 지도에서 마커를 클릭하거나, 상단 검색창에서 원하는 교정기관명(예: 서울구치소,
          목포교도소)을 입력하여 식단을 조회할 수 있습니다.
        </p>
      </div>

      <div className="pt-2 text-xs text-slate-400 flex items-center gap-1.5">
        <MapPinOff className="w-3.5 h-3.5" />
        <span>좌표가 없는 기관도 검색창을 통해 정상 조회 가능합니다.</span>
      </div>
    </div>
  );
};
