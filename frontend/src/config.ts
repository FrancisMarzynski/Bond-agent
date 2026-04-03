// Empty string = relative URL. All /api/* calls are proxied server-side
// via next.config.ts rewrites (using the API_URL env var, not exposed to browser).
export const API_URL = "";

/** Maximum allowed file upload size in bytes (50 MB). */
export const MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024;
