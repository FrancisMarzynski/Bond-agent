import type { NextRequest } from "next/server";

const API_URL = process.env.API_URL ?? "http://localhost:8000";
const INTERNAL_PROXY_TOKEN_HEADER = "X-Bond-Internal-Proxy-Token";
const BODYLESS_METHODS = new Set(["GET", "HEAD"]);

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

function joinUrlPath(basePath: string, pathname: string): string {
  const normalizedBase = basePath === "/" ? "" : basePath.replace(/\/+$/, "");
  return `${normalizedBase}${pathname}`;
}

function buildProxyTarget(request: NextRequest): URL {
  const target = new URL(API_URL);
  target.pathname = joinUrlPath(target.pathname, request.nextUrl.pathname);
  target.search = request.nextUrl.search;
  return target;
}

function buildProxyRequestHeaders(request: NextRequest): Headers {
  const headers = new Headers(request.headers);

  headers.delete("authorization");
  headers.delete("connection");
  headers.delete("content-length");
  headers.delete("host");
  headers.delete(INTERNAL_PROXY_TOKEN_HEADER);

  const proxyToken = process.env.INTERNAL_PROXY_TOKEN ?? "";
  if (proxyToken) {
    headers.set(INTERNAL_PROXY_TOKEN_HEADER, proxyToken);
  }

  return headers;
}

async function proxyRequest(request: NextRequest): Promise<Response> {
  const target = buildProxyTarget(request);
  const headers = buildProxyRequestHeaders(request);
  const init: RequestInit = {
    method: request.method,
    headers,
    cache: "no-store",
    redirect: "manual",
  };

  if (!BODYLESS_METHODS.has(request.method.toUpperCase())) {
    const body = await request.arrayBuffer();
    if (body.byteLength > 0) {
      init.body = body;
    }
  }

  try {
    const upstream = await fetch(target, init);
    const responseHeaders = new Headers(upstream.headers);
    responseHeaders.set("Cache-Control", responseHeaders.get("Cache-Control") ?? "no-cache");
    return new Response(upstream.body, {
      status: upstream.status,
      statusText: upstream.statusText,
      headers: responseHeaders,
    });
  } catch {
    return new Response("Nie udało się połączyć z backendem.", {
      status: 502,
      headers: { "Cache-Control": "no-store" },
    });
  }
}

export async function GET(request: NextRequest) {
  return proxyRequest(request);
}

export async function POST(request: NextRequest) {
  return proxyRequest(request);
}

export async function PUT(request: NextRequest) {
  return proxyRequest(request);
}

export async function PATCH(request: NextRequest) {
  return proxyRequest(request);
}

export async function DELETE(request: NextRequest) {
  return proxyRequest(request);
}

export async function HEAD(request: NextRequest) {
  return proxyRequest(request);
}
