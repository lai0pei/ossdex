import { useCallback, useEffect, useState } from "react";

export type ViewMode = "cards" | "alternatives";

/** All list filters live in the URL so a view can be bookmarked. */
export interface ListState {
  q: string;
  sort: string;
  page: number;
  view: ViewMode;
  languages: string[];
  topics: string[];
  licenses: string[];
  license_kinds: string[];
  names: string[];
  money: string[]; // business-model hints: hosted_cloud, enterprise, pricing, support_consulting, sponsors
  in_lists: string[]; // Awesome lists (owner/repo) the repo must be in
  min_stars: string;
  max_stars: string;
  min_forks: string;
  max_forks: string;
  created_after: string;
  pushed_after: string;
  pushed_before: string;
  with_readme: boolean;
  has_bounties: boolean; // open issues labelled bounty (needs `ossdex demand`)
  mentions_paper: boolean; // README links to an arXiv paper
  licensed_only: boolean; // only offered when unlicensed repos are collected
  min_gain: string;
  gain_days: string; // "1" (daily) or "7" (weekly): the window min_gain is measured over
  repo: string; // repo open in the drawer
}

export const DEFAULTS: ListState = {
  q: "",
  sort: "",
  page: 1,
  view: "cards",
  languages: [],
  topics: [],
  licenses: [],
  license_kinds: [],
  names: [],
  in_lists: [],
  money: [],
  min_stars: "",
  max_stars: "",
  min_forks: "",
  max_forks: "",
  created_after: "",
  pushed_after: "",
  pushed_before: "",
  with_readme: false,
  mentions_paper: false,
  has_bounties: false,
  licensed_only: false,
  min_gain: "",
  gain_days: "1",
  repo: "",
};

const LISTS = ["languages", "topics", "licenses", "license_kinds", "names", "in_lists", "money"] as const;
const BOOLS = ["with_readme", "licensed_only", "mentions_paper", "has_bounties"] as const;

export function parse(search: string): ListState {
  const p = new URLSearchParams(search);
  const s: ListState = { ...DEFAULTS };
  for (const k of Object.keys(DEFAULTS) as (keyof ListState)[]) {
    if ((LISTS as readonly string[]).includes(k)) {
      (s as unknown as Record<string, string[]>)[k] = p.getAll(k);
    } else if ((BOOLS as readonly string[]).includes(k)) {
      if (p.has(k)) (s as unknown as Record<string, boolean>)[k] = p.get(k) === "1";
    } else if (k === "page") {
      s.page = Math.max(1, Number(p.get("page")) || 1);
    } else if (k === "view") {
      const v = p.get("view");
      if (v === "cards" || v === "alternatives") {
        s.view = v;
      }
    } else if (p.has(k)) {
      (s as unknown as Record<string, string>)[k] = p.get(k) ?? "";
    }
  }
  return s;
}

/** Query string for the page URL (`withUi`) or for the API (without `repo`/`page`/`view`). */
export function serialize(s: ListState, withUi: boolean): URLSearchParams {
  const p = new URLSearchParams();
  for (const k of Object.keys(DEFAULTS) as (keyof ListState)[]) {
    if (!withUi && (k === "repo" || k === "page" || k === "view")) continue;
    const v = s[k];
    if (Array.isArray(v)) v.forEach((x) => p.append(k, x));
    else if (typeof v === "boolean") {
      if (v !== DEFAULTS[k]) p.set(k, v ? "1" : "0");
    } else if (typeof v === "number") {
      if (v !== DEFAULTS[k]) p.set(k, String(v));
    } else if (v !== "" && v !== DEFAULTS[k]) p.set(k, v);
  }
  // the API wants real booleans
  if (!withUi) {
    for (const b of BOOLS) if (p.has(b)) p.set(b, p.get(b) === "1" ? "true" : "false");
  }
  return p;
}

export function useListState(): [ListState, (patch: Partial<ListState>, resetPage?: boolean) => void] {
  const [state, setState] = useState<ListState>(() => parse(window.location.search));

  useEffect(() => {
    const onPop = () => setState(parse(window.location.search));
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  const update = useCallback((patch: Partial<ListState>, resetPage = true) => {
    setState((prev) => {
      const next = { ...prev, ...patch };
      if (resetPage && !("page" in patch)) next.page = 1;
      const qs = serialize(next, true).toString();
      window.history.replaceState(null, "", qs ? `?${qs}` : window.location.pathname);
      return next;
    });
  }, []);

  return [state, update];
}
