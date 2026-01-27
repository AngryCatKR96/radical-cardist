"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import styles from "./page.module.css";

type CardMeta = {
  id?: number;
  corpCode?: string;
  name?: string;
  issuer?: string;
  type?: string;
};

type CardConditions = {
  prev_month_min?: number;
};

type CardFees = {
  annual_basic?: string;
  annual_detail?: string;
};

type CardHints = {
  top_tags?: string[];
  top_titles?: string[];
  search_titles?: string[];
  search_options?: string[];
  brands?: string[];
};

type BenefitHtmlItem = {
  category: string;
  html: string;
};

type CardEmbeddingMetadata = {
  category_std?: string;
  benefit_type?: string;
  payment_methods?: string;
  exclusions_present?: boolean;
  annual_fee_total?: number | null;
  requires_spend?: boolean;
  text_len?: number;
  chunk_part?: number;
  chunk_parts?: number;
  benefit_category?: string;
  doc_type?: string;
  card_id?: number;
  name?: string;
  issuer?: string;
  [key: string]: unknown;
};

type VectorStoreStats = {
  database?: string;
  collection?: string;
  total_documents?: number;
  documents_with_embeddings?: number;
  doc_type_counts?: Record<string, number>;
  error?: string;
  detail?: string;
};

type CardListItem = {
  card_id: number;
  meta?: CardMeta;
  conditions?: CardConditions;
  fees?: CardFees;
  hints?: CardHints;
  is_discon?: boolean;
  updated_at?: string;
  embeddings_count?: number;
};

type CardListResponse = {
  total: number;
  skip: number;
  limit: number;
  items: CardListItem[];
  detail?: string;
};

type CardEmbedding = {
  doc_id?: string;
  doc_type?: string;
  text?: string;
  metadata?: CardEmbeddingMetadata;
  score?: number;
  distance?: number;
};

type CardDetail = {
  card_id: number;
  meta?: CardMeta;
  conditions?: CardConditions;
  fees?: CardFees;
  hints?: CardHints;
  is_discon?: boolean;
  benefits_html?: BenefitHtmlItem[];
  created_at?: string;
  updated_at?: string;
  embeddings?: CardEmbedding[];
  embeddings_count?: number;
  detail?: string;
};

type VectorQueryChunkMetadata = CardEmbeddingMetadata;

type VectorQueryResponse = {
  query_text: string;
  filters: Record<string, unknown>;
  top_k: number;
  doc_types?: string[] | null;
  doc_type_weights?: Record<string, number>;
  results: Array<{
    id?: string;
    text?: string;
    metadata?: VectorQueryChunkMetadata;
    distance?: number;
    score?: number;
    debug?: {
      raw_score?: number;
      doc_type_weight?: number;
      adjusted_score?: number;
      keyword_overlap?: number;
      keywords?: string[];
    };
  }>;
  detail?: string;
};

type VectorCardHit = {
  card_id: number;
  name?: string;
  issuer?: string;
  type?: string;
  // ranking score (raw × weight)
  adjusted_score?: number;
  raw_score?: number;
  doc_type_weight?: number;
  best_doc_type?: string;
  snippet?: string;
};

const formatNumber = (n: number | undefined) =>
  typeof n === "number" ? new Intl.NumberFormat("ko-KR").format(n) : "-";

const formatDate = (raw?: string) => {
  if (!raw) return "-";
  const d = new Date(raw);
  if (Number.isNaN(d.getTime())) return raw;
  return d.toLocaleString("ko-KR");
};

const getStringField = (
  obj: Record<string, unknown> | undefined,
  key: string
): string | undefined => {
  if (!obj) return undefined;
  const value = obj[key];
  return typeof value === "string" ? value : undefined;
};

const cardTypeLabel = (raw?: string) => {
  if (!raw) return "-";
  if (raw === "C") return "신용카드(C)";
  if (raw === "D") return "체크카드(D)";
  if (raw === "P") return "선불카드(P)";
  return raw;
};

function UiIcon({
  name,
  className,
}: {
  name:
    | "menu"
    | "grid"
    | "file"
    | "search"
    | "settings"
    | "moon"
    | "refresh"
    | "doc"
    | "cpu"
    | "shapes";
  className?: string;
}) {
  const common = { className, viewBox: "0 0 24 24", fill: "none" as const };
  switch (name) {
    case "menu":
      return (
        <svg {...common} stroke="currentColor" strokeWidth="2">
          <path d="M4 7h16M4 12h16M4 17h16" strokeLinecap="round" />
        </svg>
      );
    case "grid":
      return (
        <svg {...common} stroke="currentColor" strokeWidth="2">
          <path
            d="M4 4h7v7H4V4Zm9 0h7v7h-7V4ZM4 13h7v7H4v-7Zm9 0h7v7h-7v-7Z"
            strokeLinejoin="round"
          />
        </svg>
      );
    case "file":
      return (
        <svg {...common} stroke="currentColor" strokeWidth="2">
          <path
            d="M7 3h7l3 3v15a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1Z"
            strokeLinejoin="round"
          />
          <path d="M14 3v4h4" />
        </svg>
      );
    case "search":
      return (
        <svg {...common} stroke="currentColor" strokeWidth="2">
          <path
            d="M10.5 18a7.5 7.5 0 1 1 0-15 7.5 7.5 0 0 1 0 15Z"
            strokeLinejoin="round"
          />
          <path d="M16.5 16.5 21 21" strokeLinecap="round" />
        </svg>
      );
    case "settings":
      return (
        <svg {...common} stroke="currentColor" strokeWidth="2">
          <path
            d="M12 15.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7Z"
            strokeLinejoin="round"
          />
          <path
            d="M19.4 15a7.9 7.9 0 0 0 .1-1l2-1.2-2-3.4-2.3.5a7.2 7.2 0 0 0-1.7-1L15 6H9l-.5 2a7.2 7.2 0 0 0-1.7 1L4.5 8.4 2.5 11.8 4.5 13a7.9 7.9 0 0 0 .1 1L2.5 15.2l2 3.4 2.3-.5a7.2 7.2 0 0 0 1.7 1L9 22h6l.5-2a7.2 7.2 0 0 0 1.7-1l2.3.5 2-3.4-2.1-1.1Z"
            strokeLinejoin="round"
          />
        </svg>
      );
    case "moon":
      return (
        <svg {...common} stroke="currentColor" strokeWidth="2">
          <path
            d="M21 13.2A7.5 7.5 0 0 1 10.8 3a6.5 6.5 0 1 0 10.2 10.2Z"
            strokeLinejoin="round"
          />
        </svg>
      );
    case "refresh":
      return (
        <svg {...common} stroke="currentColor" strokeWidth="2">
          <path
            d="M21 12a9 9 0 0 1-15.4 6.4"
            strokeLinecap="round"
          />
          <path d="M3 12a9 9 0 0 1 15.4-6.4" strokeLinecap="round" />
          <path d="M3 3v6h6" strokeLinecap="round" />
          <path d="M21 21v-6h-6" strokeLinecap="round" />
        </svg>
      );
    case "doc":
      return (
        <svg {...common} stroke="currentColor" strokeWidth="2">
          <path
            d="M7 3h10a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2Z"
            strokeLinejoin="round"
          />
          <path d="M8 8h8M8 12h8M8 16h6" strokeLinecap="round" />
        </svg>
      );
    case "cpu":
      return (
        <svg {...common} stroke="currentColor" strokeWidth="2">
          <path d="M9 9h6v6H9V9Z" strokeLinejoin="round" />
          <path
            d="M9 2v3M15 2v3M9 19v3M15 19v3M2 9h3M2 15h3M19 9h3M19 15h3"
            strokeLinecap="round"
          />
          <path d="M6 6h12v12H6V6Z" strokeLinejoin="round" />
        </svg>
      );
    case "shapes":
      return (
        <svg {...common} stroke="currentColor" strokeWidth="2">
          <path
            d="M8 11a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z"
            strokeLinejoin="round"
          />
          <path
            d="M16 21a4 4 0 1 0 0-8 4 4 0 0 0 0 8Z"
            strokeLinejoin="round"
          />
          <path d="M14 3h7v7h-7V3Z" strokeLinejoin="round" />
        </svg>
      );
    default:
      return null;
  }
}

export default function VectorStoreAdminPage() {
  const [stats, setStats] = useState<VectorStoreStats | null>(null);
  const [statsError, setStatsError] = useState<string | null>(null);

  const [q, setQ] = useState("");
  const [searchMode, setSearchMode] = useState<"keyword" | "vector">("keyword");
  const [withEmbeddingsOnly, setWithEmbeddingsOnly] = useState(true);
  const [skip, setSkip] = useState(0);
  const [limit] = useState(20);
  const [list, setList] = useState<CardListResponse | null>(null);
  const [listError, setListError] = useState<string | null>(null);
  const [isLoadingList, setIsLoadingList] = useState(false);

  const [selectedCardId, setSelectedCardId] = useState<number | null>(null);
  const [detail, setDetail] = useState<CardDetail | null>(null);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [isLoadingDetail, setIsLoadingDetail] = useState(false);

  const [vectorHits, setVectorHits] = useState<VectorCardHit[] | null>(null);
  const [vectorError, setVectorError] = useState<string | null>(null);
  const [isVectorLoading, setIsVectorLoading] = useState(false);
  const [docTypeToggles, setDocTypeToggles] = useState({
    summary: true,
    benefit: true,
    notes: true,
  });
  const [docTypeWeights, setDocTypeWeights] = useState({
    summary: 1.15,
    benefit: 1.0,
    notes: 0.85,
  });

  const docTypeBars = useMemo(() => {
    const counts = stats?.doc_type_counts ?? {};
    const entries = Object.entries(counts).sort((a, b) => b[1] - a[1]);
    const max = entries[0]?.[1] ?? 0;
    return entries.slice(0, 8).map(([k, v]) => ({
      key: k,
      value: v,
      pct: max > 0 ? Math.round((v / max) * 100) : 0,
    }));
  }, [stats?.doc_type_counts]);

  const barFillClass = useCallback(
    (key: string) => {
      if (key === "benefit") return styles.barFillBenefit;
      if (key === "summary") return styles.barFillSummary;
      if (key === "notes") return styles.barFillNotes;
      return styles.barFillSummary;
    },
    []
  );

  const docTypePillClass = useCallback(
    (docType?: string) => {
      if (docType === "summary") return `${styles.docTypePill} ${styles.docTypeSummary}`;
      if (docType === "benefit") return `${styles.docTypePill} ${styles.docTypeBenefit}`;
      if (docType === "notes") return `${styles.docTypePill} ${styles.docTypeNotes}`;
      return `${styles.docTypePill} ${styles.docTypeNotes}`;
    },
    []
  );

  // 통계 로딩(fetch): 검색/목록 로딩과 UI를 섞지 않기 위해 기본은 "silent"
  const fetchStats = useCallback(async () => {
    setStatsError(null);
    try {
      const res = await fetch("/api/admin/vector-store/stats", {
        cache: "no-store",
      });
      const payload = (await res.json()) as VectorStoreStats | null;
      if (!res.ok) {
        const msg =
          (payload && (payload.detail || payload.error)) ||
          "통계 조회에 실패했습니다.";
        throw new Error(msg);
      }
      setStats(payload ?? {});
    } catch (e) {
      setStats(null);
      setStatsError(e instanceof Error ? e.message : "통계 조회 실패");
    }
  }, []);


  const fetchList = useCallback(
    async (nextSkip: number) => {
      setIsLoadingList(true);
      setListError(null);
      try {
        const params = new URLSearchParams();
        params.set("skip", String(nextSkip));
        params.set("limit", String(limit));
        params.set("with_embeddings_only", String(withEmbeddingsOnly));
        if (q.trim()) params.set("q", q.trim());

        const res = await fetch(`/api/admin/vector-store/cards?${params}`, {
          cache: "no-store",
        });
        const payload = (await res.json()) as CardListResponse | null;
        if (!res.ok) {
          const msg = payload?.detail || "목록 조회에 실패했습니다.";
          throw new Error(msg);
        }
        setList(payload);
        setSkip(nextSkip);
        setVectorHits(null);
        setVectorError(null);
      } catch (e) {
        setList(null);
        setListError(e instanceof Error ? e.message : "목록 조회 실패");
      } finally {
        setIsLoadingList(false);
      }
    },
    [limit, q, withEmbeddingsOnly]
  );

  const fetchDetail = useCallback(async (cardId: number) => {
    setIsLoadingDetail(true);
    setDetailError(null);
    try {
      const res = await fetch(`/api/admin/vector-store/cards/${cardId}`, {
        cache: "no-store",
      });
      const payload = (await res.json()) as CardDetail | null;
      if (!res.ok) {
        const msg = payload?.detail || "상세 조회에 실패했습니다.";
        throw new Error(msg);
      }
      setDetail(payload);
      setSelectedCardId(cardId);
    } catch (e) {
      setDetail(null);
      setDetailError(e instanceof Error ? e.message : "상세 조회 실패");
    } finally {
      setIsLoadingDetail(false);
    }
  }, []);

  const runVectorSearch = useCallback(async () => {
    const text = q.trim();
    if (text.length < 3) {
      setVectorError("검색어는 최소 3자 이상 입력해주세요.");
      setVectorHits(null);
      return;
    }
    setIsVectorLoading(true);
    setVectorError(null);
    try {
      const docTypes = Object.entries(docTypeToggles)
        .filter(([, v]) => v)
        .map(([k]) => k);
      const res = await fetch("/api/admin/vector-store/query", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          query_text: text,
          top_k: 50,
          doc_types: docTypes,
          doc_type_weights: docTypeWeights,
          explain: true,
        }),
        cache: "no-store",
      });
      const payload = (await res.json()) as VectorQueryResponse | null;
      if (!res.ok) {
        const msg = payload?.detail || "벡터 검색에 실패했습니다.";
        throw new Error(msg);
      }

      const map = new Map<number, VectorCardHit>();
      for (const r of payload?.results ?? []) {
        const meta = r.metadata;
        const cardId = meta?.card_id;
        if (typeof cardId !== "number") continue;
        const raw =
          typeof r.debug?.raw_score === "number"
            ? r.debug.raw_score
            : typeof r.score === "number"
              ? r.score
              : 0;
        const weight =
          typeof r.debug?.doc_type_weight === "number" ? r.debug.doc_type_weight : undefined;
        const adjusted =
          typeof r.debug?.adjusted_score === "number"
            ? r.debug.adjusted_score
            : typeof weight === "number"
              ? raw * weight
              : raw;
        const existing = map.get(cardId);
        if (!existing || (existing.adjusted_score ?? -Infinity) < adjusted) {
          map.set(cardId, {
            card_id: cardId,
            name: typeof meta?.name === "string" ? meta.name : undefined,
            issuer: typeof meta?.issuer === "string" ? meta.issuer : undefined,
            type: typeof meta?.type === "string" ? meta.type : undefined,
            raw_score: raw,
            doc_type_weight: weight,
            adjusted_score: adjusted,
            best_doc_type:
              typeof meta?.doc_type === "string" ? meta.doc_type : undefined,
            snippet: typeof r.text === "string" ? r.text.slice(0, 140) : undefined,
          });
        }
      }

      const hits = Array.from(map.values()).sort(
        (a, b) => (b.adjusted_score ?? 0) - (a.adjusted_score ?? 0)
      );
      setVectorHits(hits);
    } catch (e) {
      setVectorHits(null);
      setVectorError(e instanceof Error ? e.message : "벡터 검색 실패");
    } finally {
      setIsVectorLoading(false);
    }
  }, [q, docTypeToggles, docTypeWeights]);

  const runSearch = useCallback(() => {
    if (searchMode === "vector") {
      void runVectorSearch();
      return;
    }
    void fetchList(0);
  }, [fetchList, runVectorSearch, searchMode]);

  useEffect(() => {
    // 초기 로딩에서만 stats/list를 불러옵니다.
    // (검색어 q 변화로 fetchList 함수가 재생성되어도 stats가 같이 새로고침되지 않게 분리)
    void fetchStats();
    void fetchList(0);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const total =
    searchMode === "vector" ? (vectorHits?.length ?? 0) : (list?.total ?? 0);
  const canPrev = skip > 0;
  const canNext = skip + limit < total;

  return (
    <div className={styles.shell}> 

      <main className={styles.content}>
        <div className={styles.container}>
          <header className={styles.topHeader}>
            <div>
              <div className={styles.title}>관리자 페이지</div> 
            </div>
          </header>

          {statsError && <div className={styles.error}>{statsError}</div>}

          <section className={styles.kpis} aria-label="KPI">
            <div className={`${styles.kpiCard} ${styles.kpiCardBlue}`}>
              <div>
                <div className={styles.kpiLabel}>총 카드 문서</div>
                <div className={styles.kpiValue}>
                  {formatNumber(stats?.total_documents)}
                </div>
              </div>
              <div className={`${styles.kpiIconBox} ${styles.kpiIconBlue}`}>
                <UiIcon name="doc" className={styles.navIcon} />
              </div>
            </div>

            <div className={`${styles.kpiCard} ${styles.kpiCardGreen}`}>
              <div>
                <div className={styles.kpiLabel}>임베딩 포함 카드</div>
                <div className={styles.kpiValue}>
                  {formatNumber(stats?.documents_with_embeddings)}
                </div>
              </div>
              <div className={`${styles.kpiIconBox} ${styles.kpiIconGreen}`}>
                <UiIcon name="cpu" className={styles.navIcon} />
              </div>
            </div>

            <div className={`${styles.kpiCard} ${styles.kpiCardPurple}`}>
              <div>
                <div className={styles.kpiLabel}>doc_type 종류</div>
                <div className={styles.kpiValue}>
                  {stats?.doc_type_counts
                    ? formatNumber(Object.keys(stats.doc_type_counts).length)
                    : "-"}
                </div>
              </div>
              <div className={`${styles.kpiIconBox} ${styles.kpiIconPurple}`}>
                <UiIcon name="shapes" className={styles.navIcon} />
              </div>
            </div>
          </section>

          <section className={styles.card} aria-label="Distribution">
            <div className={styles.cardHeader}>
              <h2>데이터 분포 요약</h2>
              <span className={styles.pill}>
                {stats?.database ?? "-"} / {stats?.collection ?? "-"}
              </span>
            </div>
            <div className={styles.cardBody}>
              <div className={styles.barList}>
                {docTypeBars.map((row) => (
                  <div key={row.key} className={styles.barRow}>
                    <div style={{ fontWeight: 800 }}>{row.key}</div>
                    <div className={styles.bar}>
                      <div
                        className={`${styles.barFill} ${barFillClass(row.key)}`}
                        style={{ width: `${row.pct}%` }}
                      />
                    </div>
                    <div style={{ textAlign: "right", fontWeight: 800 }}>
                      {formatNumber(row.value)}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </section>

          <section className={styles.grid}>
          <div className={styles.card}>
            <div className={styles.cardHeader}>
              <h2>카드 목록</h2>
              <span className={styles.pill}>
                {formatNumber(total)}개
              </span>
            </div>
            <div className={styles.cardBody}>
              <div className={styles.controls} style={{ marginBottom: 10 }}>
                <div className={styles.searchField}>
                  <UiIcon name="search" className={styles.searchIcon} />
                  <input
                    className={styles.input}
                    value={q}
                    onChange={(e) => setQ(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") runSearch();
                    }}
                    placeholder={
                      searchMode === "vector"
                        ? "벡터 검색: 간편결제, 넷플릭스, 마트 30만원..."
                        : "검색: 카드명/발급사/card_id"
                    }
                  />
                </div>
                <div className={styles.segmented} role="tablist" aria-label="검색 방식">
                  <button
                    type="button"
                    role="tab"
                    className={`${styles.segButton} ${searchMode === "keyword" ? styles.segActive : ""}`}
                    onClick={() => {
                      setSearchMode("keyword");
                      setVectorHits(null);
                      setVectorError(null);
                    }}
                    aria-selected={searchMode === "keyword"}
                  >
                    키워드
                  </button>
                  <button
                    type="button"
                    role="tab"
                    className={`${styles.segButton} ${searchMode === "vector" ? styles.segActive : ""}`}
                    onClick={() => {
                      setSearchMode("vector");
                      setSkip(0);
                    }}
                    aria-selected={searchMode === "vector"}
                  >
                    벡터
                  </button>
                </div>
                <label className={styles.checkbox}>
                  <input
                    type="checkbox"
                    checked={withEmbeddingsOnly}
                    onChange={(e) => setWithEmbeddingsOnly(e.target.checked)}
                    disabled={searchMode === "vector"}
                  />
                  임베딩 있는 카드만
                </label>
                <button
                  className={`${styles.button} ${styles.buttonSmall}`}
                  type="button"
                  onClick={runSearch}
                  disabled={isLoadingList || isVectorLoading}
                >
                  {searchMode === "vector"
                    ? isVectorLoading
                      ? "검색 중..."
                      : "벡터 검색"
                    : isLoadingList
                      ? "검색 중..."
                      : "검색"}
                </button>
                <button
                  className={`${styles.button} ${styles.buttonSecondary} ${styles.buttonSmall}`}
                  type="button"
                  onClick={() => {
                    setQ("");
                    setWithEmbeddingsOnly(true);
                    setVectorHits(null);
                    setVectorError(null);
                    fetchList(0);
                  }}
                  disabled={isLoadingList || isVectorLoading}
                >
                  초기화
                </button>
              </div>

              {searchMode === "vector" && (
                <>
                  <div className={styles.controls} style={{ marginTop: 6 }}>
                    <span className={styles.muted} style={{ fontSize: 12, fontWeight: 800 }}>
                      검색 대상 doc_type
                    </span>
                    <label className={styles.checkbox}>
                      <input
                        type="checkbox"
                        checked={docTypeToggles.summary}
                        onChange={(e) =>
                          setDocTypeToggles((p) => ({ ...p, summary: e.target.checked }))
                        }
                      />
                      summary
                    </label>
                    <label className={styles.checkbox}>
                      <input
                        type="checkbox"
                        checked={docTypeToggles.benefit}
                        onChange={(e) =>
                          setDocTypeToggles((p) => ({ ...p, benefit: e.target.checked }))
                        }
                      />
                      benefit
                    </label>
                    <label className={styles.checkbox}>
                      <input
                        type="checkbox"
                        checked={docTypeToggles.notes}
                        onChange={(e) =>
                          setDocTypeToggles((p) => ({ ...p, notes: e.target.checked }))
                        }
                      />
                      notes
                    </label>
                  </div>
                  <div className={styles.weightsBox}>
                    <div className={styles.weightsHeader}>
                      <div>
                        <div className={styles.weightsTitle}>doc_type 가중치(×)</div>
                        <div className={styles.weightsSubtitle}>
                          각 결과의 <strong>raw_score</strong>에 가중치(×)를 곱해{" "}
                          <strong>adjusted_score</strong>를 만듭니다.
                        </div>
                      </div>
                      <button
                        type="button"
                        className={`${styles.button} ${styles.buttonSecondary} ${styles.buttonSmall}`}
                        onClick={() =>
                          setDocTypeWeights({ summary: 1.15, benefit: 1.0, notes: 0.85 })
                        }
                      >
                        기본값
                      </button>
                    </div>

                    <div className={styles.weightsTable} role="table" aria-label="doc_type 가중치 표">
                      <div className={styles.weightsRowHeader} role="row">
                        <div role="columnheader">doc_type</div>
                        <div role="columnheader">의미</div>
                        <div role="columnheader">가중치(×)</div>
                      </div>

                      <div className={styles.weightsRow} role="row">
                        <div role="cell">
                          <span className={docTypePillClass("summary")}>SUMMARY</span>
                        </div>
                        <div role="cell" className={styles.weightsMeaning}>
                          카드 전체 요약/조건(전월실적·연회비·태그 등)
                        </div>
                        <div role="cell">
                          <input
                            className={styles.input}
                            style={{ maxWidth: 120, paddingLeft: 12 }}
                            value={String(docTypeWeights.summary)}
                            onChange={(e) =>
                              setDocTypeWeights((p) => ({
                                ...p,
                                summary: Number(e.target.value) || 0,
                              }))
                            }
                            inputMode="decimal"
                            aria-label="summary 가중치"
                          />
                        </div>
                      </div>

                      <div className={styles.weightsRow} role="row">
                        <div role="cell">
                          <span className={docTypePillClass("benefit")}>BENEFIT</span>
                        </div>
                        <div role="cell" className={styles.weightsMeaning}>
                          카테고리별 혜택 본문(간편결제/마트/OTT 등)
                        </div>
                        <div role="cell">
                          <input
                            className={styles.input}
                            style={{ maxWidth: 120, paddingLeft: 12 }}
                            value={String(docTypeWeights.benefit)}
                            onChange={(e) =>
                              setDocTypeWeights((p) => ({
                                ...p,
                                benefit: Number(e.target.value) || 0,
                              }))
                            }
                            inputMode="decimal"
                            aria-label="benefit 가중치"
                          />
                        </div>
                      </div>

                      <div className={styles.weightsRow} role="row">
                        <div role="cell">
                          <span className={docTypePillClass("notes")}>NOTES</span>
                        </div>
                        <div role="cell" className={styles.weightsMeaning}>
                          유의사항/제외항목(할인 제외, 한도, 조건 상세)
                        </div>
                        <div role="cell">
                          <input
                            className={styles.input}
                            style={{ maxWidth: 120, paddingLeft: 12 }}
                            value={String(docTypeWeights.notes)}
                            onChange={(e) =>
                              setDocTypeWeights((p) => ({
                                ...p,
                                notes: Number(e.target.value) || 0,
                              }))
                            }
                            inputMode="decimal"
                            aria-label="notes 가중치"
                          />
                        </div>
                      </div>
                    </div>
                  </div>
                  <div className={styles.formulaBox}>
                    <div className={styles.formulaTitle}>점수 계산 방식</div>
                    <div className={styles.formulaBody}>
                      <code>adjusted_score = raw_score × doc_type_weight</code>
                      <div className={styles.formulaHint}>
                        - <strong>raw_score</strong>: MongoDB Vector Search에서 나온 원본 점수
                        <br />
                        - <strong>doc_type_weight</strong>: 위에서 설정한 가중치(×) (예: summary 1.15)
                        <br />
                        - <strong>adjusted_score</strong>: 카드 랭킹/정렬에 사용하는 최종 점수
                      </div>
                    </div>
                  </div>
                  {isVectorLoading && (
                    <div className={styles.loadingRow} aria-live="polite">
                      <span className={styles.spinner} aria-hidden="true" />
                      벡터 검색 중…
                    </div>
                  )}
                </>
              )}
              <div className={styles.legend}>
                카드 type 의미: <strong>C</strong>=신용 · <strong>D</strong>=체크 ·{" "}
                <strong>P</strong>=선불
              </div>

              {searchMode === "vector" ? (
                vectorError && <div className={styles.error}>{vectorError}</div>
              ) : (
                listError && <div className={styles.error}>{listError}</div>
              )}

              <div className={styles.tableWrap}>
                <table className={styles.table}>
                  <thead>
                    <tr>
                      <th style={{ width: 90 }}>card_id</th>
                      <th>카드명</th>
                      <th style={{ width: 160 }}>발급사</th>
                      <th style={{ width: 90 }}>type</th>
                      {searchMode === "vector" ? (
                        <>
                          <th style={{ width: 110 }}>adj</th>
                          <th style={{ width: 110 }}>raw</th>
                          <th style={{ width: 90 }}>w</th>
                          <th style={{ width: 120 }}>doc_type</th>
                        </>
                      ) : (
                        <>
                          <th style={{ width: 110 }}>chunks</th>
                          <th style={{ width: 170 }}>updated_at</th>
                        </>
                      )}
                    </tr>
                  </thead>
                  <tbody>
                    {searchMode === "vector"
                      ? (vectorHits ?? []).map((hit) => {
                          const isSelected = hit.card_id === selectedCardId;
                          return (
                            <tr
                              key={`v_${hit.card_id}`}
                              style={{
                                background: isSelected
                                  ? "rgba(37,99,235,0.06)"
                                  : "transparent",
                              }}
                            >
                              <td>
                                <button
                                  type="button"
                                  className={styles.rowButton}
                                  onClick={() => fetchDetail(hit.card_id)}
                                  disabled={isLoadingDetail}
                                >
                                  {hit.card_id}
                                </button>
                              </td>
                              <td>
                                <button
                                  type="button"
                                  className={styles.rowButton}
                                  onClick={() => fetchDetail(hit.card_id)}
                                  disabled={isLoadingDetail}
                                >
                                  <div style={{ fontWeight: 900 }}>
                                    {hit.name ?? "-"}
                                  </div>
                                </button>
                              </td>
                              <td className={styles.muted}>{hit.issuer ?? "-"}</td>
                              <td>
                                <span
                                  className={styles.pill}
                                  title="C=신용카드, D=체크카드, P=선불카드"
                                >
                                  {hit.type ?? "-"}
                                </span>
                              </td>
                              <td className={styles.muted}>
                                {typeof hit.adjusted_score === "number"
                                  ? hit.adjusted_score.toFixed(4)
                                  : "-"}
                              </td>
                              <td className={styles.muted}>
                                {typeof hit.raw_score === "number"
                                  ? hit.raw_score.toFixed(4)
                                  : "-"}
                              </td>
                              <td className={styles.muted}>
                                {typeof hit.doc_type_weight === "number"
                                  ? hit.doc_type_weight.toFixed(2)
                                  : "-"}
                              </td>
                              <td>
                                <span className={docTypePillClass(hit.best_doc_type)}>
                                  {String(hit.best_doc_type ?? "unknown").toUpperCase()}
                                </span>
                              </td>
                            </tr>
                          );
                        })
                      : (list?.items ?? []).map((item) => {
                          const isSelected = item.card_id === selectedCardId;
                          return (
                            <tr
                              key={`k_${item.card_id}`}
                              style={{
                                background: isSelected
                                  ? "rgba(37,99,235,0.06)"
                                  : "transparent",
                              }}
                            >
                              <td>
                                <button
                                  type="button"
                                  className={styles.rowButton}
                                  onClick={() => fetchDetail(item.card_id)}
                                  disabled={isLoadingDetail}
                                >
                                  {item.card_id}
                                </button>
                              </td>
                              <td>
                                <button
                                  type="button"
                                  className={styles.rowButton}
                                  onClick={() => fetchDetail(item.card_id)}
                                  disabled={isLoadingDetail}
                                >
                                  <div style={{ fontWeight: 900 }}>
                                    {item.meta?.name ?? "-"}
                                  </div>
                                </button>
                              </td>
                              <td className={styles.muted}>{item.meta?.issuer ?? "-"}</td>
                              <td>
                                <span
                                  className={styles.pill}
                                  title="C=신용카드, D=체크카드, P=선불카드"
                                >
                                  {item.meta?.type ?? "-"}
                                </span>
                              </td>
                              <td>
                                <span className={styles.countPill}>
                                  {formatNumber(item.embeddings_count)}
                                </span>
                              </td>
                              <td className={styles.muted}>
                                {formatDate(item.updated_at)}
                              </td>
                            </tr>
                          );
                        })}
                    {searchMode === "vector" ? (
                      !isVectorLoading && (vectorHits?.length ?? 0) === 0 && (
                        <tr>
                          <td colSpan={8} className={styles.muted}>
                            검색 결과가 없습니다.
                          </td>
                        </tr>
                      )
                    ) : (
                      !isLoadingList && (list?.items?.length ?? 0) === 0 && (
                      <tr>
                        <td colSpan={6} className={styles.muted}>
                          표시할 카드가 없습니다.
                        </td>
                      </tr>
                      )
                    )}
                  </tbody>
                </table>
              </div>

              {searchMode !== "vector" && (
                <div
                  className={styles.controls}
                  style={{ marginTop: 10, justifyContent: "space-between" }}
                >
                  <button
                    type="button"
                    className={`${styles.button} ${styles.buttonSecondary} ${styles.buttonSmall}`}
                    onClick={() => fetchList(Math.max(0, skip - limit))}
                    disabled={!canPrev || isLoadingList}
                  >
                    이전
                  </button>
                  <div className={styles.muted} style={{ fontSize: 12 }}>
                    {skip + 1} ~ {Math.min(skip + limit, total)} / {formatNumber(total)}
                  </div>
                  <button
                    type="button"
                    className={`${styles.button} ${styles.buttonSecondary} ${styles.buttonSmall}`}
                    onClick={() => fetchList(skip + limit)}
                    disabled={!canNext || isLoadingList}
                  >
                    다음
                  </button>
                </div>
              )}
            </div>
          </div>

          <div className={styles.rightStack}>
            <div className={styles.card}>
              <div className={styles.cardHeader}>
                <h2>카드 상세</h2>
                <span className={styles.pill}>
                  {selectedCardId ? `card_id=${selectedCardId}` : "선택 없음"}
                </span>
              </div>
              <div className={styles.cardBody}>
              {detailError && <div className={styles.error}>{detailError}</div>}
              {!detail && !detailError && (
                <div className={styles.muted}>
                  왼쪽 목록에서 카드를 선택하면, 저장된 청크(문서)와 메타데이터를
                  확인할 수 있습니다.
                </div>
              )}

              {detail && (
                <div className={styles.twoCol}>
                  <div>
                    <div className={styles.detailTitle}>
                      <div>
                        <h3>{getStringField(detail.meta, "name") ?? "카드"}</h3>
                        <div className={styles.detailMeta}>
                          <span>{getStringField(detail.meta, "issuer") ?? "-"}</span>
                          <span className={styles.muted}>·</span>
                          <span className={styles.muted}>
                            {cardTypeLabel(getStringField(detail.meta, "type"))}
                          </span>
                          <span className={styles.muted}>·</span>
                          <span>{formatNumber(detail.embeddings_count)} chunks</span>
                        </div>
                      </div>
                      <div className={styles.muted} style={{ fontSize: 12 }}>
                        {formatDate(detail.updated_at)}
                      </div>
                    </div>
                  </div>

                  <div>
                    <div className={styles.cardHeader} style={{ border: "none", padding: 0 }}>
                      <h2 style={{ margin: 0 }}>저장된 청크(문서)</h2>
                      <span className={styles.pill}>
                        텍스트는 미리보기로 잘려서 표시됩니다
                      </span>
                    </div>
                    <div className={styles.chunks}>
                      {(detail.embeddings ?? []).slice(0, 12).map((c, idx) => (
                        <div key={`${c.doc_id ?? idx}`} className={styles.chunk}>
                          <div className={styles.chunkHead}>
                            <span className={styles.docTypeBadge}>
                              <span className={docTypePillClass(c.doc_type)}>
                                {(c.doc_type ?? "unknown").toUpperCase()}
                              </span>
                              <span className={styles.muted}>
                                {c.doc_id ? `${c.doc_id}` : ""}
                              </span>
                            </span>
                            {"distance" in c && typeof c.distance === "number" ? (
                              <span className={styles.muted}>
                                dist {c.distance.toFixed(4)}
                              </span>
                            ) : (
                              <span className={styles.muted}>
                                meta{" "}
                                {c.metadata ? Object.keys(c.metadata).length : 0}
                              </span>
                            )}
                          </div>
                          {c.metadata && (
                            <div className={styles.muted} style={{ fontSize: 11, marginBottom: 6 }}>
                              {typeof c.metadata["category_std"] === "string" && c.metadata["category_std"]
                                ? `category_std=${String(c.metadata["category_std"])}`
                                : ""}
                              {typeof c.metadata["benefit_type"] === "string" && c.metadata["benefit_type"]
                                ? ` · benefit_type=${String(c.metadata["benefit_type"])}`
                                : ""}
                              {typeof c.metadata["requires_spend"] === "boolean"
                                ? ` · requires_spend=${String(c.metadata["requires_spend"])}`
                                : ""}
                              {typeof c.metadata["text_len"] === "number"
                                ? ` · text_len=${String(c.metadata["text_len"])}`
                                : ""}
                            </div>
                          )}
                          <div className={styles.chunkText}>{c.text ?? ""}</div>
                        </div>
                      ))}
                      {(detail.embeddings ?? []).length > 12 && (
                        <div className={styles.muted} style={{ fontSize: 12 }}>
                          미리보기는 최대 12개 청크만 표시합니다.
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              )}
              </div>
            </div>
          </div>
        </section>
        </div>
      </main>
    </div>
  );
}

