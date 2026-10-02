import React from 'react';
import { Calendar as CalendarIcon } from 'lucide-react';

interface YearMonthSelectorProps {
  availableYears: number[];
  selectedYear: number | null;
  onSelectYear: (year: number) => void;
  availableMonths: number[];
  selectedMonth: number | null;
  onSelectMonth: (month: number) => void;
}

export const YearMonthSelector: React.FC<YearMonthSelectorProps> = ({
  availableYears,
  selectedYear,
  onSelectYear,
  availableMonths,
  selectedMonth,
  onSelectMonth,
}) => {
  const months = Array.from({ length: 12 }, (_, i) => i + 1);

  if (availableYears.length === 0) {
    return (
      <div className="p-4 bg-slate-50 rounded-xl border border-slate-200 text-center text-xs text-slate-500">
        등록된 식단표 연도/월 정보가 없습니다.
      </div>
    );
  }

  return (
    <div className="space-y-3 bg-white p-4 rounded-xl border border-slate-200 shadow-sm">
      {/* Year Selection */}
      <div className="flex items-center justify-between gap-3">
        <label htmlFor="year-select" className="text-xs font-semibold text-slate-700 flex items-center gap-1.5">
          <CalendarIcon className="w-3.5 h-3.5 text-blue-600" />
          <span>조회 연도 선택</span>
        </label>
        <select
          id="year-select"
          value={selectedYear || ''}
          onChange={(e) => onSelectYear(Number(e.target.value))}
          className="px-3 py-1.5 bg-slate-50 border border-slate-300 rounded-lg text-sm font-semibold text-slate-800 focus:outline-none focus:ring-2 focus:ring-blue-600 focus:bg-white transition cursor-pointer"
        >
          {availableYears.map((y) => (
            <option key={y} value={y}>
              {y}년
            </option>
          ))}
        </select>
      </div>

      {/* Month Selection Grid (1 ~ 12) */}
      <div>
        <div className="text-[11px] font-medium text-slate-500 mb-2 flex items-center justify-between">
          <span>조회 월 선택 (식단 보유 월만 활성화)</span>
          <span className="text-slate-400">{availableMonths.length}개월 보유</span>
        </div>
        <div className="grid grid-cols-4 sm:grid-cols-6 gap-1.5" role="group" aria-label="월 선택">
          {months.map((m) => {
            const isAvailable = availableMonths.includes(m);
            const isSelected = selectedMonth === m;

            return (
              <button
                key={m}
                type="button"
                disabled={!isAvailable}
                onClick={() => onSelectMonth(m)}
                aria-pressed={isSelected}
                aria-disabled={!isAvailable}
                className={`py-2 px-1 text-xs rounded-lg font-medium transition text-center focus:outline-none focus:ring-2 focus:ring-blue-500 ${
                  isSelected
                    ? 'bg-blue-600 text-white font-bold shadow-sm'
                    : isAvailable
                    ? 'bg-blue-50 text-blue-900 border border-blue-200 hover:bg-blue-100 hover:border-blue-300 cursor-pointer'
                    : 'bg-slate-50 text-slate-300 border border-slate-100 cursor-not-allowed opacity-60'
                }`}
                title={isAvailable ? `${m}월 식단표 조회` : `${m}월 식단 데이터 없음`}
              >
                {m}월
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
};
