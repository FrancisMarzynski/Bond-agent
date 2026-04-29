// In local development, hit the FastAPI server directly to avoid Next dev rewrite
// buffering/interrupting long-lived SSE POST streams.
export const API_URL = process.env.NODE_ENV === "development"
  ? "http://127.0.0.1:8000"
  : "";

/** Maximum allowed file upload size in bytes (50 MB). */
export const MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024;
