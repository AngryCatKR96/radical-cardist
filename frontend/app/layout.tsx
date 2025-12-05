import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: {
    default: "나에게 맞는 신용카드 추천 | Radical Cardist",
    template: "%s | Radical Cardist",
  },
  description:
    "소비 패턴을 자연어로 입력하면 AI가 최적의 신용카드를 한 장으로 정리해 추천합니다.",
  keywords: [
    "신용카드 추천",
    "카드 비교",
    "AI 카드 추천",
    "연회비 추천",
    "소비 패턴 분석",
  ],
  openGraph: {
    title: "나에게 맞는 신용카드 추천",
    description:
      "소비 패턴을 자연어로 입력하면 AI가 최적의 카드 혜택을 찾아드립니다.",
    siteName: "Radical Cardist",
    locale: "ko_KR",
    type: "website",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="ko">
      <body className={`${geistSans.variable} ${geistMono.variable}`}>
        {children}
      </body>
    </html>
  );
}
