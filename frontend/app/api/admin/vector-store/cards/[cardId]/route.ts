import { NextResponse } from "next/server";

export const runtime = "nodejs";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export async function GET(
  request: Request,
  context: { params: Promise<{ cardId: string }> }
) {
  const adminKey = process.env.ADMIN_API_KEY;
  if (!adminKey) {
    return NextResponse.json(
      { error: "ADMIN_API_KEY 환경 변수가 설정되지 않았습니다." },
      { status: 500 }
    );
  }

  const { cardId } = await context.params;
  const url = new URL(request.url);
  const qs = url.searchParams.toString();
  const target = `${API_BASE_URL}/admin/vector-store/cards/${encodeURIComponent(
    cardId
  )}${qs ? `?${qs}` : ""}`;

  const res = await fetch(target, {
    headers: { "X-API-Key": adminKey },
    cache: "no-store",
  });

  const payload = await res.json().catch(() => null);
  return NextResponse.json(payload, { status: res.status });
}

