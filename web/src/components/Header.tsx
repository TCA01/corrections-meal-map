import React from 'react';
import { Utensils, Clock, FileSpreadsheet } from 'lucide-react';
import { formatDataScope } from '../data/adapter';

interface HeaderProps {
  datasetVersion?: string;
  webContractVersion?: string;
  lastUpdated?: string;
  dataScope?: string;
  isMockFixture?: boolean;
}

export const Header: React.FC<HeaderProps> = ({
  datasetVersion: _datasetVersion,
  webContractVersion: _webContractVersion,
  lastUpdated,
  dataScope,
  isMockFixture,
}) => {
  // Format lastUpdated date string: e.g. 2026.10.01
  const formattedUpdate = lastUpdated
    ? lastUpdated.split('T')[0].replace(/-/g, '.')
    : undefined;

  const scopeInfo = formatDataScope(dataScope);

  return (
    <header className="bg-slate-900 text-white border-b border-slate-800 shadow-sm sticky top-0 z-30">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-3.5 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-blue-600 flex items-center justify-center text-white shadow-md shadow-blue-900/40 shrink-0">
            <Utensils className="w-5 h-5" aria-hidden="true" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-lg sm:text-xl font-bold tracking-tight text-white">
                교정 식단 데이터맵
              </h1>
              <span className="hidden sm:inline-block text-xs font-medium text-slate-400">
                Corrections Meal Data Map
              </span>
            </div>
            <p className="text-xs text-slate-300">
              전국 교정기관 수용자 식단정보 자동 수집·구조화 조회 서비스
            </p>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2 text-xs">
          {isMockFixture && (
            <span className="inline-flex items-center px-2 py-0.5 rounded text-amber-300 bg-amber-950/80 border border-amber-800 font-medium">
              테스트 환경
            </span>
          )}

          {dataScope && (
            <span
              className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full bg-slate-800/90 text-blue-300 border border-slate-700"
              title={scopeInfo.description}
            >
              <FileSpreadsheet className="w-3.5 h-3.5 text-blue-400" />
              <span>{scopeInfo.badge}</span>
            </span>
          )}

          {formattedUpdate && (
            <span
              className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full bg-slate-800 text-slate-300 border border-slate-700"
              title={`최종 갱신 시각: ${lastUpdated}`}
            >
              <Clock className="w-3.5 h-3.5 text-emerald-400" />
              <span>데이터 갱신: {formattedUpdate}</span>
            </span>
          )}
        </div>
      </div>
    </header>
  );
};
