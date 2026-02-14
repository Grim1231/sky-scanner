import { apiFetch } from "@/lib/api-client";
import type {
  UserResponse,
  UserPreferenceResponse,
  UpdatePreferenceRequest,
  SearchHistoryResponse,
} from "@/lib/types";

export async function getMe(): Promise<UserResponse> {
  return apiFetch<UserResponse>("/users/me");
}

export async function getPreferences(): Promise<UserPreferenceResponse | null> {
  return apiFetch<UserPreferenceResponse | null>("/users/me/preferences");
}

export async function updatePreferences(
  req: UpdatePreferenceRequest
): Promise<UserPreferenceResponse> {
  return apiFetch<UserPreferenceResponse>("/users/me/preferences", {
    method: "PUT",
    body: JSON.stringify(req),
  });
}

export async function getHistory(
  page: number = 1,
  pageSize: number = 20
): Promise<SearchHistoryResponse> {
  const sp = new URLSearchParams({
    page: String(page),
    page_size: String(pageSize),
  });
  return apiFetch<SearchHistoryResponse>(`/users/me/history?${sp}`);
}
