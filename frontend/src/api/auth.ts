import { getJson, sendJson } from "./client";

export type AuthUser = {
  id: number;
  email: string;
  created_at?: string;
  last_login_at?: string | null;
};

export type AuthResponse = {
  user: AuthUser;
  token: string;
  token_type: string;
  expires_at: string;
};

export type AuthPayload = {
  email: string;
  password: string;
};

export function login(payload: AuthPayload): Promise<AuthResponse> {
  return sendJson<AuthResponse>("/api/auth/login", payload);
}

export function register(payload: AuthPayload): Promise<AuthResponse> {
  return sendJson<AuthResponse>("/api/auth/register", payload);
}

export function getCurrentUser(): Promise<AuthUser> {
  return getJson<AuthUser>("/api/auth/me");
}

export function logout(): Promise<{ ok: boolean }> {
  return sendJson<{ ok: boolean }>("/api/auth/logout", {});
}
