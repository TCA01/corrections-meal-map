import React from 'react';
import { Calendar as CalendarIcon, CheckCircle2, AlertCircle } from 'lucide-react';
import { MonthMenu } from '../data/types';
import { hasMealDataForDate } from '../data/adapter';

interface CalendarViewProps {
  year: number;
  month: number;
  monthMenu: MonthMenu | null;
  selectedDate: string | null;
  onSelectDate: (dateStr: string) => void;
}

const WEEKDAYS = ['일', '월', '화', '수', '목', '금', '토'];

export const CalendarView: React.FC<CalendarViewProps> = ({
  year,
  month,
  monthMenu,
  selectedDate,
  onSelectDate,
}) => {
  // Number of days in the current month
  const daysInMonth = new Date(year, month, 0).getDate();
  // Day of the week for the 1st of the month (0 = Sun, 6 = Sat)
  const firstDayOfWeek = new Date(year, month - 1, 1).getDay();

  // Create array of empty slots for alignment
  const blanks = Array.from({ length: firstDayOfWeek }, (_, i) => i);
  // Create array of days 1 to daysInMonth
  const days = Array.from({ length: daysInMonth }, (_, i) => i + 1);

  // Count how many days actually have meal data
  let availableDaysCount = 0;
  days.forEach((d) => {
    const dateStr = `${year}-${String(month).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
    if (hasMealDataForDate(monthMenu, dateStr)) {
      availableDaysCount++;
    }
  });

  return (
    <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1.5 text-xs font-semibold text-slate-800">
          <CalendarIcon className="w-3.5 h-3.5 text-blue-600" />
          <span>
            {year}년 {month}월 달력
          </span>
        </div>
        <div className="text-[11px] text-slate-500">
          식단 제공일: <strong className="text-blue-700">{availableDaysCount}일</strong> / {daysInMonth}일
        </div>
      </div>

      {/* Weekday headers */}
      <div className="grid grid-cols-7 gap-1 text-center text-[11px] font-semibold text-slate-500 border-b border-slate-100 pb-1.5">
        {WEEKDAYS.map((wd, idx) => (
          <span
            key={wd}
            className={idx === 0 ? 'text-red-500' : idx === 6 ? 'text-blue-500' : 'text-slate-600'}
          >
            {wd}
          </span>
        ))}
      </div>

      {/* Day cells grid */}
      <div className="grid grid-cols-7 gap-1" role="grid" aria-label={`${year}년 ${month}월 식단 달력`}>
        {/* Leading empty cells */}
        {blanks.map((b) => (
          <div key={`blank-${b}`} className="h-9 sm:h-10" />
        ))}

        {/* Days of the month */}
        {days.map((d) => {
          const dateStr = `${year}-${String(month).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
          const dayOfWeek = (firstDayOfWeek + d - 1) % 7;
          const hasData = hasMealDataForDate(monthMenu, dateStr);
          const isSelected = selectedDate === dateStr;

          return (
            <button
              key={dateStr}
              type="button"
              disabled={!hasData}
              onClick={() => onSelectDate(dateStr)}
              aria-selected={isSelected}
              aria-disabled={!hasData}
              title={hasData ? `${dateStr} 식단 조회` : `${dateStr} 식단 정보 없음`}
              className={`h-9 sm:h-10 rounded-lg text-xs font-medium flex flex-col items-center justify-center relative transition focus:outline-none focus:ring-2 focus:ring-blue-600 ${
                isSelected
                  ? 'bg-blue-600 text-white font-bold ring-2 ring-blue-600 shadow-sm z-10'
                  : hasData
                  ? 'bg-blue-50/70 border border-blue-200 text-blue-950 hover:bg-blue-100 hover:border-blue-400 cursor-pointer'
                  : 'text-slate-300 border border-transparent cursor-not-allowed opacity-50'
              }`}
            >
              <span
                className={`${
                  isSelected
                    ? 'text-white'
                    : dayOfWeek === 0
                    ? 'text-red-600'
                    : dayOfWeek === 6
                    ? 'text-blue-600'
                    : 'text-slate-800'
                }`}
              >
                {d}
              </span>
              {hasData && (
                <span
                  className={`w-1 h-1 rounded-full mt-0.5 ${
                    isSelected ? 'bg-white' : 'bg-blue-600'
                  }`}
                  aria-hidden="true"
                />
              )}
            </button>
          );
        })}
      </div>

      {availableDaysCount === 0 && (
        <div className="flex items-center gap-1.5 p-3 rounded-lg bg-slate-50 border border-slate-200 text-slate-500 text-xs">
          <AlertCircle className="w-4 h-4 shrink-0 text-slate-400" />
          <span>본 월에는 아직 등록된 일별 식단 데이터가 없습니다.</span>
        </div>
      )}

      {selectedDate && (
        <div className="text-[11px] text-slate-500 flex items-center justify-between pt-1 border-t border-slate-100">
          <span className="flex items-center gap-1 text-blue-700 font-medium">
            <CheckCircle2 className="w-3.5 h-3.5 text-blue-600" />
            선택된 날짜: {selectedDate}
          </span>
          <span>식단 정보만 선택 가능</span>
        </div>
      )}
    </div>
  );
};
