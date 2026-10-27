import { NextRequest, NextResponse } from "next/server";

const allowed =
  /^(capabilities|backtests(?:\/[0-9a-f-]{36})?|paper\/(?:status|sessions(?:\/[0-9a-f-]{36}(?:\/(?:advance|start|pause|stop))?)?)|strategy-drafts(?:\/generate|\/[0-9a-f-]{36}(?:\/(?:approve|backtests))?)?)$/;
async function proxy(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> },
) {
  const path = (await context.params).path.join("/");
  if (!allowed.test(path))
    return NextResponse.json({ detail: "Not found" }, { status: 404 });
  const body = request.method === "POST" ? await request.text() : undefined;
  if (body && body.length > 8192)
    return NextResponse.json({ detail: "Request too large" }, { status: 413 });
  try {
    const base = process.env.API_INTERNAL_URL || "http://127.0.0.1:8000";
    const response = await fetch(`${base}/api/${path}`, {
      method: request.method,
      body,
      headers: { "Content-Type": "application/json" },
      cache: "no-store",
      signal: AbortSignal.timeout(90000),
    });
    return new NextResponse(await response.text(), {
      status: response.status,
      headers: { "Content-Type": "application/json" },
    });
  } catch {
    return NextResponse.json(
      { detail: "Research API is unavailable. Start the API and database." },
      { status: 503 },
    );
  }
}
export { proxy as GET, proxy as POST };
