import { NextRequest, NextResponse } from "next/server";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8000";

export async function POST(req: NextRequest) {
  const body = await req.text();

  let upstream: Response;
  try {
    upstream = await fetch(`${API_BASE}/copilot/run`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body,
    });
  } catch (e) {
    return NextResponse.json(
      { detail: `Could not reach backend at ${API_BASE}: ${String(e)}` },
      { status: 502 }
    );
  }

  const data = await upstream.text();
  return new NextResponse(data, {
    status: upstream.status,
    headers: { "Content-Type": "application/json" },
  });
}
