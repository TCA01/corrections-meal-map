import React, { useEffect, useState, useMemo, useCallback } from 'react';
import { Header } from './components/Header';
import { ProjectIntro } from './components/ProjectIntro';
import { StatsCard } from './components/StatsCard';
import { SearchBar } from './components/SearchBar';
import { KoreaMap } from './components/KoreaMap';
import { InstitutionDetail } from './components/InstitutionDetail';
import { LoadingState, ErrorState, EmptyInstitutionState } from './components/StateViews';
import { fetchInstitutions, fetchManifest, fetchMonthMenu, clearMonthMenuCache } from './data/api';
import { getAvailableMonths, getAvailableYears, hasMealDataForDate } from './data/adapter';
import { Institution, Manifest, MonthMenu } from './data/types';

export const App: React.FC = () => {
  // Global dataset state
  const [manifest, setManifest] = useState<Manifest | null>(null);
  const [institutions, setInstitutions] = useState<Institution[]>([]);
  const [isLoadingDataset, setIsLoadingDataset] = useState(true);
  const [datasetError, setDatasetError] = useState<string | null>(null);

  // User navigation state
  const [selectedInstitutionId, setSelectedInstitutionId] = useState<string | null>(null);
  const [selectedYear, setSelectedYear] = useState<number | null>(null);
  const [selectedMonth, setSelectedMonth] = useState<number | null>(null);
  const [selectedDate, setSelectedDate] = useState<string | null>(null);

  // Active month menu state
  const [monthMenu, setMonthMenu] = useState<MonthMenu | null>(null);
  const [isMonthMenuLoading, setIsMonthMenuLoading] = useState(false);
  const [monthMenuError, setMonthMenuError] = useState<string | null>(null);

  // Filter state: show only institutions with meal data
  const [onlyWithMeals, setOnlyWithMeals] = useState(false);

  // Set of institutions that have meal data in the manifest
  const availableInstitutionIds = useMemo(() => {
    if (!manifest) return new Set<string>();
    return new Set(manifest.institutions.map((i) => i.institution_id));
  }, [manifest]);

  // Find first institution from manifest that has available meal data for quick demo
  const sampleInstitutionInfo = useMemo(() => {
    if (!manifest || manifest.institutions.length === 0) return null;
    const firstManifestInst = manifest.institutions.find(
      (inst) => Object.keys(inst.available_years).length > 0
    );
    if (!firstManifestInst) return null;
    const meta = institutions.find((i) => i.institution_id === firstManifestInst.institution_id);
    return {
      institution_id: firstManifestInst.institution_id,
      name: meta?.name || firstManifestInst.institution_id,
    };
  }, [manifest, institutions]);

  // Load Initial Dataset (Manifest + Institutions)
  const loadDataset = useCallback(async () => {
    setIsLoadingDataset(true);
    setDatasetError(null);
    clearMonthMenuCache();
    try {
      const [manifestData, institutionsData] = await Promise.all([
        fetchManifest(),
        fetchInstitutions(),
      ]);
      setManifest(manifestData);
      setInstitutions(institutionsData);
    } catch (err: any) {
      console.error('Failed to load dataset:', err);
      setDatasetError(err?.message || '식단 데이터셋을 초기화하는 중 오류가 발생했습니다.');
    } finally {
      setIsLoadingDataset(false);
    }
  }, []);

  useEffect(() => {
    loadDataset();
  }, [loadDataset]);

  // Load Month Menu whenever institution, year, or month changes
  const loadCurrentMonthMenu = useCallback(
    async (instId: string, year: number, month: number) => {
      setIsMonthMenuLoading(true);
      setMonthMenuError(null);
      try {
        const menu = await fetchMonthMenu(instId, year, month);
        setMonthMenu(menu);

        // Pick first available date in that month that HAS data (do not auto-select empty today!)
        const dates = Object.keys(menu.days).sort();
        const firstAvailableDate = dates.find((d) => hasMealDataForDate(menu, d));
        setSelectedDate(firstAvailableDate || null);
      } catch (err: any) {
        console.error(`Failed to load menu for ${instId} ${year}-${month}:`, err);
        setMonthMenu(null);
        setSelectedDate(null);
        setMonthMenuError(err?.message || '해당 월의 식단표를 불러오지 못했습니다.');
      } finally {
        setIsMonthMenuLoading(false);
      }
    },
    []
  );

  // Institution Selection Handler
  const handleSelectInstitution = useCallback(
    (instId: string) => {
      setSelectedInstitutionId(instId);
      setSelectedDate(null);
      setMonthMenu(null);
      setMonthMenuError(null);

      // Determine initial year & month from manifest
      const years = getAvailableYears(manifest, instId);
      if (years.length > 0) {
        const initialYear = years[0];
        setSelectedYear(initialYear);

        const months = getAvailableMonths(manifest, instId, initialYear);
        if (months.length > 0) {
          const initialMonth = months[months.length - 1]; // Latest available month in year
          setSelectedMonth(initialMonth);
          loadCurrentMonthMenu(instId, initialYear, initialMonth);
        } else {
          setSelectedMonth(null);
        }
      } else {
        setSelectedYear(null);
        setSelectedMonth(null);
      }
    },
    [manifest, loadCurrentMonthMenu]
  );

  // Year Selection Handler
  const handleSelectYear = useCallback(
    (year: number) => {
      if (!selectedInstitutionId) return;
      setSelectedYear(year);
      setSelectedDate(null);

      const months = getAvailableMonths(manifest, selectedInstitutionId, year);
      if (months.length > 0) {
        const nextMonth = months.includes(selectedMonth || 0) ? selectedMonth! : months[0];
        setSelectedMonth(nextMonth);
        loadCurrentMonthMenu(selectedInstitutionId, year, nextMonth);
      } else {
        setSelectedMonth(null);
        setMonthMenu(null);
      }
    },
    [manifest, selectedInstitutionId, selectedMonth, loadCurrentMonthMenu]
  );

  // Month Selection Handler
  const handleSelectMonth = useCallback(
    (month: number) => {
      if (!selectedInstitutionId || !selectedYear) return;
      setSelectedMonth(month);
      setSelectedDate(null);
      loadCurrentMonthMenu(selectedInstitutionId, selectedYear, month);
    },
    [selectedInstitutionId, selectedYear, loadCurrentMonthMenu]
  );

  // Retry loading current month menu
  const handleRetryMonthMenu = () => {
    if (selectedInstitutionId && selectedYear && selectedMonth) {
      loadCurrentMonthMenu(selectedInstitutionId, selectedYear, selectedMonth);
    }
  };

  // Fast demonstration: select sample institution with real meal data
  const handleSelectSampleMeal = useCallback(() => {
    if (!sampleInstitutionInfo) return;
    handleSelectInstitution(sampleInstitutionInfo.institution_id);
  }, [sampleInstitutionInfo, handleSelectInstitution]);

  // Deselect Institution
  const handleCloseInstitution = () => {
    setSelectedInstitutionId(null);
    setSelectedYear(null);
    setSelectedMonth(null);
    setSelectedDate(null);
    setMonthMenu(null);
    setMonthMenuError(null);
  };

  const selectedInstitution = useMemo(() => {
    return institutions.find((i) => i.institution_id === selectedInstitutionId) || null;
  }, [institutions, selectedInstitutionId]);

  return (
    <div className="min-h-screen flex flex-col bg-slate-100 font-sans text-slate-900">
      {/* Top Header */}
      <Header
        datasetVersion={manifest?.dataset_version}
        webContractVersion={manifest?.web_contract_version}
        lastUpdated={manifest?.stats?.last_updated}
        dataScope={manifest?.stats?.data_scope}
        isMockFixture={manifest?.is_mock_fixture}
      />

      {/* Main Content Container */}
      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-5 space-y-5">
        {/* Intro / Contest Notice */}
        <ProjectIntro
          fixtureNotice={manifest?.fixture_notice}
          dataScope={manifest?.stats?.data_scope}
          onSelectSampleMeal={handleSelectSampleMeal}
          sampleInstitutionName={sampleInstitutionInfo?.name}
        />

        {/* Dataset Status Summary */}
        {manifest?.stats && (
          <StatsCard
            stats={manifest.stats}
            institutionsCount={institutions.length}
            institutionsWithCoordsCount={institutions.filter((i) => i.has_coordinates).length}
          />
        )}

        {/* Global Search Bar & Fast-Access Filter Controls */}
        <div className="space-y-3">
          <div className="flex flex-col sm:flex-row gap-3 items-center justify-between">
            <div className="w-full">
              <SearchBar
                institutions={institutions}
                selectedInstitutionId={selectedInstitutionId}
                onSelectInstitution={handleSelectInstitution}
                availableInstitutionIds={availableInstitutionIds}
                onlyWithMeals={onlyWithMeals}
              />
            </div>
            {selectedInstitution && (
              <div className="text-xs text-slate-600 shrink-0 self-end sm:self-center bg-white px-3 py-1.5 rounded-lg border border-slate-200 shadow-sm">
                선택 기관: <span className="font-bold text-blue-700">{selectedInstitution.name}</span>
              </div>
            )}
          </div>

          {/* Quick Action & Filter Bar */}
          <div className="flex flex-wrap items-center justify-between gap-2.5 bg-white px-3.5 py-2.5 rounded-xl border border-slate-200 shadow-sm text-xs">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-semibold text-slate-700">기관 필터:</span>
              <button
                type="button"
                onClick={() => setOnlyWithMeals(false)}
                className={`px-2.5 py-1 rounded-lg font-medium transition cursor-pointer ${
                  !onlyWithMeals
                    ? 'bg-slate-800 text-white shadow-sm'
                    : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                }`}
              >
                전체 기관 ({institutions.length}개소)
              </button>
              <button
                type="button"
                onClick={() => setOnlyWithMeals(true)}
                className={`px-2.5 py-1 rounded-lg font-medium transition cursor-pointer flex items-center gap-1.5 ${
                  onlyWithMeals
                    ? 'bg-blue-600 text-white shadow-sm'
                    : 'bg-emerald-50 text-emerald-800 border border-emerald-200 hover:bg-emerald-100'
                }`}
              >
                <span className="w-2 h-2 rounded-full bg-emerald-400"></span>
                <span>식단 조회 가능 기관만 보기 ({availableInstitutionIds.size}개소)</span>
              </button>
            </div>

            {sampleInstitutionInfo && (
              <button
                type="button"
                onClick={handleSelectSampleMeal}
                className="inline-flex items-center gap-1.5 px-3 py-1 bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700 text-white rounded-lg font-bold shadow-sm transition cursor-pointer"
                title={`예시 식단 바로 보기 (${sampleInstitutionInfo.name})`}
              >
                <span>⚡ 예시 식단 바로 보기</span>
                <span className="opacity-80 font-normal">({sampleInstitutionInfo.name})</span>
              </button>
            )}
          </div>
        </div>

        {/* Main Application Area: Loading / Error / Two-Column Layout */}
        {isLoadingDataset ? (
          <LoadingState message="전국 교정기관 기준정보 및 실제 수용자 식단 데이터셋을 불러오는 중입니다..." />
        ) : datasetError ? (
          <ErrorState message={datasetError} onRetry={loadDataset} />
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-5 items-start">
            {/* Left / Top (Map Column) */}
            <div className="lg:col-span-6 xl:col-span-7 space-y-3">
              <div className="flex items-center justify-between px-1">
                <span className="text-xs font-semibold text-slate-700">대한민국 교정기관 지도</span>
                <span className="text-[11px] text-slate-500">마커 클릭 시 기관 상세 조회</span>
              </div>
              <KoreaMap
                institutions={institutions}
                selectedInstitutionId={selectedInstitutionId}
                onSelectInstitution={handleSelectInstitution}
                availableInstitutionIds={availableInstitutionIds}
                onlyWithMeals={onlyWithMeals}
                onToggleOnlyWithMeals={setOnlyWithMeals}
              />
            </div>

            {/* Right / Bottom (Detail / Meal Panel Column) */}
            <div className="lg:col-span-6 xl:col-span-5 space-y-4">
              {selectedInstitution ? (
                <InstitutionDetail
                  institution={selectedInstitution}
                  manifest={manifest}
                  selectedYear={selectedYear}
                  onSelectYear={handleSelectYear}
                  selectedMonth={selectedMonth}
                  onSelectMonth={handleSelectMonth}
                  monthMenu={monthMenu}
                  isMonthMenuLoading={isMonthMenuLoading}
                  monthMenuError={monthMenuError}
                  onRetryMonthMenu={handleRetryMonthMenu}
                  selectedDate={selectedDate}
                  onSelectDate={setSelectedDate}
                  onClose={handleCloseInstitution}
                  onSelectSampleMeal={handleSelectSampleMeal}
                />
              ) : (
                <EmptyInstitutionState
                  onQuickSelect={handleSelectInstitution}
                  sampleInstitutionName={sampleInstitutionInfo?.name}
                  onSelectSampleMeal={handleSelectSampleMeal}
                  onlyWithMeals={onlyWithMeals}
                  onToggleOnlyWithMeals={setOnlyWithMeals}
                  availableCount={availableInstitutionIds.size}
                />
              )}
            </div>
          </div>
        )}
      </main>

      {/* Footer */}
      <footer className="bg-white border-t border-slate-200 mt-12 py-6 text-xs text-slate-500 text-center space-y-1">
        <p className="font-semibold text-slate-700">
          교정 식단 데이터맵 (Corrections Meal Data Map)
        </p>
        <p>
          본 서비스는 법무행정경진대회 출품작으로, 비정형 공공데이터 표준화 및 수용자 처우 정보의 디지털
          투명성을 위해 제작되었습니다.
        </p>
        {manifest?.dataset_version && (
          <p className="text-[11px] text-slate-400">
            데이터셋 식별자: {manifest.dataset_version}
          </p>
        )}
      </footer>
    </div>
  );
};
export default App;
