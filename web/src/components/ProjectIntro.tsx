import React from 'react';
import { Sparkles, Info } from 'lucide-react';

interface ProjectIntroProps {
  fixtureNotice?: string;
  dataScope?: string;
  onSelectSampleMeal?: () => void;
  sampleInstitutionName?: string;
}

export const ProjectIntro: React.FC<ProjectIntroProps> = ({
  fixtureNotice,
  dataScope,
  onSelectSampleMeal,
}) => {
  return (
    <div className="bg-white border border-slate-200 rounded-xl p-4 sm:p-5 shadow-sm space-y-3">
      <div className="flex items-start gap-3">
        <div className="p-2 rounded-lg bg-blue-50 text-blue-700 mt-0.5 shrink-0">
          <Sparkles className="w-4 h-4" aria-hidden="true" />
        </div>
        <div className="space-y-1">
          <h2 className="text-sm font-semibold text-slate-900 flex items-center gap-2">
            법무행정 디지털 혁신 과제 — 비정형 공공데이터 표준화
          </h2>
          <p className="text-xs sm:text-sm text-slate-600 leading-relaxed">
            교정기관마다 XLSX · XLS · PDF · HWP · HWPX 등 서로 다른 형식으로 공개되는 수용자 식단표를
            자동 수집·검증·구조화하여 한 곳에서 조회할 수 있도록 개발된 디지털 교정행정 데이터 서비스입니다.
            다양한 비정형 문서 포맷을 단계별로 처리할 수 있도록 파이프라인을 구축 중이며,
            {dataScope === 'excel_ready_only' ? (
              <strong className="text-slate-800 font-semibold"> 현재 1단계로 엄격한 데이터 검증을 통과한 Excel 기반 식단 데이터를 우선 제공합니다.</strong>
            ) : (
              ' 현재 검증 완료된 표준 식단 데이터를 제공합니다.'
            )}
          </p>
        </div>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-y-2 gap-x-4 pt-2 border-t border-slate-100 text-xs text-slate-500">
        <div className="flex flex-wrap items-center gap-y-1 gap-x-2">
          <span className="font-semibold text-slate-700">30초 빠른 탐색:</span>
          <span>1. 교정기관 검색 / 지도</span>
          <span>→</span>
          <span>2. 기관 선택</span>
          <span>→</span>
          <span>3. 연도 / 월 선택</span>
          <span>→</span>
          <span>4. 날짜 선택</span>
          <span>→</span>
          <span>5. 아침 · 점심 · 저녁 식단 및 원본 출처 확인</span>
        </div>

        {onSelectSampleMeal && (
          <button
            type="button"
            onClick={onSelectSampleMeal}
            className="inline-flex items-center gap-1.5 px-3 py-1 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-xs font-bold shadow-sm transition cursor-pointer shrink-0"
          >
            <Sparkles className="w-3.5 h-3.5 text-amber-300" />
            <span>예시 식단 바로 보기</span>
          </button>
        )}
      </div>

      {fixtureNotice && (
        <div className="flex items-center gap-2 text-xs bg-amber-50 text-amber-800 border border-amber-200/80 rounded-lg px-3 py-2">
          <Info className="w-4 h-4 shrink-0 text-amber-600" />
          <span>{fixtureNotice}</span>
        </div>
      )}
    </div>
  );
};
