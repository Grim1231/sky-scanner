import { apiFetch } from "@/lib/api-client";
import type {
  RegisterRequest,
  LoginRequest,
  TokenResponse,
} from "@/lib/types";

export async function register(req: RegisterRequest): Promise<TokenResponse> {
  return apiFetch<TokenResponse>("/auth/register", {
    method: "POST",
    body: JSON.stringify(req),
  });
}

export async function login(req: LoginRequest): Promise<TokenResponse> {
  return apiFetch<TokenResponse>("/auth/login", {
    method: "POST",
    body: JSON.stringify(req),
  });
}

export async function refreshToken(
  refresh_token: string
): Promise<TokenResponse> {
  return apiFetch<TokenResponse>("/auth/refresh", {
    method: "POST",
    body: JSON.stringify({ refresh_token }),
  });
}
