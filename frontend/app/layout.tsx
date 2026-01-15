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
  metadataBase: new URL(process.env.NEXT_PUBLIC_BASE_URL || 'http://localhost:3000'),
  title: {
    default: "나에게 맞는 신용카드 추천 | 카데몽",
    template: "%s | 카데몽",
  },
  description: "카데몽이 여러분의 최고의 신용카드를 추천해줍니다.",
  openGraph: {
    title: "나에게 맞는 신용카드 추천",
    description: "카데몽이 여러분의 최고의 신용카드를 추천해줍니다.",
    siteName: "나에게 맞는 신용카드 추천 | 카데몽",
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
