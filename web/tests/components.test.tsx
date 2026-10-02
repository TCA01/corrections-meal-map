import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ProjectIntro } from '../src/components/ProjectIntro';
import { StatsCard } from '../src/components/StatsCard';
import { YearMonthSelector } from '../src/components/YearMonthSelector';
import { CalendarView } from '../src/components/CalendarView';
import { MealView } from '../src/components/MealView';
import { SourceCard } from '../src/components/SourceCard';
import { SearchBar } from '../src/components/SearchBar';
import { KoreaMap } from '../src/components/KoreaMap';
import { LoadingState, ErrorState, EmptyInstitutionState } from '../src/components/StateViews';
import { DayMenu, Institution, MonthMenu } from '../src/data/types';

describe('ProjectIntro Component', () => {
  it('renders the contest project statement and navigation flow', () => {
    render(<ProjectIntro fixtureNotice="개발용 Mock 데이터" />);
    expect(screen.getByText(/법무행정 디지털 혁신 과제/i)).toBeInTheDocument();
    expect(
      screen.getByText(/XLSX · XLS · PDF · HWP · HWPX/i)
    ).toBeInTheDocument();
    expect(screen.getByText(/개발용 Mock 데이터/i)).toBeInTheDocument();
  });
});

describe('StatsCard Component', () => {
  it('renders stats when provided in manifest', () => {
    const stats = {
      total_institutions: 55,
      collected_institutions: 3,
      structured_documents: 19,
      total_meal_records: 1767,
      last_updated: '2026-09-30',
    };
    render(<StatsCard stats={stats} />);
    expect(screen.getByText('55개소')).toBeInTheDocument();
    expect(screen.getByText('3개소')).toBeInTheDocument();
    expect(screen.getByText('19건')).toBeInTheDocument();
    expect(screen.getByText(/2026\.09\.30/)).toBeInTheDocument();
  });

  it('renders nothing when stats are undefined to avoid fake data', () => {
    const { container } = render(<StatsCard stats={undefined} />);
    expect(container).toBeEmptyDOMElement();
  });
});

describe('YearMonthSelector Component', () => {
  it('only enables months that exist in availableMonths', () => {
    const onSelectMonth = vi.fn();
    render(
      <YearMonthSelector
        availableYears={[2026]}
        selectedYear={2026}
        onSelectYear={vi.fn()}
        availableMonths={[9, 10]}
        selectedMonth={9}
        onSelectMonth={onSelectMonth}
      />
    );

    // 9월 and 10월 should be enabled
    const btn9 = screen.getByRole('button', { name: '9월' });
    const btn10 = screen.getByRole('button', { name: '10월' });
    expect(btn9).not.toBeDisabled();
    expect(btn10).not.toBeDisabled();

    // 1월 and 8월 should be disabled
    const btn1 = screen.getByRole('button', { name: '1월' });
    const btn8 = screen.getByRole('button', { name: '8월' });
    expect(btn1).toBeDisabled();
    expect(btn8).toBeDisabled();

    // Clicking 10월 calls onSelectMonth
    fireEvent.click(btn10);
    expect(onSelectMonth).toHaveBeenCalledWith(10);
  });
});

describe('CalendarView Component', () => {
  const mockMenu: MonthMenu = {
    schema_version: '1.0',
    institution_id: 'KR_CORR_MOKPO_PRISON',
    year: 2026,
    month: 9,
    days: {
      '2026-09-01': {
        breakfast: { menu_items: [{ name: '쌀밥' }] },
      },
      '2026-09-15': {
        lunch: { menu_items: [{ name: '비빔밥' }] },
      },
    },
    sources: [],
  };

  it('only allows selecting dates with meal data, disables dates without data', () => {
    const onSelectDate = vi.fn();
    render(
      <CalendarView
        year={2026}
        month={9}
        monthMenu={mockMenu}
        selectedDate="2026-09-01"
        onSelectDate={onSelectDate}
      />
    );

    // Day 1 has data -> enabled
    const day1Btn = screen.getByTitle('2026-09-01 식단 조회');
    expect(day1Btn).not.toBeDisabled();
    expect(day1Btn).toHaveAttribute('aria-selected', 'true');

    // Day 2 has no data -> disabled
    const day2Btn = screen.getByTitle('2026-09-02 식단 정보 없음');
    expect(day2Btn).toBeDisabled();

    // Day 15 has data -> enabled and clickable
    const day15Btn = screen.getByTitle('2026-09-15 식단 조회');
    expect(day15Btn).not.toBeDisabled();
    fireEvent.click(day15Btn);
    expect(onSelectDate).toHaveBeenCalledWith('2026-09-15');
  });
});

describe('MealView Component', () => {
  it('displays breakfast, lunch, and dinner cards with "공개된 식단 정보 없음" for empty meals', () => {
    const dayMenu: DayMenu = {
      breakfast: { menu_items: [{ name: '쌀밥' }, { name: '된장국' }] },
      lunch: { menu_items: [{ name: '제육볶음' }] },
      dinner: { menu_items: [] },
    };

    render(<MealView dateStr="2026-09-30" dayMenu={dayMenu} />);

    // Check title
    expect(screen.getByText(/2026년 9월 30일/)).toBeInTheDocument();

    // Breakfast
    expect(screen.getByText('쌀밥')).toBeInTheDocument();
    expect(screen.getByText('된장국')).toBeInTheDocument();

    // Lunch
    expect(screen.getByText('제육볶음')).toBeInTheDocument();

    // Dinner empty state
    expect(screen.getByText('공개된 식단 정보 없음')).toBeInTheDocument();
    expect(
      screen.getByText('원본 문서에 식단 내역이 기재되지 않았습니다.')
    ).toBeInTheDocument();
  });
});

describe('SourceCard Component', () => {
  it('renders source title and external URL link without exposing local paths', () => {
    const sources = [
      {
        source_id: 'src-1',
        title: '목포교도소 2026년 9월 식단표',
        url: 'https://corrections.go.kr/notice/100',
        published_at: '2026-08-28',
      },
    ];

    render(
      <SourceCard
        sources={sources}
        institutionName="목포교도소"
        year={2026}
        month={9}
      />
    );

    expect(screen.getByText('목포교도소 2026년 9월 식단표')).toBeInTheDocument();
    expect(screen.getByText(/공개일/)).toBeInTheDocument();
    const link = screen.getByRole('link', { name: /원본 게시글 보기|원본 자료 보기/i });
    expect(link).toHaveAttribute('href', 'https://corrections.go.kr/notice/100');
    expect(link).toHaveAttribute('target', '_blank');
  });
});

describe('SearchBar Component', () => {
  const mockInstitutions: Institution[] = [
    {
      institution_id: 'KR_CORR_SEOUL_DETENTION',
      name: '서울구치소',
      short_name: '서울구',
      type: 'detention_center',
      type_korean: '구치소',
      address: '경기도 의왕시',
      latitude: null,
      longitude: null,
      has_coordinates: false,
    },
    {
      institution_id: 'KR_CORR_MOKPO_PRISON',
      name: '목포교도소',
      short_name: '목포교',
      type: 'prison',
      type_korean: '교도소',
      address: '전남 목포시',
      latitude: 34.8028,
      longitude: 126.3986,
      has_coordinates: true,
    },
  ];

  it('filters institutions and allows selecting institutions even without coordinates', () => {
    const onSelect = vi.fn();
    render(
      <SearchBar
        institutions={mockInstitutions}
        selectedInstitutionId={null}
        onSelectInstitution={onSelect}
      />
    );

    const input = screen.getByPlaceholderText(/교정기관 검색/i);
    fireEvent.change(input, { target: { value: '서울' } });

    // Seoul detention should appear in dropdown
    const seoulOption = screen.getByText('서울구치소');
    expect(seoulOption).toBeInTheDocument();
    expect(screen.getByText('위치 확인 중')).toBeInTheDocument();

    fireEvent.click(seoulOption);
    expect(onSelect).toHaveBeenCalledWith('KR_CORR_SEOUL_DETENTION');
  });
});

describe('KoreaMap Component', () => {
  const mockInstitutions: Institution[] = [
    {
      institution_id: 'KR_CORR_SEOUL_DETENTION',
      name: '서울구치소',
      short_name: '서울구',
      type: 'detention_center',
      type_korean: '구치소',
      address: '경기도 의왕시',
      latitude: null,
      longitude: null,
      has_coordinates: false,
    },
    {
      institution_id: 'KR_CORR_MOKPO_PRISON',
      name: '목포교도소',
      short_name: '목포교',
      type: 'prison',
      type_korean: '교도소',
      address: '전남 목포시',
      latitude: 34.8028,
      longitude: 126.3986,
      has_coordinates: true,
    },
  ];

  it('renders without crashing and shows notice when selected institution has no coordinates', () => {
    render(
      <KoreaMap
        institutions={mockInstitutions}
        selectedInstitutionId="KR_CORR_SEOUL_DETENTION"
        onSelectInstitution={vi.fn()}
      />
    );

    // Shows notice that selected institution has no coordinates
    expect(
      screen.getByText(/위치 좌표 확인 중 \(지도 미표시\) — \[서울구치소\]/i)
    ).toBeInTheDocument();
    expect(screen.getByText(/지도 위치:/i)).toBeInTheDocument();
    expect(screen.getByText(/전체 2개소/i)).toBeInTheDocument();
  });
});

describe('StateViews', () => {
  it('renders LoadingState', () => {
    render(<LoadingState message="테스트 로딩 메시지" />);
    expect(screen.getByText('데이터 로딩 중')).toBeInTheDocument();
    expect(screen.getByText('테스트 로딩 메시지')).toBeInTheDocument();
  });

  it('renders ErrorState with retry button', () => {
    const onRetry = vi.fn();
    render(<ErrorState message="네트워크 오류 발생" onRetry={onRetry} />);
    expect(screen.getByText('네트워크 오류 발생')).toBeInTheDocument();
    const retryBtn = screen.getByRole('button', { name: '데이터 다시 불러오기' });
    fireEvent.click(retryBtn);
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it('renders EmptyInstitutionState and responds to quick demo and filter buttons', () => {
    const onSelectSample = vi.fn();
    const onToggleOnlyMeals = vi.fn();

    render(
      <EmptyInstitutionState
        sampleInstitutionName="목포교도소"
        onSelectSampleMeal={onSelectSample}
        onlyWithMeals={false}
        onToggleOnlyWithMeals={onToggleOnlyMeals}
        availableCount={30}
      />
    );

    expect(screen.getByText('지도에서 교정기관을 선택하세요')).toBeInTheDocument();
    const demoBtn = screen.getByRole('button', { name: /예시 식단 바로 보기/i });
    expect(demoBtn).toBeInTheDocument();
    fireEvent.click(demoBtn);
    expect(onSelectSample).toHaveBeenCalledTimes(1);

    const filterBtn = screen.getByRole('button', { name: /식단 있는 기관만 보기/i });
    expect(filterBtn).toBeInTheDocument();
    fireEvent.click(filterBtn);
    expect(onToggleOnlyMeals).toHaveBeenCalledWith(true);
  });
});
