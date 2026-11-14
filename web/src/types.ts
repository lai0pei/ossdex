export interface Repo {
  ghr_id: number;
  full_name: string;
  description: string | null;
  language: string | null;
  topics: string[];
  stars: number | null;
  forks: number | null;
  license: string | null;
  license_kind?: string | null;
  url: string | null;
  pushed_at: string | null;
  created_at: string | null;
  has_readme: boolean;
  gain_1d: number | null; // stars gained in the last 1 day (daily); null until enough history exists
  gain_7d: number | null; // stars gained in the last 7 days (weekly)
  gain_30d?: number | null;
  // search mode only
  score?: number;
  why?: string[];
  snippet?: string | null;
  // Enriched at-a-glance fields
  homepage?: string | null;
  open_issues?: number | null;
  sparkline?: number[];
  money_signals?: string[];
  lists_count?: number;
  papers_count?: number;
  bounties?: number;
  help_wanted?: number;
}

export interface RepoPage {
  items: Repo[];
  total: number;
  mode: "list" | "search";
}

export interface Facet {
  value: string;
  count: number;
}

export interface Facets {
  languages: Facet[];
  topics: Facet[];
  licenses: Facet[];
  lists?: Facet[];
  money?: Facet[];
}

export interface StarPoint {
  day: string;
  stars: number | null;
  forks: number | null;
}

export interface RepoDetail extends Repo {
  homepage: string | null;
  open_issues: number | null;
  readme_excerpt: string | null; // first ~1,500 characters; the full README is on GitHub
  readme_truncated: boolean;
  readme_url: string;
  github_url: string;
  history: StarPoint[];
  lists?: { list: string; section: string | null; url: string | null }[];
  papers?: { arxiv_id: string; title: string | null; url: string }[];
  money?: { signals: string[]; funding: { platform: string | null; url: string | null }[] } | null;
  demand?: {
    help_wanted: number;
    bounties: number;
    fetched_at: string | null;
    top_issues: { number: number; title: string; url: string; reactions: number; comments: number; labels: string[] }[];
  } | null;
}

export interface Status {
  db_path: string;
  repos: number;
  enriched: number; // repos with a README stored
  history_days: number; // days of star snapshots collected so far
  min_stars: string | null;
  require_license: boolean; // false: unlicensed repos are collected too
  as_of: string | null;
}

export interface PackageManager {
  id: string;
  name: string;
  install_template: string;
  path: string;
}

export interface CliTool {
  id: string;
  description: string;
  path: string;
}

export interface DetectedPaidProduct {
  catalog_id: string;
  name: string;
  category: string;
  reason: string;
  known_repos: string[];
}

export interface InferredHabit {
  habit: string;
  label: string;
  evidence: string;
}


export interface AlternativeCandidate {
  full_name: string;
  stars: number | null;
  forks: number | null;
  language: string | null;
  license: string | null;
  license_kind: string | null;
  description: string | null;
  homepage: string | null;
  gain_1d?: number | null;
  gain_7d: number | null;
  form_factor: string;
  os_compatible: boolean;
  os_evidence: string[];
  fit_score: number;
  fit_badge: string;
  habit_reasons: string[];
  workflow_synergies: string[];
  tailored_install_command: string | null;
  tradeoffs: string;
}

export interface AlternativesResponse {
  paid_product: string;
  category: string;
  target_os: string;
  user_habits: string[];
  installed_software: string[];
  alternatives_count: number;
  alternatives: AlternativeCandidate[];
  articulation_guide: {
    best_overall_pick: string | null;
    best_cli_pick: string | null;
    best_gui_pick: string | null;
    summary: string;
  };
  as_of: string;
}
