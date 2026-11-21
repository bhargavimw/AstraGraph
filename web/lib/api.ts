/**
 * Typed client for the AstraGraph API (NEXT_PUBLIC_API_URL).
 *
 * - Every response is validated with its zod schema (lib/api-schemas.ts).
 * - Requests time out, can be cancelled with an AbortSignal, and are retried
 *   with exponential backoff when the server is unreachable or answers
 *   502/503/504 — what a free-tier host does while it wakes up (up to ~60 s).
 *   `onWaking` fires once when a request starts retrying, so the UI can show
 *   "Waking the telescope…".
 * - 4xx responses are not retried; they throw an ApiError carrying the
 *   server's message.
 */

import type { z } from "zod";
import {
  ConstellationDetailSchema,
  ConstellationListSchema,
  DemoSkyInfoSchema,
  FrameResponseSchema,
  HealthSchema,
  QuizGradeSchema,
  QuizNewSchema,
  SkyResponseSchema,
  TonightResponseSchema,
} from "@/lib/api-schemas";
import type {
  ApiConstellationDetail,
  ApiConstellationSummary,
  ApiDemoSkyInfo,
  ApiFrame,
  ApiQuiz,
  ApiQuizGrade,
  ApiSky,
  ApiTonight,
  ObserverLocation,
} from "@/lib/types";

export const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/+$/, "");

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number | null,
    readonly retryable: boolean,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export interface RequestOptions {
  signal?: AbortSignal;
  /** Per-attempt timeout (ms). */
  timeoutMs?: number;
  /** Total time budget for retries while the server wakes up (ms). */
  wakeBudgetMs?: number;
  /** Called once when the first attempt fails and retrying begins. */
  onWaking?: () => void;
}

const RETRY_STATUS = new Set([502, 503, 504]);

function sleep(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) return reject(signal.reason);
    const id = setTimeout(resolve, ms);
    signal?.addEventListener("abort", () => {
      clearTimeout(id);
      reject(signal.reason);
    }, { once: true });
  });
}

async function attempt(url: string, init: RequestInit, timeoutMs: number, outer?: AbortSignal): Promise<Response> {
  const controller = new AbortController();
  const onAbort = () => controller.abort(outer?.reason);
  outer?.addEventListener("abort", onAbort, { once: true });
  const timer = setTimeout(() => controller.abort(new DOMException("Timed out", "TimeoutError")), timeoutMs);
  try {
    return await fetch(url, { ...init, signal: controller.signal });
  } finally {
    clearTimeout(timer);
    outer?.removeEventListener("abort", onAbort);
  }
}

async function request<S extends z.ZodType>(
  path: string,
  schema: S,
  init: RequestInit = {},
  { signal, timeoutMs = 15000, wakeBudgetMs = 60000, onWaking }: RequestOptions = {},
): Promise<z.infer<S>> {
  const url = `${API_URL}${path}`;
  const started = Date.now();
  let delay = 1000;
  let warned = false;

  for (;;) {
    let retryable = false;
    let failure: ApiError;
    try {
      const response = await attempt(url, init, timeoutMs, signal);
      if (response.ok) {
        const body: unknown = await response.json();
        const parsed = schema.safeParse(body);
        if (!parsed.success) {
          throw new ApiError(`Unexpected response from ${path}: ${parsed.error.message}`, response.status, false);
        }
        return parsed.data;
      }
      retryable = RETRY_STATUS.has(response.status);
      failure = new ApiError(await errorMessage(response), response.status, retryable);
    } catch (error) {
      if (error instanceof ApiError) throw error;
      if (signal?.aborted) throw error; // cancelled by the caller: stop quietly
      retryable = true; // network error or timeout: the server may be asleep
      failure = new ApiError("Can't reach the AstraGraph server.", null, true);
    }
    if (!retryable || Date.now() - started + delay > wakeBudgetMs) throw failure;
    if (!warned) {
      warned = true;
      onWaking?.();
    }
    await sleep(delay, signal);
    delay = Math.min(delay * 1.8, 8000);
  }
}

async function errorMessage(response: Response): Promise<string> {
  try {
    const body: unknown = await response.json();
    if (typeof body === "object" && body !== null && "detail" in body) {
      const detail = (body as { detail: unknown }).detail;
      if (typeof detail === "string") return detail;
    }
  } catch {
    /* not JSON */
  }
  return `Request failed (${response.status})`;
}

const locationQuery = ({ lat, lon, tz }: ObserverLocation) =>
  new URLSearchParams({ lat: String(lat), lon: String(lon), tz });

// --------------------------------------------------------------- endpoints
export const api = {
  health: (opts?: RequestOptions) => request("/health", HealthSchema, {}, opts),

  sky: (location: ObserverLocation, offsetHours = 0, opts?: RequestOptions): Promise<ApiSky> => {
    const q = locationQuery(location);
    q.set("offset_hours", String(offsetHours));
    return request(`/sky?${q}`, SkyResponseSchema, {}, opts);
  },

  tonight: (location: ObserverLocation, opts?: RequestOptions): Promise<ApiTonight> =>
    request(`/tonight?${locationQuery(location)}`, TonightResponseSchema, {}, opts),

  constellations: (opts?: RequestOptions): Promise<ApiConstellationSummary[]> =>
    request("/constellations", ConstellationListSchema, {}, opts),

  constellation: (name: string, location: ObserverLocation, opts?: RequestOptions): Promise<ApiConstellationDetail> =>
    request(`/constellation/${encodeURIComponent(name)}?${locationQuery(location)}`, ConstellationDetailSchema, {}, opts),

  newQuiz: (mode: "easy" | "hard", constellation?: string, opts?: RequestOptions): Promise<ApiQuiz> => {
    const q = new URLSearchParams({ mode });
    if (constellation) q.set("constellation", constellation);
    return request(`/quiz/new?${q}`, QuizNewSchema, {}, opts);
  },

  gradeQuiz: (id: string, edges: Array<[string, string]>, opts?: RequestOptions): Promise<ApiQuizGrade> =>
    request("/quiz/grade", QuizGradeSchema, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id, edges }),
    }, opts),

  /** Send one camera frame (JPEG). Short timeout and no wake retries: live frames go stale. */
  frame: (image: Blob, sessionId: string, opts?: RequestOptions): Promise<ApiFrame> => {
    const form = new FormData();
    form.append("image", image, "frame.jpg");
    form.append("session_id", sessionId);
    return request("/frame", FrameResponseSchema, { method: "POST", body: form },
      { timeoutMs: 8000, wakeBudgetMs: 0, ...opts });
  },

  demoSky: (opts?: RequestOptions): Promise<ApiDemoSkyInfo> => request("/demo-sky", DemoSkyInfoSchema, {}, opts),

  demoFrameUrl: (constellation: string, index: number): string =>
    `${API_URL}/demo-sky/frame?${new URLSearchParams({ constellation, index: String(index) })}`,
};
