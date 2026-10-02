import React from 'react';
import { Sunrise, Sun, Moon, AlertCircle, Utensils } from 'lucide-react';
import { DayMenu, MealSlotData, MenuItem } from '../data/types';

interface MealViewProps {
  dateStr: string;
  dayMenu: DayMenu | null;
}

const WEEKDAY_NAMES = ['일요일', '월요일', '화요일', '수요일', '목요일', '금요일', '토요일'];

export const MealView: React.FC<MealViewProps> = ({ dateStr, dayMenu }) => {
  // Format Korean date string: e.g. 2026년 9월 30일 수요일
  const [y, m, d] = dateStr.split('-').map(Number);
  const dateObj = new Date(y, m - 1, d);
  const weekdayName = WEEKDAY_NAMES[dateObj.getDay()] || '';

  const mealSlots: Array<{
    id: 'breakfast' | 'lunch' | 'dinner';
    label: '아침' | '점심' | '저녁';
    subLabel: string;
    icon: React.ComponentType<{ className?: string }>;
    accentColor: string;
    slot?: MealSlotData | null;
  }> = [
    {
      id: 'breakfast',
      label: '아침',
      subLabel: '조식',
      icon: Sunrise,
      accentColor: 'text-amber-600 bg-amber-50 border-amber-200',
      slot: dayMenu?.breakfast,
    },
    {
      id: 'lunch',
      label: '점심',
      subLabel: '중식',
      icon: Sun,
      accentColor: 'text-orange-600 bg-orange-50 border-orange-200',
      slot: dayMenu?.lunch,
    },
    {
      id: 'dinner',
      label: '저녁',
      subLabel: '석식',
      icon: Moon,
      accentColor: 'text-indigo-600 bg-indigo-50 border-indigo-200',
      slot: dayMenu?.dinner,
    },
  ];

  return (
    <div className="space-y-4">
      {/* Date Title Banner */}
      <div className="flex items-center justify-between bg-slate-900 text-white px-4 py-3 rounded-xl shadow-sm">
        <div className="flex items-center gap-2">
          <Utensils className="w-4 h-4 text-blue-400" />
          <h3 className="text-sm sm:text-base font-bold tracking-tight">
            {y}년 {m}월 {d}일 <span className="font-medium text-slate-300">({weekdayName})</span>
          </h3>
        </div>
        <span className="text-xs text-blue-200 bg-blue-950/80 px-2.5 py-0.5 rounded-full border border-blue-800">
          수용자 일일 식단표
        </span>
      </div>

      {/* 3 Meal Sections / Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3.5">
        {mealSlots.map((item) => {
          const Icon = item.icon;
          const rawSlot = item.slot as any;
          const items: MenuItem[] = rawSlot?.menu_items || (Array.isArray(rawSlot) ? rawSlot : []);
          const hasItems = items.length > 0;

          return (
            <div
              key={item.id}
              className="bg-white border border-slate-200 rounded-xl p-4 shadow-sm flex flex-col justify-between hover:border-slate-300 transition"
            >
              <div>
                {/* Header */}
                <div className="flex items-center justify-between pb-2.5 border-b border-slate-100 mb-3">
                  <div className="flex items-center gap-2">
                    <div className={`p-1.5 rounded-lg border ${item.accentColor}`}>
                      <Icon className="w-4 h-4" />
                    </div>
                    <div>
                      <span className="font-bold text-sm text-slate-900">{item.label}</span>
                      <span className="text-xs text-slate-400 ml-1.5">({item.subLabel})</span>
                    </div>
                  </div>
                  <span className="text-[11px] font-semibold text-slate-500">
                    {hasItems ? `${items.length}개 품목` : '0개'}
                  </span>
                </div>

                {/* Menu items list or empty notice */}
                {hasItems ? (
                  <ul className="space-y-1.5" role="list">
                    {items.map((menuItem, idx) => {
                      const hasDistinctRaw =
                        menuItem.raw_text && menuItem.raw_text !== menuItem.name;

                      return (
                        <li
                          key={idx}
                          className="text-xs sm:text-sm text-slate-800 bg-slate-50 px-3 py-2 rounded-lg border border-slate-100 flex items-center justify-between"
                        >
                          <span className="font-semibold">{menuItem.name}</span>
                          {hasDistinctRaw && (
                            <span
                              className="text-[10px] text-slate-400 truncate max-w-[90px]"
                              title={menuItem.raw_text}
                            >
                              원문: {menuItem.raw_text}
                            </span>
                          )}
                        </li>
                      );
                    })}
                  </ul>
                ) : (
                  <div className="py-7 px-3 bg-slate-50 border border-dashed border-slate-200 rounded-lg text-center space-y-1">
                    <AlertCircle className="w-4 h-4 text-slate-400 mx-auto" />
                    <p className="text-xs font-semibold text-slate-600">공개된 식단 정보 없음</p>
                    <p className="text-[10px] text-slate-400">
                      원본 문서에 식단 내역이 기재되지 않았습니다.
                    </p>
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
