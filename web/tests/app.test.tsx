import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { App } from '../src/App';
import * as api from '../src/data/api';
import { Manifest, Institution, MonthMenu } from '../src/data/types';

describe('App Component Integration Flow', () => {
  const mockManifest: Manifest = {
    schema_version: '1.0',
    dataset_version: '2026.09-test',
    is_mock_fixture: true,
    fixture_notice: '테스트용 Mock 데이터',
    stats: {
      total_institutions: 55,
      collected_institutions: 2,
      structured_documents: 4,
      total_meal_records: 120,
      last_updated: '2026-09-30',
    },
    institutions: [
      {
        institution_id: 'KR_CORR_MOKPO_PRISON',
        available_years: {
          '2026': [9],
        },
      },
      {
        institution_id: 'KR_CORR_SEOUL_DETENTION',
        available_years: {
          '2026': [8],
        },
      },
    ],
  };

  const mockInstitutions: Institution[] = [
    {
      institution_id: 'KR_CORR_MOKPO_PRISON',
      name: '목포교도소',
      short_name: '목포교',
      type: 'prison',
      type_korean: '교도소',
      address: '전라남도 목포시',
      latitude: 34.8028,
      longitude: 126.3986,
      has_coordinates: true,
    },
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
      institution_id: 'KR_CORR_ANYANG_PRISON',
      name: '안양교도소',
      short_name: '안양교',
      type: 'prison',
      type_korean: '교도소',
      address: '경기도 안양시',
      latitude: null,
      longitude: null,
      has_coordinates: false,
    },
  ];

  const mockMokpoMenu: MonthMenu = {
    schema_version: '1.0',
    institution_id: 'KR_CORR_MOKPO_PRISON',
    year: 2026,
    month: 9,
    days: {
      '2026-09-01': {
        breakfast: {
          menu_items: [{ name: '쌀밥' }, { name: '콩나물국' }],
          source_document_id: 'doc-1',
          source_document_ids: ['doc-1'],
        },
        lunch: {
          menu_items: [{ name: '비빔밥' }],
          source_document_id: 'doc-1',
          source_document_ids: ['doc-1'],
        },
        dinner: null, // empty dinner slot
      },
    },
    sources: [
      {
        original_filename: '목포교도소 2026년 9월 식단표',
        post_url: 'https://corrections.go.kr/notice/1',
        published_date: '2026-08-28',
      },
    ],
  };

  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('renders initial load, shows stats and empty state prompt', async () => {
    vi.spyOn(api, 'fetchManifest').mockResolvedValue(mockManifest);
    vi.spyOn(api, 'fetchInstitutions').mockResolvedValue(mockInstitutions);

    render(<App />);

    // Initially loading state is rendered
    expect(screen.getByText(/데이터 로딩 중/i)).toBeInTheDocument();

    // After loading completes
    await waitFor(() => {
      expect(screen.getByText('교정 식단 데이터맵')).toBeInTheDocument();
      expect(screen.getByText('55개소')).toBeInTheDocument();
      expect(screen.getByText('지도에서 교정기관을 선택하세요')).toBeInTheDocument();
    });
  });

  it('handles dataset load error and allows retry', async () => {
    vi.spyOn(api, 'fetchManifest').mockRejectedValue(new Error('네트워크 타임아웃'));
    vi.spyOn(api, 'fetchInstitutions').mockResolvedValue(mockInstitutions);

    render(<App />);

    await waitFor(() => {
      expect(screen.getByText('네트워크 타임아웃')).toBeInTheDocument();
    });

    // Test retry
    vi.spyOn(api, 'fetchManifest').mockResolvedValue(mockManifest);
    fireEvent.click(screen.getByRole('button', { name: '데이터 다시 불러오기' }));

    await waitFor(() => {
      expect(screen.getByText('지도에서 교정기관을 선택하세요')).toBeInTheDocument();
    });
  });

  it('completes the full flow: search -> institution -> year/month -> calendar -> meals -> source', async () => {
    vi.spyOn(api, 'fetchManifest').mockResolvedValue(mockManifest);
    vi.spyOn(api, 'fetchInstitutions').mockResolvedValue(mockInstitutions);
    vi.spyOn(api, 'fetchMonthMenu').mockResolvedValue(mockMokpoMenu);

    render(<App />);

    await waitFor(() => {
      expect(screen.getByText('지도에서 교정기관을 선택하세요')).toBeInTheDocument();
    });

    // 1. Search for Mokpo
    const searchInput = screen.getByPlaceholderText(/교정기관 검색/i);
    fireEvent.change(searchInput, { target: { value: '목포' } });

    // 2. Click Mokpo option
    const mokpoOption = screen.getByText('목포교도소');
    fireEvent.click(mokpoOption);

    // 3. Institution Detail should be displayed with 2026 and 9월 active
    await waitFor(() => {
      expect(screen.getByRole('heading', { level: 2, name: /목포교도소/i })).toBeInTheDocument();
      expect(screen.getByTitle('2026-09-01 식단 조회')).toBeInTheDocument();
    });

    // 4. Check meal display: Breakfast & Lunch items, and empty dinner message
    await waitFor(() => {
      expect(screen.getByText('쌀밥')).toBeInTheDocument();
      expect(screen.getByText('콩나물국')).toBeInTheDocument();
      expect(screen.getByText('비빔밥')).toBeInTheDocument();
      expect(screen.getByText('공개된 식단 정보 없음')).toBeInTheDocument();
    });

    // 5. Check Source card
    expect(screen.getByText('식단표 공공데이터 원본 출처')).toBeInTheDocument();
    expect(screen.getByText('목포교도소 2026년 9월 식단표')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /원본 게시글 보기|원본 자료 보기/i })).toHaveAttribute(
      'href',
      'https://corrections.go.kr/notice/1'
    );
  });

  it('handles selecting institution with no coordinates safely', async () => {
    vi.spyOn(api, 'fetchManifest').mockResolvedValue(mockManifest);
    vi.spyOn(api, 'fetchInstitutions').mockResolvedValue(mockInstitutions);
    vi.spyOn(api, 'fetchMonthMenu').mockResolvedValue({
      schema_version: '1.0',
      institution_id: 'KR_CORR_SEOUL_DETENTION',
      year: 2026,
      month: 8,
      days: {},
      sources: [],
    });

    render(<App />);

    await waitFor(() => {
      expect(screen.getByText('지도에서 교정기관을 선택하세요')).toBeInTheDocument();
    });

    const searchInput = screen.getByPlaceholderText(/교정기관 검색/i);
    fireEvent.change(searchInput, { target: { value: '서울' } });

    const seoulOption = screen.getByText('서울구치소');
    fireEvent.click(seoulOption);

    await waitFor(() => {
      expect(screen.getByRole('heading', { level: 2, name: /서울구치소/i })).toBeInTheDocument();
      // Should show notice that coordinates are missing without crashing
      expect(screen.getByText(/위치 좌표 확인 중 \(식단 조회 가능\)/i)).toBeInTheDocument();
    });
  });

  it('handles institution without meal data in manifest', async () => {
    vi.spyOn(api, 'fetchManifest').mockResolvedValue(mockManifest);
    vi.spyOn(api, 'fetchInstitutions').mockResolvedValue(mockInstitutions);

    render(<App />);

    await waitFor(() => {
      expect(screen.getByText('지도에서 교정기관을 선택하세요')).toBeInTheDocument();
    });

    const searchInput = screen.getByPlaceholderText(/교정기관 검색/i);
    fireEvent.change(searchInput, { target: { value: '안양' } });

    const anyangOption = screen.getByText('안양교도소');
    fireEvent.click(anyangOption);

    await waitFor(() => {
      expect(screen.getByRole('heading', { level: 2, name: /안양교도소/i })).toBeInTheDocument();
      expect(screen.getByText(/현재 구조화된 식단 데이터가 없습니다|식단 데이터 수집 대기 중/i)).toBeInTheDocument();
    });
  });

  it('triggers quick demonstration via sample meal button directly into full meal view', async () => {
    vi.spyOn(api, 'fetchManifest').mockResolvedValue(mockManifest);
    vi.spyOn(api, 'fetchInstitutions').mockResolvedValue(mockInstitutions);
    vi.spyOn(api, 'fetchMonthMenu').mockResolvedValue(mockMokpoMenu);

    render(<App />);

    await waitFor(() => {
      expect(screen.getByText('지도에서 교정기관을 선택하세요')).toBeInTheDocument();
    });

    // Find and click the sample meal demo button
    const demoButtons = screen.getAllByRole('button', { name: /예시 식단 바로 보기/i });
    expect(demoButtons.length).toBeGreaterThan(0);
    fireEvent.click(demoButtons[0]);

    // Should load Mokpo institution and render meal view immediately
    await waitFor(() => {
      expect(screen.getByRole('heading', { level: 2, name: /목포교도소/i })).toBeInTheDocument();
      expect(screen.getByText('쌀밥')).toBeInTheDocument();
      expect(screen.getByText('비빔밥')).toBeInTheDocument();
    });
  });
});
