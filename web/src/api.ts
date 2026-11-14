import type {
  AlternativesResponse,
  Facets,
  Repo,
  RepoDetail,
  RepoPage,
  Status,
} from "./types";

async function getJson<T>(url: string, signal?: AbortSignal): Promise<T> {
  const r = await fetch(url, { signal });
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
  return r.json() as Promise<T>;
}

export const fetchStatus = () => getJson<Status>("/api/status");
export const fetchRepos = (params: URLSearchParams, signal?: AbortSignal) =>
  getJson<RepoPage>(`/api/repos?${params}`, signal);
export const fetchFacets = (params: URLSearchParams, signal?: AbortSignal) =>
  getJson<Facets>(`/api/facets?${params}`, signal);
export const fetchRepo = (fullName: string) => getJson<RepoDetail>(`/api/repos/${fullName}`);
export const fetchSimilar = (fullName: string) =>
  getJson<{ repos: Repo[]; note?: string }>(`/api/repos/${fullName}/similar`);
export const fetchAlternatives = (params: URLSearchParams, signal?: AbortSignal) =>
  getJson<AlternativesResponse>(`/api/alternatives?${params}`, signal);
