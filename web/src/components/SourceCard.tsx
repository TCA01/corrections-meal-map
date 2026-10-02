import React from 'react';
import { ExternalLink, Download, FileText, CheckCircle, Layers } from 'lucide-react';
import { DayMenu, MenuSource } from '../data/types';

interface SourceCardProps {
  sources?: MenuSource[];
  dayMenu?: DayMenu | null;
  institutionName: string;
  year: number;
  month: number;
}

export const SourceCard: React.FC<SourceCardProps> = ({
  sources = [],
  dayMenu,
  institutionName,
  year,
  month,
}) => {
  // Extract document IDs referenced by the current day's meal slots
  const dayDocIds = new Set<string>();
  const inlineSources: MenuSource[] = [];

  const slots = [dayMenu?.breakfast, dayMenu?.lunch, dayMenu?.dinner];
  slots.forEach((s) => {
    if (s?.source_document_ids) {
      s.source_document_ids.forEach((id) => dayDocIds.add(id));
    }
    if (s?.source) {
      inlineSources.push(s.source);
    }
  });

  // Filter sources that belong to this day if available; otherwise show all month sources
  let relevantSources: MenuSource[] = [];
  if (dayDocIds.size > 0 && sources.length > 0) {
    relevantSources = sources.filter((src) => src.document_id && dayDocIds.has(src.document_id));
  }
  if (relevantSources.length === 0 && inlineSources.length > 0) {
    relevantSources = inlineSources;
  }
  if (relevantSources.length === 0 && sources.length > 0) {
    relevantSources = sources;
  }

  // Deduplicate by document_id or original_filename
  const uniqueSourcesMap = new Map<string, MenuSource>();
  relevantSources.forEach((src) => {
    const key = src.document_id || src.original_filename || src.title || JSON.stringify(src);
    if (!uniqueSourcesMap.has(key)) {
      uniqueSourcesMap.set(key, src);
    }
  });
  const displaySources = Array.from(uniqueSourcesMap.values());
  const isMultipleSources = displaySources.length > 1 || dayDocIds.size > 1;

  return (
    <div className="bg-slate-50 border border-slate-200 rounded-xl p-4 text-xs text-slate-600 space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 font-bold text-slate-800">
          <FileText className="w-4 h-4 text-blue-600" />
          <span>식단표 공공데이터 원본 출처</span>
        </div>
        {isMultipleSources && (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-blue-100 text-blue-800 font-semibold text-[11px]">
            <Layers className="w-3 h-3" />
            <span>복수 원본 자료 ({displaySources.length}건)</span>
          </span>
        )}
      </div>

      {displaySources.length > 0 ? (
        <div className="space-y-2.5">
          {displaySources.map((src, idx) => {
            const filename = src.original_filename || src.title || '수용자 식단표 원본';
            const pubDate = src.published_date || src.published_at;
            const postUrl = src.post_url || src.url;
            const downloadUrl = src.download_url;

            return (
              <div
                key={src.document_id || idx}
                className="bg-white p-3.5 rounded-xl border border-slate-200 shadow-xs flex flex-col sm:flex-row sm:items-center justify-between gap-3"
              >
                <div className="space-y-1 min-w-0">
                  <div className="font-bold text-slate-900 text-sm flex items-center gap-1.5 truncate">
                    <CheckCircle className="w-4 h-4 text-emerald-600 shrink-0" />
                    <span className="truncate" title={filename}>
                      {filename}
                    </span>
                  </div>

                  <div className="flex flex-wrap items-center gap-x-3 gap-y-0.5 text-[11px] text-slate-500">
                    {pubDate && <span>공개일: <strong className="text-slate-700">{pubDate}</strong></span>}
                    {src.document_id && (
                      <span className="text-slate-400">문서 ID: {src.document_id}</span>
                    )}
                  </div>
                </div>

                <div className="flex flex-wrap items-center gap-2 shrink-0">
                  {postUrl && (
                    <a
                      href={postUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg bg-blue-600 text-white hover:bg-blue-700 font-semibold text-xs shadow-xs transition"
                    >
                      <span>원본 게시글 보기</span>
                      <ExternalLink className="w-3.5 h-3.5" />
                    </a>
                  )}

                  {downloadUrl && (
                    <a
                      href={downloadUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg bg-slate-100 text-slate-800 hover:bg-slate-200 font-medium text-xs border border-slate-300 transition"
                    >
                      <Download className="w-3.5 h-3.5 text-slate-600" />
                      <span>첨부파일 보기</span>
                    </a>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        <div className="bg-white p-3 rounded-lg border border-slate-200 flex items-center justify-between">
          <span className="font-medium text-slate-700">
            {institutionName} {year}년 {month}월 수용자 식단표
          </span>
          <span className="text-slate-400 text-[11px]">법무부 교정본부 정보공개</span>
        </div>
      )}

      <p className="text-[11px] text-slate-400 leading-normal">
        ※ 본 식단 데이터는 법무부 교정본부 및 각 교정기관 공식 홈페이지에 공개된 수용자 식단표 원본
        문서에서 자동 추출·검증된 정규화 데이터입니다.
      </p>
    </div>
  );
};
