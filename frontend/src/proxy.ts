import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

const API_PREFIX = "/api/";
const BASIC_AUTH_CHALLENGE = 'Basic realm="Bond - dostep wewnetrzny", charset="UTF-8"';

const PUBLIC_EXACT_PATHS = new Set([
  "/favicon.ico",
  "/healthz",
  "/manifest.json",
  "/manifest.webmanifest",
  "/robots.txt",
  "/sitemap.xml",
]);

const PUBLIC_PREFIXES = ["/_next/"];
const PUBLIC_METADATA_ROUTE = /^\/(?:apple-icon|icon|opengraph-image|twitter-image)(?:\/|$|\.)/;

function isTruthyEnv(value: string | undefined): boolean {
  if (!value) {
    return false;
  }

  switch (value.trim().toLowerCase()) {
    case "1":
    case "on":
    case "true":
    case "yes":
      return true;
    default:
      return false;
  }
}

function normalizePathname(pathname: string): string {
  if (!pathname || pathname === "/") {
    return "/";
  }

  const normalized = pathname.replace(/\/+$/, "");
  return normalized || "/";
}

function isPublicPath(pathname: string): boolean {
  const normalizedPath = normalizePathname(pathname);

  if (PUBLIC_EXACT_PATHS.has(normalizedPath)) {
    return true;
  }

  if (PUBLIC_PREFIXES.some((prefix) => pathname.startsWith(prefix))) {
    return true;
  }

  return PUBLIC_METADATA_ROUTE.test(normalizedPath);
}

function constantTimeEqual(left: string, right: string): boolean {
  const leftBytes = new TextEncoder().encode(left);
  const rightBytes = new TextEncoder().encode(right);
  const maxLength = Math.max(leftBytes.length, rightBytes.length);
  let diff = leftBytes.length ^ rightBytes.length;

  for (let index = 0; index < maxLength; index += 1) {
    diff |= (leftBytes[index] ?? 0) ^ (rightBytes[index] ?? 0);
  }

  return diff === 0;
}

function decodeBase64Utf8(value: string): string | null {
  try {
    const binary = atob(value);
    const bytes = Uint8Array.from(binary, (char) => char.charCodeAt(0));
    return new TextDecoder().decode(bytes);
  } catch {
    return null;
  }
}

function parseBasicAuthHeader(authorizationHeader: string | null): {
  username: string;
  password: string;
} | null {
  if (!authorizationHeader) {
    return null;
  }

  const [scheme, encodedValue] = authorizationHeader.split(" ");
  if (!encodedValue || scheme.toLowerCase() !== "basic") {
    return null;
  }

  const decodedValue = decodeBase64Utf8(encodedValue);
  if (!decodedValue) {
    return null;
  }

  const separatorIndex = decodedValue.indexOf(":");
  if (separatorIndex === -1) {
    return null;
  }

  return {
    username: decodedValue.slice(0, separatorIndex),
    password: decodedValue.slice(separatorIndex + 1),
  };
}

function hasValidBasicAuth(request: NextRequest): boolean {
  const expectedUsername = process.env.INTERNAL_BASIC_AUTH_USERNAME ?? "";
  const expectedPassword = process.env.INTERNAL_BASIC_AUTH_PASSWORD ?? "";

  if (!expectedUsername || !expectedPassword) {
    return false;
  }

  const parsedCredentials = parseBasicAuthHeader(request.headers.get("authorization"));
  if (!parsedCredentials) {
    return false;
  }

  return (
    constantTimeEqual(parsedCredentials.username, expectedUsername) &&
    constantTimeEqual(parsedCredentials.password, expectedPassword)
  );
}

function unauthorizedResponse(): NextResponse {
  return new NextResponse("Wymagane uwierzytelnienie.", {
    status: 401,
    headers: {
      "Cache-Control": "no-store",
      "WWW-Authenticate": BASIC_AUTH_CHALLENGE,
    },
  });
}

export function proxy(request: NextRequest) {
  const pathname = request.nextUrl.pathname;
  const internalAuthEnabled = isTruthyEnv(process.env.INTERNAL_AUTH_ENABLED);

  if (isPublicPath(pathname)) {
    return NextResponse.next();
  }

  if (internalAuthEnabled && !hasValidBasicAuth(request)) {
    return unauthorizedResponse();
  }

  if (pathname === "/api" || pathname.startsWith(API_PREFIX)) {
    return NextResponse.next();
  }

  return NextResponse.next();
}

export const config = {
  matcher: "/:path*",
};
