'use client';

import dynamic from "next/dynamic";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import styles from "./page.module.css";
import type { RecommendResponse } from "@/types/recommendation";

type RequestStatus = "idle" | "loading" | "success" | "error";

const MIN_INPUT_LENGTH = 15;
const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

const SAMPLE_PROMPTS = [
  "사회초년생 / 월 200~300 / 간편결제 위주",
  "해외 결제, 항공 마일리지 많이 쓰고 싶어요",
  "마트 30만원, 배달앱 10만원, 연회비 2만원 이내"
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

export default function HomePage() {
  const [userInput, setUserInput] = useState("");
  const [status, setStatus] = useState<RequestStatus>("idle");
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<RecommendResponse | null>(null);
  const [isHydrated, setIsHydrated] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);

  const trimmedLength = userInput.trim().length;
  const isTooShort =
    trimmedLength > 0 && trimmedLength < MIN_INPUT_LENGTH && status !== "loading";
  const isSubmitDisabled =
    trimmedLength < MIN_INPUT_LENGTH || status === "loading";

  const breakdownEntries = useMemo(() => {
    if (!result?.analysis?.category_breakdown) return [];
    return Object.entries(result.analysis.category_breakdown)
      .filter(([, amount]) => amount > 0)
      .sort((a, b) => b[1] - a[1]);
  }, [result]);

  const focusTextarea = () => {
    requestAnimationFrame(() => textareaRef.current?.focus());
  };

  useEffect(() => {
    if (typeof window === "undefined") return;
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (stored) {
      try {
        const parsed = JSON.parse(stored) as Partial<{
          userInput: unknown;
          status: unknown;
          error: unknown;
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

        if (parsed.result && isRecommendResponse(parsed.result)) {
          setResult(parsed.result);
        }
      } catch (restoreError) {
        console.warn("로컬 스토리지 상태 복원 실패:", restoreError);
      }
    }
    setIsHydrated(true);
  }, []);

  useEffect(() => {
    if (!isHydrated || typeof window === "undefined") return;
    try {
      window.localStorage.setItem(
        STORAGE_KEY,
        JSON.stringify({
          userInput,
          status,
          error,
          result,
        })
      );
    } catch (persistError) {
      console.warn("로컬 스토리지 저장 실패:", persistError);
    }
  }, [isHydrated, userInput, status, error, result]);

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
        const detail =
          (payload as { detail?: string } | null)?.detail ??
          "조건이 너무 까다로운 것 같아요. 연회비/전월 실적 조건을 조금 완화해서 다시 시도해보세요.";
        throw new Error(detail);
      }

      if (!isRecommendResponse(payload)) {
        throw new Error("응답 형식이 올바르지 않습니다. 잠시 후 다시 시도해주세요.");
      }

      setResult(payload);
      setStatus("success");
    } catch (fetchError) {
      console.error(fetchError);
      const message =
        fetchError instanceof Error
          ? fetchError.message
          : "일시적인 오류가 발생했습니다. 잠시 후 다시 시도해주세요.";
      setError(message);
      setStatus("error");
    }
  }, [userInput]);

  const handleSubmit = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    requestRecommendation();
  };

  const handleRetry = () => {
    requestRecommendation();
  };

  const handleAdjust = () => {
    setStatus("idle");
    setError(null);
    setResult(null);
    focusTextarea();
  };

  const handleReset = () => {
    setUserInput("");
    setStatus("idle");
    setError(null);
    setResult(null);
    focusTextarea();
  };

  const handlePromptClick = (prompt: string) => {
    setUserInput(prompt);
    setStatus("idle");
    setResult(null);
    setError(null);
    focusTextarea();
  };

  const explanationMarkdown = result?.explanation ?? "";

  return (
    <main className={styles.page}>
      <section className={styles.hero}>
        <p className={styles.eyebrow}>AI Credit Card Advisor</p>
        <h1 className={styles.title}>나에게 맞는 신용카드 추천</h1>
        <p className={styles.subtitle}>
          소비 패턴을 자연어로 적어주시면, AI가 카드 한 장을 골라드립니다.
          연회비나 전월 실적 조건 걱정 없이 바로 비교해보세요.
        </p>
      </section>

      <section className={styles.workspace}>
        <article className={styles.inputCard}>
          <header>
            <h2>소비 패턴 입력</h2>
            <p>최소 15자 이상 자세히 적어주실수록 정확도가 높아집니다.</p>
          </header>

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
                  : "예산, 선호 혜택, 연회비 조건을 함께 적어주세요."}
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
            <p className={styles.placeholder}>
              아직 추천을 받지 않았어요. 조건을 입력하고 버튼을 눌러보세요.
            </p>
          )}

          {status === "loading" && (
            <div className={styles.loadingBox}>
              <div className={styles.spinner} aria-hidden />
              <div>
                <p>소비 패턴을 분석하고 있어요…</p>
                <small>약 5~10초 정도 소요될 수 있습니다.</small>
              </div>
            </div>
          )}

          {status === "error" && (
            <div className={styles.errorBox}>
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
                    label: "순 혜택",
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
                  <h4>이 카드를 추천한 이유</h4>
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
                  조건 조금 바꿔서 다시 질문하기
                </button>
                <button
                  type="button"
                  className={styles.ghostButton}
                  onClick={handleReset}
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
