'use client';

import dynamic from "next/dynamic";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import styles from "./page.module.css";
import type { RecommendResponse } from "@/types/recommendation";
import Lottie from "lottie-react";
import cashOrCardAnim from "@/Cash or Card.json";

type RequestStatus = "idle" | "loading" | "success" | "error";

const MIN_INPUT_LENGTH = 15;
const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

const SAMPLE_PROMPTS = [
  "사회초년생 / 월소비 200만원에서 300만원 / 편의점과 배달앱 결제가 많음",
  "해외 결제가 많고 항공 마일리지 많이 모으고 싶어요",
  "마트에서 한 달에 약 30만원 정도 쓰고, 배달앱은 10만원 정도 사용합니다."
];

const ReactMarkdown = dynamic(() => import("react-markdown"), { ssr: false });
const STORAGE_KEY = "radical-cardist-recommend-state";
const ALLOWED_STATUSES: RequestStatus[] = ["idle", "loading", "success", "error"];

const replaceBrWithNewline = (text: string) =>
  text.replace(/<br\s*\/?>/gi, "\n");

const CATEGORY_LABELS: Record<string, string> = {
  digital_payment: "간편결제/페이",
  grocery: "마트/식료품",
  subscription_video: "OTT 구독",
  subscription_music: "음악/콘텐츠",
  subscription: "구독 서비스",
  online_shopping: "온라인 쇼핑",
  travel: "여행/항공",
  cafe: "카페",
  coffee: "카페",
  convenience_store: "편의점",
  dining: "외식",
  fuel: "주유",
  transportation: "교통",
  delivery: "배달앱",
  public_utilities: "공과금",
  education: "교육",
  mobile_payment: "모바일 결제"
};

const formatAmount = (value: number) =>
  new Intl.NumberFormat("ko-KR").format(value);

const toCategoryLabel = (key: string) =>
  CATEGORY_LABELS[key] ?? key.replace(/_/g, " ").toUpperCase();

const isRecommendResponse = (payload: unknown): payload is RecommendResponse => {
  if (!payload || typeof payload !== "object") return false;
  const data = payload as RecommendResponse;
  return (
    typeof data.explanation === "string" &&
    typeof data.card === "object" &&
    typeof data.analysis === "object"
  );
};

type RateLimitError = {
  error: string;
  message: string;
  reset_at?: string;
  limit?: number;
};

type RateLimitStatus = {
  limit: number;
  remaining: number;
  resetAt?: number;
};

export default function HomePage() {
  const [userInput, setUserInput] = useState("");
  const [status, setStatus] = useState<RequestStatus>("idle");
  const [error, setError] = useState<string | null>(null);
  const [rateLimitInfo, setRateLimitInfo] = useState<RateLimitError | null>(null);
  const [rateLimitStatus, setRateLimitStatus] = useState<RateLimitStatus | null>(null);
  const [result, setResult] = useState<RecommendResponse | null>(null);
  const [isHydrated, setIsHydrated] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const storageTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  // 메모이제이션된 파생 상태들
  const trimmedLength = useMemo(() => userInput.trim().length, [userInput]);
  
  const isTooShort = useMemo(
    () => trimmedLength > 0 && trimmedLength < MIN_INPUT_LENGTH && status !== "loading",
    [trimmedLength, status]
  );
  
  const isSubmitDisabled = useMemo(
    () => trimmedLength < MIN_INPUT_LENGTH || status === "loading",
    [trimmedLength, status]
  );

  const breakdownEntries = useMemo(() => {
    if (!result?.analysis?.category_breakdown) return [];
    return Object.entries(result.analysis.category_breakdown)
      .filter(([, amount]) => amount > 0)
      .sort((a, b) => b[1] - a[1]);
  }, [result]);

  const explanationMarkdown = useMemo(
    () => result?.explanation ?? "",
    [result?.explanation]
  );

  const focusTextarea = useCallback(() => {
    requestAnimationFrame(() => textareaRef.current?.focus());
  }, []);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (stored) {
      try {
        const parsed = JSON.parse(stored) as Partial<{
          userInput: unknown;
          status: unknown;
          error: unknown;
          rateLimitInfo: unknown;
          rateLimitStatus: unknown;
          result: unknown;
        }>;

        if (typeof parsed.userInput === "string") {
          setUserInput(parsed.userInput);
        }

        const storedStatus = ALLOWED_STATUSES.includes(
          parsed.status as RequestStatus
        )
          ? (parsed.status as RequestStatus)
          : "idle";
        setStatus(storedStatus === "loading" ? "idle" : storedStatus);

        setError(typeof parsed.error === "string" ? parsed.error : null);

        if (parsed.rateLimitInfo && typeof parsed.rateLimitInfo === "object" && parsed.rateLimitInfo !== null) {
          const rateLimit = parsed.rateLimitInfo as RateLimitError;
          if (rateLimit.error === "Rate limit exceeded") {
            setRateLimitInfo(rateLimit);
          }
        }

        if (parsed.rateLimitStatus && typeof parsed.rateLimitStatus === "object" && parsed.rateLimitStatus !== null) {
          const rateStatus = parsed.rateLimitStatus as RateLimitStatus;
          if (typeof rateStatus.limit === "number" && typeof rateStatus.remaining === "number") {
            setRateLimitStatus(rateStatus);
          }
        }

        if (parsed.result && isRecommendResponse(parsed.result)) {
          setResult(parsed.result);
        }
      } catch (restoreError) {
        console.warn("로컬 스토리지 상태 복원 실패:", restoreError);
      }
    }
    setIsHydrated(true);
  }, []);

  // localStorage 저장을 디바운싱하여 최적화
  useEffect(() => {
    if (!isHydrated || typeof window === "undefined") return;
    
    // 이전 타이머가 있으면 취소
    if (storageTimeoutRef.current) {
      clearTimeout(storageTimeoutRef.current);
    }
    
    // 500ms 후에 저장 (디바운싱)
    storageTimeoutRef.current = setTimeout(() => {
      try {
        window.localStorage.setItem(
          STORAGE_KEY,
          JSON.stringify({
            userInput,
            status,
            error,
            rateLimitInfo,
            rateLimitStatus,
            result,
          })
        );
      } catch (persistError) {
        console.warn("로컬 스토리지 저장 실패:", persistError);
      }
    }, 500);
    
    // cleanup 함수
    return () => {
      if (storageTimeoutRef.current) {
        clearTimeout(storageTimeoutRef.current);
      }
    };
  }, [isHydrated, userInput, status, error, rateLimitInfo, rateLimitStatus, result]);

  const requestRecommendation = useCallback(async () => {
    const trimmed = userInput.trim();
    if (trimmed.length < MIN_INPUT_LENGTH) {
      setError(`조금 더 구체적으로 적어주세요. (최소 ${MIN_INPUT_LENGTH}자)`);
      setStatus("idle");
      focusTextarea();
      return;
    }

    setStatus("loading");
    setError(null);
    setRateLimitInfo(null);
    setResult(null);

    try {
      const response = await fetch(
        `${API_BASE_URL}/recommend/natural-language`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ user_input: trimmed }),
          cache: "no-store"
        }
      );

      let payload: unknown = null;
      try {
        payload = await response.json();
      } catch {
        payload = null;
      }

      if (!response.ok) {
        const detail = (payload as { detail?: string | RateLimitError } | null)?.detail;
        
        // Rate limit 에러인 경우
        if (detail && typeof detail === "object" && "error" in detail && detail.error === "Rate limit exceeded") {
          const rateLimitError = detail as RateLimitError;
          setRateLimitInfo(rateLimitError);
          const errorMessage = ("message" in rateLimitError && typeof rateLimitError.message === "string")
            ? rateLimitError.message
            : "일일 추천 횟수를 초과했습니다.";
          throw new Error(errorMessage);
        }
        
        // 일반 에러인 경우
        const errorMessage = typeof detail === "string" 
          ? detail 
          : (typeof detail === "object" && detail && "message" in detail && typeof detail.message === "string")
            ? detail.message
            : "조건이 너무 까다로운 것 같아요. 연회비/전월 실적 조건을 조금 완화해서 다시 시도해보세요.";
        throw new Error(errorMessage);
      }

      if (!isRecommendResponse(payload)) {
        throw new Error("응답 형식이 올바르지 않습니다. 잠시 후 다시 시도해주세요.");
      }

      // Rate limit 헤더 읽기
      const limitHeader = response.headers.get("X-RateLimit-Limit");
      const remainingHeader = response.headers.get("X-RateLimit-Remaining");
      const resetHeader = response.headers.get("X-RateLimit-Reset");
      
      if (limitHeader && remainingHeader) {
        setRateLimitStatus({
          limit: parseInt(limitHeader, 10),
          remaining: parseInt(remainingHeader, 10),
          resetAt: resetHeader ? parseInt(resetHeader, 10) : undefined
        });
      }

      setResult(payload);
      setStatus("success");
      setRateLimitInfo(null);
    } catch (fetchError) {
      console.info(fetchError);
      const message =
        fetchError instanceof Error
          ? fetchError.message
          : "일시적인 오류가 발생했습니다. 잠시 후 다시 시도해주세요.";
      setError(message);
      setStatus("error");
    }
  }, [userInput, focusTextarea]);

  const handleSubmit = useCallback((event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    requestRecommendation();
  }, [requestRecommendation]);

  const handleRetry = useCallback(() => {
    requestRecommendation();
  }, [requestRecommendation]);

  const handleAdjust = useCallback(() => {
    setStatus("idle");
    setError(null);
    setRateLimitInfo(null);
    setResult(null);
    focusTextarea();
  }, [focusTextarea]);

  const handleReset = useCallback(() => {
    setUserInput("");
    setStatus("idle");
    setError(null);
    setRateLimitInfo(null);
    setResult(null);
    focusTextarea();
  }, [focusTextarea]);

  const handlePromptClick = useCallback((prompt: string) => {
    setUserInput(prompt);
    setStatus("idle");
    setResult(null);
    setError(null);
    setRateLimitInfo(null);
    focusTextarea();
  }, [focusTextarea]);

  // 로딩 애니메이션 상태 관리
  const [loadingStage, setLoadingStage] = useState(0);
  const [loadingPercent, setLoadingPercent] = useState(0);
  const loadingStartRef = useRef<number | null>(null);
  const loadingRafRef = useRef<number | null>(null);

  const STAGES = [
    { title: "패턴 분석", desc: "소비 카테고리와 선호 혜택을 정리합니다." },
    { title: "후보군 필터링", desc: "연회비·전월실적 조건으로 후보를 줄입니다." },
    { title: "혜택 매칭", desc: "할인·적립 혜택을 점수화해 비교합니다." },
    { title: "최종 정렬", desc: "상위 카드의 우선순위를 확정합니다." },
    { title: "추천 생성", desc: "추천 이유와 함께 결과를 생성합니다." },
  ];

  const STAGE_TIMES = [0, 12000, 24000, 39000, 51000];

  function clamp(n: number, min: number, max: number) {
    return Math.max(min, Math.min(max, n));
  }

  function easeOutCubic(t: number) {
    return 1 - Math.pow(1 - t, 3);
  }

  // 로딩 진행률 및 단계 관리
  useEffect(() => {
    if (status !== "loading") {
      setLoadingStage(0);
      setLoadingPercent(0);
      loadingStartRef.current = null;
      if (loadingRafRef.current) cancelAnimationFrame(loadingRafRef.current);
      loadingRafRef.current = null;
      return;
    }

    loadingStartRef.current = performance.now();

    const tick = (now: number) => {
      const start = loadingStartRef.current ?? now;
      const elapsed = now - start;

      // 단계 전환
      let nextStage = 0;
      for (let i = 0; i < STAGE_TIMES.length; i++) {
        if (elapsed >= STAGE_TIMES[i]) nextStage = i;
      }
      setLoadingStage(nextStage);

      // 진행률 (0 -> 95%)
      if (status === "loading") {
        const t = clamp(elapsed / 60000, 0, 1);
        const eased = easeOutCubic(t);
        const target = Math.floor(eased * 95);
        setLoadingPercent((p) => (target > p ? target : p));
      } else if (status === "success") {
        // 완료 시 95~100%로 빠르게 마무리
        setLoadingPercent((p) => {
          const base = p < 95 ? 95 : p;
          const next = base + Math.max(1, Math.floor((100 - base) * 0.25));
          return next >= 100 ? 100 : next;
        });
      }

      loadingRafRef.current = requestAnimationFrame(tick);
    };

    loadingRafRef.current = requestAnimationFrame(tick);

    return () => {
      if (loadingRafRef.current) cancelAnimationFrame(loadingRafRef.current);
      loadingRafRef.current = null;
    };
  }, [status]);

  return (
    <main className={styles.page}>
      <section className={styles.hero}>
        <p className={styles.eyebrow}>카데몽의 카드 추천</p>
        <h1 className={styles.title}>나에게 맞는 신용카드 추천</h1>
        <img src="/cademon_main.png" alt="cademon_main" style={{ width: "200px" }} />
        <p className={styles.subtitle}>
          소비 패턴을 적어주시면, 카데몽이 카드 한 장을 골라드립니다. <br></br>
          당신의 소비 흐름을 분석해 가장 잘 맞는 카드를 골라드립니다.
        </p>
        {rateLimitStatus && (
          <div style={{
            marginTop: "1rem",
            padding: "0.5rem 1rem",
            backgroundColor: "rgba(0, 0, 0, 0.05)",
            borderRadius: "0.5rem",
            fontSize: "0.875rem",
            color: "var(--text-secondary, #666)",
            display: "inline-block"
          }}>
            일일 요청 한도: {rateLimitStatus.remaining} / {rateLimitStatus.limit}회
          </div>
        )}
      </section>

      <section className={styles.workspace}>
        <article className={styles.inputCard}> 

          <form onSubmit={handleSubmit} className={styles.form} autoComplete="off">
            <label htmlFor="spending-textarea" className={styles.fieldLabel}>
              내 소비 습관
            </label>
            <textarea
              id="spending-textarea"
              ref={textareaRef}
              className={styles.textarea}
              rows={7}
              maxLength={800}
              placeholder="예) 마트에서 한 달에 30만원, 넷플릭스 구독, 배달앱 자주 씀. 연 회비는 2만원 이내였으면 좋지만, 혜택 좋으면 조금 더 내도 괜찮아요."
              value={userInput}
              onChange={(event) => setUserInput(event.target.value)}
              disabled={status === "loading"}
            />

            <div className={styles.promptList}>
              {SAMPLE_PROMPTS.map((prompt) => (
                <button
                  key={prompt}
                  type="button"
                  className={styles.promptButton}
                  onClick={() => handlePromptClick(prompt)}
                  disabled={status === "loading"}
                >
                  {prompt}
                </button>
              ))}
            </div>

            <div className={styles.formFooter}>
              <p
                className={styles.validation}
                aria-live="polite"
                role="status"
              >
                {isTooShort
                  ? `조금 더 구체적으로 적어주세요. (최소 ${MIN_INPUT_LENGTH}자)`
                  : "예산, 선호하는 혜택, 연회비 조건 등을 함께 적어주세요."}
              </p>
              <button
                type="submit"
                className={styles.submitButton}
                disabled={isSubmitDisabled}
              >
                {status === "loading" ? "분석 중..." : "카드 추천 받기"}
              </button>
            </div>
          </form>
        </article>

        <article className={styles.resultCard} aria-live="polite">
          {status === "idle" && !result && !error && (
            <div className={styles.idleAnimationBox}>
              <div className={styles.idleLottieContainer}>
                <Lottie
                  animationData={cashOrCardAnim as unknown as object}
                  loop
                  autoplay
                  style={{ width: 300, height: 300 }}
                />
              </div>
              <p className={styles.placeholder}>
                소비 패턴을 입력하고 카드 추천을 받아보세요
              </p>
            </div>
          )}

          {status === "loading" && (
            <div className={styles.loadingBox}>
              <div className={styles.lottieContainer}>
                <Lottie
                  animationData={cashOrCardAnim as unknown as object}
                  loop
                  autoplay
                  style={{ width: 280, height: 280 }}
                />
              </div>
              <div className={styles.loadingInfo}>
                <div className={styles.loadingTitle}>{STAGES[loadingStage]?.title || "처리 중"}</div>
                <div className={styles.loadingDesc}>{STAGES[loadingStage]?.desc || "계산을 진행 중입니다."}</div>
                <div className={styles.progressRow}>
                  <div className={styles.progressBar}>
                    <div 
                      className={styles.progressFill} 
                      style={{ width: `${loadingPercent}%` }}
                    />
                  </div>
                  <div className={styles.progressPercent}>{loadingPercent}%</div>
                </div>
                <div className={styles.loadingHint}>
                  보통 40~60초 정도 걸립니다. 비교 계산을 진행 중입니다.
                </div> 
              </div>
            </div>
          )}

          {status === "error" && (
            <div className={styles.errorBox}>
              {rateLimitInfo ? (
                <>
                  <p className={styles.errorTitle}>
                    일일 추천 횟수를 초과했습니다
                  </p>
                  <p>
                    {rateLimitInfo.message || "일일 추천 횟수를 초과했습니다. 내일 다시 시도해주세요."}
                  </p>
                  {rateLimitInfo.reset_at && (
                    <p style={{ fontSize: "0.9em", color: "var(--text-secondary)", marginTop: "0.5rem" }}>
                      제한 해제 시간: {new Date(rateLimitInfo.reset_at).toLocaleString("ko-KR", {
                        year: "numeric",
                        month: "long",
                        day: "numeric",
                        hour: "2-digit",
                        minute: "2-digit"
                      })}
                    </p>
                  )}
                  {rateLimitInfo.limit && (
                    <p style={{ fontSize: "0.9em", color: "var(--text-secondary)", marginTop: "0.25rem" }}>
                      일일 제한: {rateLimitInfo.limit}회
                    </p>
                  )}
                </>
              ) : (
                <>
                  <p className={styles.errorTitle}>
                    조건이 너무 까다로운 것 같아요.
                  </p>
                  <p>
                    {error ??
                      "연회비나 전월 실적 조건을 조금 완화해서 다시 시도해볼까요?"}
                  </p>
                  <button
                    type="button"
                    className={styles.retryButton}
                    onClick={handleRetry}
                    disabled={trimmedLength < MIN_INPUT_LENGTH}
                  >
                    다시 시도
                  </button>
                </>
              )}
            </div>
          )}

          {status === "success" && result && (
            <>
              <div className={styles.resultHeader}>
                <div>
                  <p className={styles.badge}>추천 완료</p>
                  <h3>{result.card.name}</h3>
                  <p className={styles.brand}>{result.card.brand}</p>
                </div>
                <div className={styles.savingsBox}>
                  <span>예상 절약액</span>
                  <strong>연 {formatAmount(result.card.annual_savings)}원</strong>
                  <small>월 {formatAmount(result.card.monthly_savings)}원</small>
                </div>
              </div>

              <ul className={styles.metaGrid}>
                {[
                  {
                    label: "연회비",
                    value: replaceBrWithNewline(result.card.annual_fee),
                    icon: "💳",
                  },
                  {
                    label: "전월 실적",
                    value: replaceBrWithNewline(result.card.required_spend),
                    icon: "📅",
                  },
                  {
                    label: "순 혜택(혜택금 - 연회비)",
                    value: `${formatAmount(result.analysis.net_benefit)}원`,
                    icon: "✨",
                  },
                ].map((item) => (
                  <li key={item.label} className={styles.metaItem}>
                    <div className={styles.metaLabel}>
                      <span className={styles.metaIcon} aria-hidden="true">
                        {item.icon}
                      </span>
                      <span>{item.label}</span>
                    </div>
                    <p className={styles.metaValue}>{item.value}</p>
                  </li>
                ))}
              </ul>

              {result.card.benefits?.length > 0 && (
                <section className={styles.benefits}>
                  <h4>주요 혜택</h4>
                  <ul>
                    {result.card.benefits.map((benefit) => (
                      <li key={benefit} className={styles.benefitPill}>
                        {benefit}
                      </li>
                    ))}
                  </ul>
                </section>
              )}

              {explanationMarkdown && (
                <section className={styles.explanation}> 
                  <div className={styles.markdown}>
                    <ReactMarkdown>{explanationMarkdown}</ReactMarkdown>
                  </div>
                </section>
              )}

              {(breakdownEntries.length > 0 ||
                result.analysis.warnings.length > 0) && (
                <section className={styles.analysis}>
                  {breakdownEntries.length > 0 && (
                    <div>
                      <h4>카테고리별 예상 절약액</h4>
                      <ul>
                        {breakdownEntries.map(([category, amount]) => (
                          <li key={category}>
                            <span>{toCategoryLabel(category)}</span>
                            <strong>{formatAmount(amount)}원/월</strong>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                  {result.analysis.warnings.length > 0 && (
                    <div>
                      <h4>주의사항</h4>
                      <ul>
                        {result.analysis.warnings.map((warning) => (
                          <li key={warning}>{warning}</li>
                        ))}
                      </ul>
        </div>
                  )}
                  {!result.analysis.conditions_met && (
                    <p className={styles.warningNote}>
                      전월 실적 조건을 충족하지 못할 수 있으니, 최근 소비액을
                      다시 확인해보세요.
                    </p>
                  )}
                </section>
              )}

              <div className={styles.actions}>
                <button
                  type="button"
                  className={styles.secondaryButton}
                  onClick={handleAdjust}
                >
                  새로 입력하기
                </button> 
        </div>
            </>
          )}
        </article>
      </section>
    </main>
  );
}
