import { useEffect, useState } from "react";
import type { Repo, RepoPage } from "./types";
import type { ListState } from "./state";
import { agoWithDate, langColor } from "./ago";
import {
  IconAward,
  IconBookmark,
  IconCheck,
  IconChevronLeft,
  IconChevronRight,
  IconClock,
  IconExternal,
  IconFileText,
  IconFork,
  IconRepo,
  IconSearch,
  IconShieldCheck,
  IconSparkles,
  IconStar,
  IconTrendingUp,
} from "./icons";

export const fmtStars = (n: number | null | undefined) =>
  n == null ? "–" : n >= 1000 ? `${(n / 1000).toFixed(n >= 10000 ? 0 : 1)}k` : String(n);

function highlight(text: string, q: string) {
  const terms = q.toLowerCase().match(/\w{2,}/g);
  if (!terms) return text;
  const re = new RegExp(`(${[...new Set(terms)].map((t) => t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|")})`, "gi");
  return text.split(re).map((part, i) =>
    i % 2 === 1 ? <mark key={i}>{part}</mark> : part,
  );
}

function gainLabel(r: Repo, days: string, sort?: string): string {
  // If explicitly sorting by weekly, show weekly (7d)
  if (sort === "gain_7d") {
    const g = r.gain_7d;
    if (g != null && g !== 0) return `${g > 0 ? "+" : ""}${fmtStars(g)} / 7d`;
    return "";
  }
  // If explicitly sorting by daily, show daily (1d)
  if (sort === "gain_1d") {
    const g = r.gain_1d;
    if (g != null && g !== 0) return `${g > 0 ? "+" : ""}${fmtStars(g)} / 1d`;
    return "";
  }
  // If days is "7", show 7d (fallback to 1d)
  if (days === "7") {
    const g = r.gain_7d ?? r.gain_1d;
    if (g != null && g !== 0) {
      const windowStr = r.gain_7d != null ? "7d" : "1d";
      return `${g > 0 ? "+" : ""}${fmtStars(g)} / ${windowStr}`;
    }
    return "";
  }
  // Otherwise default to 1d (daily), fallback to 7d
  const g = r.gain_1d ?? r.gain_7d;
  if (g != null && g !== 0) {
    const windowStr = r.gain_1d != null ? "1d" : "7d";
    return `${g > 0 ? "+" : ""}${fmtStars(g)} / ${windowStr}`;
  }
  return "";
}

export function OwnerAvatar({ owner, size = 36 }: { owner: string; size?: number }) {
  const [failed, setFailed] = useState(false);
  if (!owner || failed) {
    return (
      <span className="avatar-fallback" style={{ width: size, height: size }}>
        <IconRepo size={Math.round(size * 0.52)} />
      </span>
    );
  }
  return (
    <img
      className="owner-avatar"
      src={`https://github.com/${encodeURIComponent(owner)}.png?size=72`}
      alt=""
      width={size}
      height={size}
      loading="lazy"
      onError={() => setFailed(true)}
    />
  );
}

export function MiniSparkline({
  points,
  width = 68,
  height = 20,
  stroke,
}: {
  points?: number[];
  width?: number;
  height?: number;
  stroke?: string;
}) {
  if (!points || points.length < 2) return null;
  const min = Math.min(...points);
  const max = Math.max(...points);
  const range = max - min || 1;
  const padding = 2;
  const usableH = height - padding * 2;
  const usableW = width - padding * 2;
  const step = usableW / (points.length - 1);

  const coords = points.map((p, i) => {
    const x = padding + i * step;
    const y = padding + usableH - ((p - min) / range) * usableH;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });

  const lineD = `M ${coords.join(" L ")}`;
  const areaD = `${lineD} L ${padding + usableW},${height} L ${padding},${height} Z`;
  const isUp = points[points.length - 1] >= points[0];
  const strokeColor = stroke || (isUp ? "var(--gain-text)" : "var(--muted)");

  return (
    <svg
      className="mini-sparkline"
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      aria-hidden="true"
    >
      <path d={areaD} className="mini-sparkline-area" />
      <path
        d={lineD}
        className="mini-sparkline-line"
        stroke={strokeColor}
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
        fill="none"
      />
    </svg>
  );
}

export default function RepoList(props: {
  data: RepoPage | undefined;
  loading: boolean;
  error: Error | null;
  state: ListState;
  pageSize: number;
  onChange: (p: Partial<ListState>, resetPage?: boolean) => void;
  savedRepos?: string[];
  onToggleSaved?: (fullName: string) => void;
  cardDensity?: "comfortable" | "compact";
}) {
  const {
    data,
    state: s,
    onChange,
    savedRepos = [],
    onToggleSaved,
    cardDensity = "comfortable",
  } = props;
  const [focusIdx, setFocusIdx] = useState<number>(-1);

  useEffect(() => {
    setFocusIdx(-1);
  }, [data?.items]);

  // Keyboard navigation for cards: j/k moves focus, Enter opens inspector
  useEffect(() => {
    const items = data?.items ?? [];
    if (items.length === 0) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      const el = e.target as HTMLElement | null;
      const tag = el?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || el?.isContentEditable) return;
      if (e.key === "j" || e.key === "ArrowDown") {
        e.preventDefault();
        setFocusIdx((i) => {
          const next = Math.min(items.length - 1, i + 1);
          if (s.repo) onChange({ repo: items[next].full_name }, false);
          return next;
        });
      } else if (e.key === "k" || e.key === "ArrowUp") {
        e.preventDefault();
        setFocusIdx((i) => {
          const next = Math.max(0, i <= 0 ? 0 : i - 1);
          if (s.repo) onChange({ repo: items[next].full_name }, false);
          return next;
        });
      } else if (e.key === "Enter" && focusIdx >= 0 && focusIdx < items.length) {
        e.preventDefault();
        onChange({ repo: items[focusIdx].full_name }, false);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [data?.items, focusIdx, onChange, s.repo]);

  const searching = s.q.trim() !== "";
  const pages = data ? Math.max(1, Math.ceil(data.total / props.pageSize)) : 1;

  return (
    <section className="list">
      {props.error && <div className="error-banner">Could not load repositories: {props.error.message}</div>}

      {(
        <ul className={`repos profile-grid ${cardDensity === "compact" ? "compact-list" : ""}`}>
          {props.loading && !data && Array.from({ length: 8 }).map((_, idx) => (
            <li key={idx} className="repo-card skeleton-card" aria-hidden="true">
              <div className="skeleton-row">
                <div className="skeleton-line w-40" />
                <div className="skeleton-line w-15" />
              </div>
              <div className="skeleton-line w-85" />
              <div className="skeleton-line w-70" />
              <div className="skeleton-row">
                <div className="skeleton-line w-30" />
                <div className="skeleton-line w-20" />
              </div>
            </li>
          ))}

          {data?.items.map((r, idx) => {
            const [owner, repoName] = r.full_name.includes("/")
              ? r.full_name.split("/", 2)
              : ["", r.full_name];
            const gain = gainLabel(r, s.gain_days, s.sort);
            const ghUrl = r.url || `https://github.com/${r.full_name}`;
            const isSelected = s.repo.toLowerCase() === r.full_name.toLowerCase() || focusIdx === idx;
            const isSaved = savedRepos.includes(r.full_name);
            const hasSignals = (r.money_signals && r.money_signals.length > 0) ||
                               (r.lists_count != null && r.lists_count > 0) ||
                               (r.papers_count != null && r.papers_count > 0);

            return (
              <li
                key={r.ghr_id}
                className={`repo-card profile-card clickable ${props.loading ? "stale" : ""} ${isSelected ? "active" : ""}`}
                onClick={() => onChange({ repo: r.full_name }, false)}
              >
                <div className="profile-head">
                  <OwnerAvatar owner={owner} size={36} />
                  <div className="profile-identity">
                    {owner && <span className="repo-owner">@{owner}</span>}
                    <button
                      className="repo-name"
                      onClick={(e) => {
                        e.stopPropagation();
                        onChange({ repo: r.full_name }, false);
                      }}
                    >
                      <span className="repo-slug">{repoName}</span>
                    </button>
                  </div>

                  <div className="card-head-metrics">
                    {r.sparkline && r.sparkline.length >= 2 && (
                      <div className="card-spark-wrap desktop-sparkline" title={`Recent stars velocity: ${r.sparkline[0]} → ${r.sparkline[r.sparkline.length - 1]}`}>
                        <MiniSparkline points={r.sparkline} width={64} height={20} />
                      </div>
                    )}
                    <div className="card-head-actions">
                      {onToggleSaved && (
                        <button
                          type="button"
                          className={`gh-ext-link bookmark-btn ${isSaved ? "saved" : ""}`}
                          title={isSaved ? "Remove from saved" : "Save repository"}
                          aria-label={isSaved ? `Unsave ${r.full_name}` : `Save ${r.full_name}`}
                          onClick={(e) => {
                            e.stopPropagation();
                            onToggleSaved(r.full_name);
                          }}
                        >
                          <IconBookmark size={15} filled={isSaved} />
                        </button>
                      )}
                      <a
                        className="gh-ext-link"
                        href={ghUrl}
                        target="_blank"
                        rel="noreferrer"
                        title="Open on GitHub"
                        aria-label={`Open ${r.full_name} on GitHub`}
                        onClick={(e) => e.stopPropagation()}
                      >
                        <IconExternal size={15} />
                      </a>
                    </div>
                  </div>
                </div>

                <div className="profile-body">
                  {/* Dedicated language and license meta row for clean mobile & desktop scanning */}
                  {(r.language || r.license) && (
                    <div className="card-meta-row">
                      {r.language && (
                        <button
                          className="chip lang-chip"
                          onClick={(e) => {
                            e.stopPropagation();
                            onChange({ languages: [r.language!.toLowerCase()] });
                          }}
                        >
                          <span className="lang-dot" style={{ backgroundColor: langColor(r.language) }} />
                          {r.language}
                        </button>
                      )}
                      {r.license && (
                        <button
                          type="button"
                          className={`chip license-chip kind-${r.license_kind || "other"} clickable`}
                          title={`${r.license} (${r.license_kind || "unclassified"}) — click to filter`}
                          onClick={(e) => {
                            e.stopPropagation();
                            if (r.license_kind) {
                              onChange({ license_kinds: [r.license_kind] });
                            } else if (r.license) {
                              onChange({ licenses: [r.license] });
                            }
                          }}
                        >
                          {r.license_kind === "permissive" ? <IconShieldCheck size={10} /> : <IconCheck size={10} />}
                          <span>{r.license}</span>
                        </button>
                      )}
                    </div>
                  )}

                  {r.description && (
                    <p className="desc line-clamp-2">{highlight(r.description, s.q)}</p>
                  )}

                  {r.snippet && (
                    <p className="snippet line-clamp-2">{highlight(r.snippet, s.q)}</p>
                  )}

                  {/* At-a-Glance Commercial & Velocity Signals */}
                  {hasSignals && (
                    <div className="card-signals-row">
                      {r.money_signals?.slice(0, 2).map((m) => (
                        <span
                          key={m}
                          className="signal-badge money"
                          title={`Business signal: ${m.replace("_", " ")}`}
                          onClick={(e) => {
                            e.stopPropagation();
                            onChange({ money: [...new Set([...s.money, m])] });
                          }}
                        >
                          <IconSparkles size={11} />
                          <span>{m.replace("_", " ")}</span>
                        </span>
                      ))}
                      {r.lists_count != null && r.lists_count > 0 && (
                        <span className="signal-badge list" title={`Featured in ${r.lists_count} curated Awesome lists`}>
                          <IconAward size={11} />
                          <span>{r.lists_count} {r.lists_count === 1 ? "list" : "lists"}</span>
                        </span>
                      )}
                      {r.papers_count != null && r.papers_count > 0 && (
                        <span className="signal-badge paper" title={`Cites ${r.papers_count} research paper(s)`}>
                          <IconFileText size={11} />
                          <span>{r.papers_count} {r.papers_count === 1 ? "paper" : "papers"}</span>
                        </span>
                      )}
                    </div>
                  )}

                  {r.topics.length > 0 && (
                    <div className="chips profile-topics">
                      {r.topics.slice(0, 4).map((t) => (
                        <button
                          key={t}
                          className="chip topic"
                          onClick={(e) => {
                            e.stopPropagation();
                            onChange({ topics: [...new Set([...s.topics, t])] });
                          }}
                        >
                          #{t}
                        </button>
                      ))}
                    </div>
                  )}
                </div>

                <div className="profile-foot">
                  <div className="profile-metrics">
                    <span className="stat-pill" title={`${r.stars?.toLocaleString() ?? 0} stars`}>
                      <span className="star-icon">
                        <IconStar size={12} filled />
                      </span>
                      {fmtStars(r.stars)}
                    </span>
                    {r.forks != null && r.forks > 0 && (
                      <span className="meta-item" title={`${r.forks.toLocaleString()} forks`}>
                        <IconFork size={12} />
                        <span>{fmtStars(r.forks)}</span>
                      </span>
                    )}
                    {!r.license && (
                      <span className="meta-item no-lic" title="No license: all rights reserved, not open source">
                        no license
                      </span>
                    )}
                  </div>

                  <div className="profile-status">
                    {r.sparkline && r.sparkline.length >= 2 && (
                      <div className="card-spark-wrap mobile-sparkline" title={`Recent stars velocity: ${r.sparkline[0]} → ${r.sparkline[r.sparkline.length - 1]}`}>
                        <MiniSparkline points={r.sparkline} width={56} height={18} />
                      </div>
                    )}
                    {gain ? (
                      <span
                        className="gain-badge"
                        title={gain.includes("/ 7d") ? "Stars gained over 7 days (weekly)" : "Stars gained over 1 day (daily)"}
                      >
                        <IconTrendingUp size={12} />
                        <span>{gain}</span>
                      </span>
                    ) : r.pushed_at ? (
                      <span className="meta-item" title={r.pushed_at.slice(0, 10)}>
                        <IconClock size={12} />
                        <span>{agoWithDate(r.pushed_at)}</span>
                      </span>
                    ) : null}
                  </div>
                </div>
              </li>
            );
          })}

          {data && data.items.length === 0 && (
            <li className="empty">
              <div className="empty-icon">
                <IconSearch size={24} />
              </div>
              <div>No repositories match your filters{searching ? " or search query" : ""}.</div>
            </li>
          )}
        </ul>
      )}

      {/* Pagination (for cards view) */}
      {data && pages > 1 && (
        <nav className="pager" aria-label="Pagination">
          <button className="btn pager-btn prev" disabled={s.page <= 1} onClick={() => onChange({ page: s.page - 1 }, false)}>
            <IconChevronLeft size={14} />
            <span>Previous</span>
          </button>
          <span className="pager-info">Page {s.page} of {pages}</span>
          <button className="btn pager-btn next" disabled={s.page >= pages} onClick={() => onChange({ page: s.page + 1 }, false)}>
            <span>Next</span>
            <IconChevronRight size={14} />
          </button>
        </nav>
      )}
    </section>
  );
}
