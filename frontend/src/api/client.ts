export class ApiError extends Error {
  status: number;
  body: string;

  constructor(message: string, status: number, body: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.body = body;
  }
}

const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL || "").trim().replace(/\/+$/, "");

export function apiUrl(path: string): string {
  if (/^https?:\/\//i.test(path)) return path;
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  return apiBaseUrl ? `${apiBaseUrl}${normalizedPath}` : normalizedPath;
}

export async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(apiUrl(path), { credentials: "include" });
  if (!response.ok) {
    const body = await response.text();
    throw new ApiError(`Request failed: ${response.status}`, response.status, body);
  }
  return response.json() as Promise<T>;
}

export async function sendJson<T>(path: string, payload: unknown): Promise<T> {
  const response = await fetch(apiUrl(path), {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const body = await response.text();
    throw new ApiError(`Request failed: ${response.status}`, response.status, body);
  }
  return response.json() as Promise<T>;
}

export async function patchJson<T>(path: string, payload: unknown): Promise<T> {
  const response = await fetch(apiUrl(path), {
    method: "PATCH",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const body = await response.text();
    throw new ApiError(`Request failed: ${response.status}`, response.status, body);
  }
  return response.json() as Promise<T>;
}
