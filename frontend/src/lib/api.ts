import axios, { AxiosError } from "axios";

import type { TokenPair } from "@/types/api";

/** Base URL: "" in dev (Vite proxies /api to Django) or an absolute origin in prod. */
export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";

export class ApiError extends Error {
  status: number;
  /** DRF detail payload: string, field-error object, or list. */
  detail: unknown;

  constructor(status: number, message: string, detail?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

/** Extract the most useful message from a DRF error body. */
export function apiErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    const d = error.detail;
    if (typeof d === "string") return d;
    if (d && typeof d === "object") {
      const parts: string[] = [];
      for (const [field, value] of Object.entries(d as Record<string, unknown>)) {
        const text = Array.isArray(value) ? value.join(" ") : String(value);
        parts.push(field === "detail" || field === "non_field_errors" ? text : `${field}: ${text}`);
      }
      if (parts.length > 0) return parts.join(" · ");
    }
    if (error.message) return error.message;
  }
  if (axios.isAxiosError(error)) return error.message;
  return "Something went wrong.";
}

/* ---------------------------------- tokens --------------------------------- */

const STORAGE_KEY = "mf.tokens";

type StoredTokens = { access: string; refresh: string };

function loadTokens(): StoredTokens | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<StoredTokens>;
    return parsed.access && parsed.refresh ? (parsed as StoredTokens) : null;
  } catch {
    return null;
  }
}

function saveTokens(tokens: StoredTokens | null): void {
  try {
    if (tokens) localStorage.setItem(STORAGE_KEY, JSON.stringify(tokens));
    else localStorage.removeItem(STORAGE_KEY);
  } catch {
    // Storage unavailable (private mode etc.): session just won't persist.
  }
}

export function getTokens(): StoredTokens | null {
  return loadTokens();
}

export function setTokens(tokens: TokenPair | null): void {
  saveTokens(tokens);
}

/** Subscribers notified whenever the stored token pair changes (or is cleared). */
type TokensListener = (tokens: StoredTokens | null) => void;
const tokensListeners = new Set<TokensListener>();

export function subscribeToTokens(listener: TokensListener): () => void {
  tokensListeners.add(listener);
  return () => tokensListeners.delete(listener);
}

function storeAndPublish(tokens: TokenPair | null): void {
  saveTokens(tokens);
  for (const listener of tokensListeners) listener(tokens);
}

/* --------------------------------- client ---------------------------------- */

export const api = axios.create({
  baseURL: `${API_BASE_URL}/api/v1`,
  headers: { "Content-Type": "application/json" },
});

api.interceptors.request.use((config) => {
  const tokens = loadTokens();
  if (tokens?.access) config.headers.Authorization = `Bearer ${tokens.access}`;
  return config;
});

/* ------------------------------ auth endpoints ----------------------------- */

export async function login(username: string, password: string): Promise<TokenPair> {
  const { data } = await api.post<TokenPair>("/auth/login/", { username, password });
  storeAndPublish(data);
  return data;
}

export async function register(input: {
  username: string;
  email: string;
  password: string;
  first_name?: string;
  last_name?: string;
}): Promise<unknown> {
  return (await api.post("/auth/register/", input)).data;
}

export async function logout(): Promise<void> {
  const tokens = loadTokens();
  storeAndPublish(null);
  if (tokens) {
    // Revocation is best-effort: clear local state even if the network fails.
    try {
      await api.post("/auth/logout/", { refresh: tokens.refresh });
    } catch {
      // Already revoked or offline; nothing to do.
    }
  }
}

/* ----------------------------- refresh handling ---------------------------- */

let refreshInFlight: Promise<string | null> | null = null;

/** Exchange the refresh token for a new pair; resolves null when unrecoverable. */
function requestRefresh(refresh: string): Promise<string | null> {
  return axios
    .post<TokenPair>(`${API_BASE_URL}/api/v1/auth/refresh/`, { refresh })
    .then(({ data }) => {
      storeAndPublish(data);
      return data.access;
    })
    .catch(() => {
      storeAndPublish(null);
      return null;
    });
}

/** Single-flight refresh: concurrent 401s share one rotation request. */
function refreshAccessToken(): Promise<string | null> {
  const tokens = loadTokens();
  if (!tokens?.refresh) return Promise.resolve(null);
  refreshInFlight ??= requestRefresh(tokens.refresh).finally(() => {
    refreshInFlight = null;
  });
  return refreshInFlight;
}

api.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const original = error.config as
      | (NonNullable<AxiosError["config"]> & { _retried?: boolean })
      | undefined;

    const status = error.response?.status;
    const url = original?.url ?? "";
    const isAuthCall = url.startsWith("/auth/");

    if (
      status === 401 &&
      original &&
      !original._retried &&
      !isAuthCall // never rotate on login/refresh/logout itself
    ) {
      original._retried = true;
      const access = await refreshAccessToken();
      if (access) {
        original.headers.Authorization = `Bearer ${access}`;
        return api.request(original);
      }
    }

    const response = error.response;
    const detail = response?.data as unknown;
    const message =
      typeof detail === "object" && detail !== null && "detail" in detail
        ? String((detail as { detail: unknown }).detail)
        : typeof detail === "string"
          ? detail
          : (response?.statusText ?? error.message);

    return Promise.reject(new ApiError(response?.status ?? 0, message, detail));
  },
);

/* ------------------------------ typed helpers ------------------------------ */

/** GET a list endpoint, unwrapping DRF pagination and following next links. */
export async function listAll<T>(path: string, params?: Record<string, unknown>): Promise<T[]> {
  const acc: T[] = [];
  let url: string | undefined = path;
  let first = true;
  while (url) {
    const { data } = await api.get(url, first ? { params } : undefined);
    const page = data as { results: T[]; next: string | null };
    acc.push(...page.results);
    if (!page.next) break;
    // next is an absolute URL; convert to a client-relative path.
    url = page.next.startsWith(API_BASE_URL) ? page.next.slice(API_BASE_URL.length) : page.next;
    first = false;
  }
  return acc;
}

export async function getOne<T>(path: string): Promise<T> {
  return (await api.get<T>(path)).data;
}

export async function post<T>(path: string, body?: unknown): Promise<T> {
  return (await api.post<T>(path, body ?? {})).data;
}
