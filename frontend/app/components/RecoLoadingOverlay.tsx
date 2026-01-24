"use client";

import React, { useEffect, useMemo, useRef, useState } from "react";
import Lottie from "lottie-react";
import cashOrCardAnim from "@/Cash or Card.json";

type StageKey = "ANALYZE" | "FILTER" | "SCORE" | "RANK" | "GENERATE";

type Stage = {
  key: StageKey;
  title: string;
  desc: string;
  anim: object; 
  startAtMs: number;
}; 

const STAGES: Stage[] = [
  {
    key: "ANALYZE",
    title: "패턴 분석",
    desc: "소비 카테고리와 선호 혜택을 정리합니다.",
    anim: cashOrCardAnim as unknown as object,
    startAtMs: 0,
  },
  {
    key: "FILTER",
    title: "후보군 필터링",
    desc: "연회비·전월실적 조건으로 후보를 줄입니다.",
    anim: cashOrCardAnim as unknown as object,
    startAtMs: 12000,
  },
  {
    key: "SCORE",
    title: "혜택 매칭",
    desc: "할인·적립 혜택을 점수화해 비교합니다.",
    anim: cashOrCardAnim as unknown as object,
    startAtMs: 24000,
  },
  {
    key: "RANK",
    title: "최종 정렬",
    desc: "상위 카드의 우선순위를 확정합니다.",
    anim: cashOrCardAnim as unknown as object,
    startAtMs: 39000,
  },
  {
    key: "GENERATE",
    title: "추천 생성",
    desc: "추천 이유와 함께 결과를 생성합니다.",
    anim: cashOrCardAnim as unknown as object,
    startAtMs: 51000,
  },
];

function clamp(n: number, min: number, max: number) {
  return Math.max(min, Math.min(max, n));
}

// 초반 빠르게, 후반 천천히(체감상 자연스러움)
function easeOutCubic(t: number) {
  return 1 - Math.pow(1 - t, 3);
}

export type RecoLoadingOverlayProps = {
  open: boolean;
  /** 서버 응답이 완료되면 true로 변경 */
  done: boolean;
  /** 오버레이 닫고 싶을 때 호출 (예: percent가 100 되었을 때) */
  onClose?: () => void;

  /** 예상 대기시간(기본 60초) */
  expectedMs?: number;

  /** 사용자가 취소 가능하게 할지 */
  cancellable?: boolean;
  onCancel?: () => void;
};

export default function RecoLoadingOverlay({
  open,
  done,
  onClose,
  expectedMs = 60000,
  cancellable = true,
  onCancel,
}: RecoLoadingOverlayProps) {
  const [stageIdx, setStageIdx] = useState(0);
  const [percent, setPercent] = useState(0);
  const [isMobile, setIsMobile] = useState(false);

  const startTsRef = useRef<number | null>(null);
  const rafRef = useRef<number | null>(null);
  const closedRef = useRef(false);

  const stage = useMemo(() => STAGES[stageIdx] ?? STAGES[0], [stageIdx]);

  // 반응형 체크
  useEffect(() => {
    const checkMobile = () => {
      setIsMobile(window.innerWidth <= 768);
    };
    checkMobile();
    window.addEventListener('resize', checkMobile);
    return () => window.removeEventListener('resize', checkMobile);
  }, []);

  useEffect(() => {
    if (!open) {
      // 리셋
      setStageIdx(0);
      setPercent(0);
      startTsRef.current = null;
      closedRef.current = false;
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
      return;
    }

    startTsRef.current = performance.now();

    const tick = (now: number) => {
      const start = startTsRef.current ?? now;
      const elapsed = now - start;

      // 단계 전환
      // 현재 elapsed가 어느 stage startAtMs를 넘었는지 계산
      let nextStageIdx = 0;
      for (let i = 0; i < STAGES.length; i++) {
        if (elapsed >= STAGES[i].startAtMs) nextStageIdx = i;
      }
      setStageIdx(nextStageIdx);

      // 진행률
      if (!done) {
        // 0 -> 95%를 expectedMs 동안 도달
        const t = clamp(elapsed / expectedMs, 0, 1);
        const eased = easeOutCubic(t);
        const target = Math.floor(eased * 95);
        setPercent((p) => (target > p ? target : p));
      } else {
        // done이면 95~100을 빠르게 마무리
        setPercent((p) => {
          const base = p < 95 ? 95 : p;
          const next = base + Math.max(1, Math.floor((100 - base) * 0.25));
          return next >= 100 ? 100 : next;
        });
      }

      rafRef.current = requestAnimationFrame(tick);
    };

    rafRef.current = requestAnimationFrame(tick);

    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    };
  }, [open, done, expectedMs]);

  // 100% 도달 시 닫기
  useEffect(() => {
    if (!open) return;
    if (percent < 100) return;
    if (closedRef.current) return;
    closedRef.current = true;

    // 약간의 완주 연출 여백을 주고 닫기
    const t = window.setTimeout(() => onClose?.(), 250);
    return () => window.clearTimeout(t);
  }, [open, percent, onClose]);

  if (!open) return null;

  return (
    <div style={styles.backdrop} role="dialog" aria-modal="true">
      <div style={{
        ...styles.panel,
        gridTemplateColumns: isMobile ? "1fr" : "280px 1fr",
        padding: isMobile ? 16 : 18,
      }}>
        <div style={styles.left}>
          <div style={styles.lottieBox}>
            <Lottie
              animationData={stage.anim}
              loop
              autoplay
              style={{ width: 220, height: 220 }}
            />
          </div>

          <div style={styles.smallInfo}>
            <div style={styles.smallLabel}>현재 단계</div>
            <div style={styles.smallValue}>
              {stageIdx + 1}/{STAGES.length}
            </div>
          </div>
        </div>

        <div style={styles.right}>
          <div style={styles.title}>{stage.title}</div>
          <div style={styles.desc}>{stage.desc}</div>

          <div style={styles.progressRow}>
            <div style={styles.bar}>
              <div style={{ ...styles.barFill, width: `${percent}%` }} />
            </div>
            <div style={styles.percent}>{percent}%</div>
          </div>

          <div style={styles.hint}>
            보통 40~60초 정도 걸립니다. 비교 계산을 진행 중입니다.
          </div>

          {cancellable && (
            <div style={styles.actions}>
              <button
                type="button"
                onClick={onCancel}
                style={styles.cancelBtn}
              >
                취소
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  backdrop: {
    position: "fixed",
    inset: 0,
    background: "rgba(0,0,0,0.55)",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    zIndex: 9999,
    padding: 16,
  },
  panel: {
    width: "min(760px, 100%)",
    background: "#111827",
    borderRadius: 18,
    padding: 18,
    display: "grid",
    gap: 16,
    boxShadow: "0 20px 60px rgba(0,0,0,0.35)",
  },
  left: {
    display: "flex",
    flexDirection: "column",
    gap: 12,
  },
  lottieBox: {
    borderRadius: 14,
    background: "#0B1220",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    padding: 10,
    minHeight: 260,
  },
  smallInfo: {
    borderRadius: 14,
    background: "#0B1220",
    padding: 12,
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
  },
  smallLabel: { color: "rgba(255,255,255,0.6)", fontSize: 12 },
  smallValue: { color: "white", fontSize: 12, fontWeight: 700 },
  right: {
    display: "flex",
    flexDirection: "column",
    gap: 10,
    paddingTop: 8,
  },
  title: { color: "white", fontSize: 18, fontWeight: 800 },
  desc: { color: "rgba(255,255,255,0.75)", fontSize: 14, lineHeight: 1.5 },
  progressRow: { display: "flex", alignItems: "center", gap: 10, marginTop: 6 },
  bar: {
    flex: 1,
    height: 10,
    background: "rgba(255,255,255,0.12)",
    borderRadius: 999,
    overflow: "hidden",
  },
  barFill: {
    height: "100%",
    background: "rgba(255,255,255,0.88)",
    borderRadius: 999,
    transition: "width 180ms linear",
  },
  percent: { color: "white", fontSize: 12, width: 48, textAlign: "right" },
  hint: { color: "rgba(255,255,255,0.55)", fontSize: 12, marginTop: 2 },
  actions: { marginTop: 10, display: "flex", justifyContent: "flex-end" },
  cancelBtn: {
    borderRadius: 10,
    border: "1px solid rgba(255,255,255,0.18)",
    background: "transparent",
    color: "rgba(255,255,255,0.9)",
    padding: "10px 12px",
    fontSize: 13,
    cursor: "pointer",
    transition: "all 0.2s ease",
  },
};
