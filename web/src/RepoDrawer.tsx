import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import ReactMarkdown from "react-markdown";
import rehypeSanitize from "rehype-sanitize";
import { fetchRepo, fetchSimilar } from "./api";
import { fmtStars, OwnerAvatar } from "./RepoList";
import type { StarPoint } from "./types";
import { agoWithDate, langColor } from "./ago";
import { analyzeSingleRepo } from "./ideaAnalysis";
import {
  SINGLE_REPO_CATEGORIES,
  SINGLE_REPO_PROMPTS,
} from "./promptLibrary";
import {
  IconActivity,
  IconAward,
  IconBookmark,
  IconBookOpen,
  IconCheck,
  IconChevronLeft,
  IconChevronRight,
  IconClock,
  IconCode,
  IconCopy,
  IconExternal,
  IconFileText,
  IconFork,
  IconGitHub,
  IconGlobe,
  IconMaximize,
  IconMinimize,
  IconShieldCheck,
  IconSparkles,
  IconStar,
  IconTrendingUp,
  IconX,
} from "./icons";

const KIND_NOTES: Record<string, string> = {
  permissive: "Permissive (MIT, Apache 2.0, BSD): Safe to use in closed, proprietary, and commercial SaaS products without open-sourcing your code. Keep the copyright notice.",
  weak_copyleft: "Weak Copyleft (LGPL, MPL): You can use it in commercial products. Any direct modifications to this library's source files must be shared, but your surrounding application can stay closed.",
  copyleft: "Copyleft (GPL): If you distribute applications built on this project, your entire source code must be licensed under the GPL.",
  network_copyleft: "Network Copyleft (AGPL): Users interacting with your service over a network/SaaS are legally entitled to receive the complete source code under AGPL.",
  other: "Custom / Source-Available: May include non-compete clauses, revenue limits (e.g. BSL, SSPL), or custom restrictions. Review the LICENSE file carefully before commercial adoption.",
  none: "All Rights Reserved: Not open source. You do not have permission to copy, modify, distribute, or run this code commercially without written permission.",
};

function TrendChart({ points, metric }: { points: StarPoint[]; metric: "stars" | "forks" }) {
  const pts = points.filter((p) => (metric === "stars" ? p.stars != null : p.forks != null));
  if (pts.length < 2) return null;
  const w = 560;
  const h = 76;
  const vals = pts.map((p) => (metric === "stars" ? (p.stars as number) : (p.forks as number)));
  const lo = Math.min(...vals);
  const hi = Math.max(...vals);
  const x = (i: number) => (i / (pts.length - 1)) * (w - 16) + 8;
  const y = (v: number) => (hi === lo ? h / 2 : h - 14 - ((v - lo) / (hi - lo || 1)) * (h - 26));
  const linePath = pts.map((_, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(vals[i]).toFixed(1)}`).join(" ");
  const areaPath = `${linePath} L${x(pts.length - 1).toFixed(1)},${h} L${x(0).toFixed(1)},${h} Z`;

  return (
    <div className="star-chart-wrap">
      <div className="chart-y-axis">
        <span>{fmtStars(hi)}</span>
        <span>{fmtStars(lo)}</span>
      </div>
      <svg className="star-chart" viewBox={`0 0 ${w} ${h}`} role="img" aria-label={`${metric} history from ${lo} to ${hi}`}>
        <defs>
          <linearGradient id="trendGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--accent)" stopOpacity="0.28" />
            <stop offset="100%" stopColor="var(--accent)" stopOpacity="0.0" />
          </linearGradient>
        </defs>
        <path className="chart-area" d={areaPath} fill="url(#trendGrad)" />
        <path
          className="chart-line"
          pathLength={1}
          d={linePath}
          fill="none"
          stroke="var(--accent)"
          strokeWidth="2.2"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        {pts.map((p, i) => (
          <circle key={p.day} className="chart-dot" cx={x(i)} cy={y(vals[i])} r="3" fill="var(--accent)">
            <title>{`${p.day}: ${vals[i].toLocaleString()} ${metric}`}</title>
          </circle>
        ))}
      </svg>
      <div className="chart-x-axis">
        <span>{pts[0].day}</span>
        <span>{pts[pts.length - 1].day}</span>
      </div>
    </div>
  );
}

export default function RepoDrawer({
  name,
  onClose,
  onOpenRepo,
  onPrevRepo,
  onNextRepo,
  hasPrev = false,
  hasNext = false,
  onFilterTopic,
  onFilterList,
  onFilterMoney,
  onFilterLanguage,
  isSaved,
  onToggleSaved,
}: {
  name: string;
  onClose: () => void;
  onOpenRepo?: (repoName: string) => void;
  onPrevRepo?: () => void;
  onNextRepo?: () => void;
  hasPrev?: boolean;
  hasNext?: boolean;
  onFilterTopic?: (topic: string) => void;
  onFilterList?: (list: string) => void;
  onFilterMoney?: (hint: string) => void;
  onFilterLanguage?: (lang: string) => void;
  isSaved?: boolean;
  onToggleSaved?: (repoName: string) => void;
}) {
  const { data: r, error, isLoading } = useQuery({ queryKey: ["repo", name], queryFn: () => fetchRepo(name) });
  const similar = useQuery({ queryKey: ["repo", name, "similar"], queryFn: () => fetchSimilar(name), staleTime: 60_000 });
  const [maximized, setMaximized] = useState(true);
  const [chartMetric, setChartMetric] = useState<"stars" | "forks">("stars");
  const [copiedSlug, setCopiedSlug] = useState(false);
  const [copiedBrief, setCopiedBrief] = useState(false);
  const [copiedTemplateId, setCopiedTemplateId] = useState<string | null>(null);
  const [selectedPromptId, setSelectedPromptId] = useState<string>("idea-articulator");
  const [promptCategory, setPromptCategory] = useState<string>("All");
  const [showPromptPreview, setShowPromptPreview] = useState<boolean>(false);

  const selectedTemplate =
    SINGLE_REPO_PROMPTS.find((p) => p.id === selectedPromptId) || SINGLE_REPO_PROMPTS[0];

  const copyPromptById = (templateId: string) => {
    if (!r) return;
    const tpl = SINGLE_REPO_PROMPTS.find((p) => p.id === templateId) || selectedTemplate;
    const promptText = tpl.generate({ repo: r });
    navigator.clipboard.writeText(promptText).then(() => {
      setCopiedTemplateId(templateId);
      setCopiedBrief(true);
      setTimeout(() => {
        setCopiedTemplateId(null);
        setCopiedBrief(false);
      }, 2000);
    });
  };

  const copyMcpBrief = () => {
    copyPromptById(selectedPromptId);
  };

  useEffect(() => {
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onClose();
        return;
      }
      const tag = (e.target as HTMLElement | null)?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
      if ((e.key === "ArrowLeft" || e.key === "h") && onPrevRepo && hasPrev) {
        e.preventDefault();
        onPrevRepo();
      } else if ((e.key === "ArrowRight" || e.key === "l") && onNextRepo && hasNext) {
        e.preventDefault();
        onNextRepo();
      }
    };
    window.addEventListener("keydown", onKey);

    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = prevOverflow;
    };
  }, [hasPrev, hasNext, onClose, onNextRepo, onPrevRepo]);

  const hasStarHistory = r && (r.history.filter((p) => p.stars != null).length >= 2 || r.gain_1d != null || r.gain_7d != null);
  const [owner, repoSlug] = name.includes("/") ? name.split("/", 2) : ["", name];

  // Rewrite relative markdown image / link URLs so they point to GitHub
  const transformUri = (uri: string) => {
    if (!uri || !r) return uri;
    if (uri.startsWith("http://") || uri.startsWith("https://") || uri.startsWith("mailto:") || uri.startsWith("#")) {
      return uri;
    }
    const cleanPath = uri.replace(/^\.?\//, "");
    return `https://raw.githubusercontent.com/${r.full_name}/HEAD/${cleanPath}`;
  };

  const content = (
    <>
      <header className="modal-header">
        <div className="modal-title-wrap">
          <OwnerAvatar owner={owner} size={30} />
          <div className="modal-title-text">
            <h2>
              {owner && <span className="repo-owner">{owner}/</span>}
              <span>{repoSlug}</span>
            </h2>
            <button
              type="button"
              className="copy-slug-btn"
              title={copiedSlug ? "Copied!" : `Copy ${name}`}
              aria-label={`Copy ${name}`}
              onClick={() => {
                navigator.clipboard.writeText(name).then(() => {
                  setCopiedSlug(true);
                  setTimeout(() => setCopiedSlug(false), 1800);
                });
              }}
            >
              {copiedSlug ? <IconCheck size={12} /> : <IconCopy size={12} />}
            </button>
          </div>
          {r && (
            <div className="modal-links">
              {onToggleSaved && (
                <button
                  className={`btn-link ${isSaved ? "btn-ask-ai" : ""}`}
                  onClick={() => onToggleSaved(r.full_name)}
                  title={isSaved ? "Remove from saved" : "Save repository"}
                >
                  <IconBookmark size={13} filled={isSaved} />
                  <span>{isSaved ? "Saved" : "Save"}</span>
                </button>
              )}
              <button
                className="btn-link"
                onClick={copyMcpBrief}
                title="Copy structured product idea prompt for Claude or your MCP client"
              >
                {copiedBrief ? <IconCheck size={12} /> : <IconCopy size={12} />}
                <span>{copiedBrief ? "Brief Copied!" : "Copy MCP Brief"}</span>
              </button>
              <a className="btn-link" href={r.github_url} target="_blank" rel="noreferrer">
                <IconGitHub size={13} />
                <span>GitHub</span>
                <IconExternal size={11} />
              </a>
              {r.homepage && (
                <a className="btn-link" href={r.homepage} target="_blank" rel="noreferrer">
                  <IconGlobe size={13} />
                  <span>Website</span>
                  <IconExternal size={11} />
                </a>
              )}
            </div>
          )}
        </div>

        <div className="modal-actions">
          {onPrevRepo && (
            <button
              className="icon-btn"
              onClick={onPrevRepo}
              disabled={!hasPrev}
              title="Previous repository (h / ←)"
              aria-label="Previous repository"
            >
              <IconChevronLeft size={15} />
            </button>
          )}
          {onNextRepo && (
            <button
              className="icon-btn"
              onClick={onNextRepo}
              disabled={!hasNext}
              title="Next repository (l / →)"
              aria-label="Next repository"
            >
              <IconChevronRight size={15} />
            </button>
          )}
          <button
            className="icon-btn"
            onClick={() => setMaximized((v) => !v)}
            title={maximized ? "Compact popup" : "Maximize popup"}
            aria-label={maximized ? "Compact popup" : "Maximize popup"}
          >
            {maximized ? <IconMinimize size={15} /> : <IconMaximize size={15} />}
          </button>
          <button className="icon-btn" onClick={onClose} title="Close popup (Esc)" aria-label="Close popup">
            <IconX size={16} />
          </button>
        </div>
      </header>

      {isLoading && (
        <div className="modal-body" aria-hidden="true">
          <div className="skeleton-line w-70" />
          <div className="drawer-stats">
            {Array.from({ length: 4 }).map((_, i) => (
              <div key={i} className="stat-box">
                <div className="skeleton-line w-40" />
                <div className="skeleton-line w-70" />
              </div>
            ))}
          </div>
          <div className="skeleton-block" />
        </div>
      )}

      {error && <div className="drawer-state error">{(error as Error).message}</div>}

      {r && (
        <div className="modal-body">
          <div className="modal-overview">
            {r.description && <p className="drawer-desc">{r.description}</p>}

            {(() => {
              const forkRatio = r.stars && r.forks ? ((r.forks / r.stars) * 100).toFixed(1) : null;
              const ageYears = r.created_at
                ? ((Date.now() - new Date(r.created_at).getTime()) / (365.25 * 86400 * 1000)).toFixed(1)
                : null;
              const starsPerYear =
                ageYears && r.stars ? Math.round(r.stars / Math.max(parseFloat(ageYears), 0.5)) : null;
              const kindAdvice = r.license_kind ? KIND_NOTES[r.license_kind] : KIND_NOTES.none;

              return (
                <>
                  <div className="drawer-stats">
                    <div className="stat-box">
                      <span className="stat-label">
                        <IconStar size={12} filled className="star-icon" />
                        <span>Stars</span>
                      </span>
                      <span className="stat-value">{fmtStars(r.stars)}</span>
                      {starsPerYear && <span className="stat-sub muted small">{fmtStars(starsPerYear)}/yr</span>}
                    </div>

                    {r.forks != null && (
                      <div className="stat-box">
                        <span className="stat-label">
                          <IconFork size={12} />
                          <span>Forks</span>
                        </span>
                        <span className="stat-value">{fmtStars(r.forks)}</span>
                        {forkRatio && <span className="stat-sub muted small">{forkRatio}% of stars</span>}
                      </div>
                    )}

                    {r.language && (
                      <div
                        className={`stat-box ${onFilterLanguage ? "clickable" : ""}`}
                        onClick={() => {
                          if (onFilterLanguage && r.language) {
                            onFilterLanguage(r.language.toLowerCase());
                            onClose();
                          }
                        }}
                        title={onFilterLanguage ? `Filter by ${r.language}` : undefined}
                      >
                        <span className="stat-label">
                          <IconCode size={12} />
                          <span>Language</span>
                        </span>
                        <span className="stat-value stat-lang">
                          <span className="lang-dot" style={{ backgroundColor: langColor(r.language) }} />
                          {r.language}
                        </span>
                      </div>
                    )}

                    <div className="stat-box">
                      <span className="stat-label">
                        <IconBookOpen size={12} />
                        <span>License</span>
                      </span>
                      <span className="stat-value" title={r.license ? undefined : "All rights reserved, not open source"}>
                        {r.license ?? "None"}
                      </span>
                      <span className="stat-sub muted small">{r.license_kind?.replace("_", " ") ?? "unclassified"}</span>
                    </div>

                    {r.pushed_at && (
                      <div className="stat-box">
                        <span className="stat-label">
                          <IconClock size={12} />
                          <span>Updated</span>
                        </span>
                        <span className="stat-value" title={r.pushed_at.slice(0, 10)}>{agoWithDate(r.pushed_at)}</span>
                        {ageYears && <span className="stat-sub muted small">{ageYears} yrs old</span>}
                      </div>
                    )}

                    {r.open_issues != null && (
                      <div className="stat-box">
                        <span className="stat-label">
                          <IconActivity size={12} />
                          <span>Open Issues</span>
                        </span>
                        <span className="stat-value">{r.open_issues.toLocaleString()}</span>
                      </div>
                    )}
                  </div>

                  {/* Commercial / SaaS Guidance Callout */}
                  <div className="license-advice-box">
                    <div className="lic-advice-header">
                      <IconShieldCheck size={14} />
                      <span>Commercial & SaaS Use Guidance</span>
                    </div>
                    <p className="lic-advice-text">{kindAdvice}</p>
                  </div>

                  {/* Product Idea Brief & Strategy */}
                  <section className="product-brief-box">
                    <div className="product-brief-header">
                      <div className="product-brief-title-wrap">
                        <span className="product-brief-badge">
                          <IconSparkles size={13} />
                          <span>Product Idea Brief</span>
                        </span>
                        <span className={`product-verdict-pill level-${analyzeSingleRepo(r).licensePosture.level}`}>
                          {analyzeSingleRepo(r).licensePosture.badge}
                        </span>
                      </div>
                      <button
                        type="button"
                        className="btn-subtle small-btn"
                        onClick={copyMcpBrief}
                        title="Copy structured brief for MCP client"
                      >
                        {copiedBrief ? <IconCheck size={12} /> : <IconCopy size={12} />}
                        <span>{copiedBrief ? "Copied" : "Copy MCP Brief"}</span>
                      </button>
                    </div>

                    <p className="product-brief-summary">{analyzeSingleRepo(r).licensePosture.summary}</p>

                    <div className="product-signals-grid">
                      <div className="product-signal-item">
                        <span className="signal-item-label">Deployment Signal</span>
                        <span className="signal-item-val">{analyzeSingleRepo(r).deploymentSignal}</span>
                      </div>
                      <div className="product-signal-item">
                        <span className="signal-item-label">Velocity</span>
                        <span className="signal-item-val">{analyzeSingleRepo(r).velocitySignal}</span>
                      </div>
                      {analyzeSingleRepo(r).businessPrecedents.length > 0 && (
                        <div className="product-signal-item">
                          <span className="signal-item-label">Precedents</span>
                          <span className="signal-item-val">{analyzeSingleRepo(r).businessPrecedents.join(", ")}</span>
                        </div>
                      )}
                      {(analyzeSingleRepo(r).demandHighlight.bounties > 0 || analyzeSingleRepo(r).demandHighlight.topWish) && (
                        <div className="product-signal-item">
                          <span className="signal-item-label">Community Demand</span>
                          <span className="signal-item-val">
                            {analyzeSingleRepo(r).demandHighlight.bounties > 0 ? `${analyzeSingleRepo(r).demandHighlight.bounties} bounties. ` : ""}
                            {analyzeSingleRepo(r).demandHighlight.topWish ? `Top wish: "${analyzeSingleRepo(r).demandHighlight.topWish}"` : ""}
                          </span>
                        </div>
                      )}
                    </div>

                    <div className="product-playbooks-list">
                      <h4 className="playbooks-title">Candidate Product Angles</h4>
                      <div className="playbooks-grid">
                        {analyzeSingleRepo(r).playbooks.map((p) => (
                          <div key={p.title} className="playbook-card">
                            <div className="playbook-head">
                              <span className="playbook-name">{p.title}</span>
                              <span className={`playbook-type type-${p.type}`}>{p.type}</span>
                            </div>
                            <p className="playbook-desc">{p.description}</p>
                            <p className="playbook-rationale">
                              <strong>Why:</strong> {p.rationale}
                            </p>
                          </div>
                        ))}
                      </div>
                    </div>

                    {/* Categorized MCP Prompt Library */}
                    <div className="prompt-library-section">
                      <div className="prompt-library-header">
                        <div className="prompt-library-title-wrap">
                          <h4 className="prompt-library-title">
                            <IconSparkles size={14} />
                            <span>MCP Prompt Library</span>
                          </h4>
                          <span className="muted small">
                            Pre-engineered prompts combining {r.full_name} data with ossdex MCP tools
                          </span>
                        </div>
                        <div className="prompt-library-actions">
                          <button
                            type="button"
                            className={`btn-subtle small-btn ${showPromptPreview ? "active" : ""}`}
                            onClick={() => setShowPromptPreview((v) => !v)}
                            title="Toggle Markdown prompt preview"
                          >
                            <IconFileText size={12} />
                            <span>{showPromptPreview ? "Hide Preview" : "Preview Prompt"}</span>
                          </button>
                          <button
                            type="button"
                            className="btn-subtle small-btn"
                            onClick={() => copyPromptById(selectedPromptId)}
                            title={`Copy ${selectedTemplate.title} for your MCP client`}
                          >
                            {copiedTemplateId === selectedPromptId ? <IconCheck size={12} /> : <IconCopy size={12} />}
                            <span>{copiedTemplateId === selectedPromptId ? "Copied!" : "Copy Active"}</span>
                          </button>
                        </div>
                      </div>

                      <div className="prompt-category-tabs">
                        {SINGLE_REPO_CATEGORIES.map((cat) => (
                          <button
                            key={cat}
                            type="button"
                            className={`prompt-cat-pill ${promptCategory === cat ? "active" : ""}`}
                            onClick={() => setPromptCategory(cat)}
                          >
                            {cat}
                          </button>
                        ))}
                      </div>

                      <div className="prompt-cards-grid">
                        {(promptCategory === "All"
                          ? SINGLE_REPO_PROMPTS
                          : SINGLE_REPO_PROMPTS.filter((p) => p.category === promptCategory)
                        ).map((tpl) => {
                          const isSelected = selectedPromptId === tpl.id;
                          const isCopied = copiedTemplateId === tpl.id;
                          return (
                            <div
                              key={tpl.id}
                              className={`prompt-card ${isSelected ? "selected" : ""}`}
                              onClick={() => setSelectedPromptId(tpl.id)}
                            >
                              <div className="prompt-card-head">
                                <span className="prompt-card-title">{tpl.title}</span>
                                <span className="prompt-card-badge">{tpl.badge}</span>
                              </div>
                              <p className="prompt-card-summary">{tpl.summary}</p>
                              <div className="prompt-card-foot">
                                <div className="prompt-tool-tags">
                                  {tpl.toolsUsed.map((t) => (
                                    <span key={t} className="prompt-tool-tag font-mono">
                                      {t}
                                    </span>
                                  ))}
                                </div>
                                <button
                                  type="button"
                                  className="btn-subtle small-btn prompt-card-copy"
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    setSelectedPromptId(tpl.id);
                                    copyPromptById(tpl.id);
                                  }}
                                  title={`Copy ${tpl.title} prompt`}
                                >
                                  {isCopied ? <IconCheck size={11} /> : <IconCopy size={11} />}
                                  <span>{isCopied ? "Copied" : "Copy"}</span>
                                </button>
                              </div>
                            </div>
                          );
                        })}
                      </div>

                      {showPromptPreview && (
                        <div className="prompt-preview-drawer">
                          <div className="preview-drawer-head">
                            <span className="preview-title">
                              <IconCode size={13} />
                              <span>
                                Live Prompt Preview: <strong>{selectedTemplate.title}</strong>
                              </span>
                            </span>
                            <div className="preview-actions">
                              <button
                                type="button"
                                className="btn-subtle small-btn"
                                onClick={() => copyPromptById(selectedPromptId)}
                              >
                                {copiedTemplateId === selectedPromptId ? <IconCheck size={11} /> : <IconCopy size={11} />}
                                <span>{copiedTemplateId === selectedPromptId ? "Copied!" : "Copy Prompt"}</span>
                              </button>
                              <button
                                type="button"
                                className="icon-btn small-btn"
                                onClick={() => setShowPromptPreview(false)}
                                title="Close preview"
                              >
                                <IconX size={12} />
                              </button>
                            </div>
                          </div>
                          <pre className="prompt-preview-code">
                            {selectedTemplate.generate({ repo: r })}
                          </pre>
                        </div>
                      )}
                    </div>

                    {analyzeSingleRepo(r).risks.length > 0 && (
                      <div className="product-risks-callout">
                        <span className="risks-title">Risks & Considerations:</span>
                        <ul className="risks-list">
                          {analyzeSingleRepo(r).risks.map((risk, i) => (
                            <li key={i}>{risk}</li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </section>
                </>
              );
            })()}

            {(r.lists?.length ?? 0) > 0 && (
              <div className="chips">
                {r.lists!.map((l) => (
                  <button
                    key={l.list}
                    type="button"
                    className="chip clickable"
                    onClick={() => {
                      if (onFilterList) {
                        onFilterList(l.list);
                        onClose();
                      }
                    }}
                    title={`Listed in ${l.list}${l.section ? ` › ${l.section}` : ""}. Click to filter by this list`}
                  >
                    <IconAward size={12} />
                    <span>
                      {l.list.split("/").pop()}
                      {l.section ? ` · ${l.section}` : ""}
                    </span>
                  </button>
                ))}
              </div>
            )}

            {r.money && (r.money.signals.length > 0 || r.money.funding.length > 0) && (
              <div className="chips" title="Business-model hints read from the README and funding links: companies already pay for services around this project">
                {r.money.signals.map((m) => (
                  <button
                    key={m}
                    type="button"
                    className="chip clickable"
                    onClick={() => {
                      if (onFilterMoney) {
                        onFilterMoney(m);
                        onClose();
                      }
                    }}
                  >
                    <IconSparkles size={11} />
                    <span>{m.replace("_", " ")}</span>
                  </button>
                ))}
              </div>
            )}

            {(r.papers?.length ?? 0) > 0 && (
              <div className="chips">
                {r.papers!.map((p) => (
                  <a
                    key={p.arxiv_id}
                    className="chip clickable"
                    href={p.url}
                    target="_blank"
                    rel="noreferrer"
                    title="The README links to this paper"
                  >
                    <IconFileText size={12} />
                    <span>{p.title ?? `arXiv:${p.arxiv_id}`}</span>
                  </a>
                ))}
              </div>
            )}

            {r.topics.length > 0 && (
              <div className="chips">
                {r.topics.map((t) => (
                  <button
                    key={t}
                    type="button"
                    className="chip topic clickable"
                    onClick={() => {
                      if (onFilterTopic) {
                        onFilterTopic(t);
                        onClose();
                      }
                    }}
                    title={`Filter by topic #${t}`}
                  >
                    #{t}
                  </button>
                ))}
              </div>
            )}

            {hasStarHistory && (
              <section className="trend-box">
                <div className="section-head">
                  <div className="trend-title-group">
                    <h3 className="section-title">
                      <IconTrendingUp size={14} />
                      <span>History & Velocity</span>
                    </h3>
                    <div className="trend-metric-toggle">
                      <button
                        type="button"
                        className={`trend-toggle-btn ${chartMetric === "stars" ? "active" : ""}`}
                        onClick={() => setChartMetric("stars")}
                      >
                        Stars
                      </button>
                      <button
                        type="button"
                        className={`trend-toggle-btn ${chartMetric === "forks" ? "active" : ""}`}
                        onClick={() => setChartMetric("forks")}
                      >
                        Forks
                      </button>
                    </div>
                  </div>
                  <div className="gain-pills">
                    {r.gain_1d != null && r.gain_1d !== 0 && (
                      <span className="gain-badge">
                        <IconTrendingUp size={11} />
                        <span>{r.gain_1d > 0 ? "+" : ""}{r.gain_1d.toLocaleString()} (1d)</span>
                      </span>
                    )}
                    {r.gain_7d != null && r.gain_7d !== 0 && (
                      <span className="gain-badge">
                        <IconTrendingUp size={11} />
                        <span>{r.gain_7d > 0 ? "+" : ""}{r.gain_7d.toLocaleString()} (7d)</span>
                      </span>
                    )}
                  </div>
                </div>
                <TrendChart points={r.history} metric={chartMetric} />
              </section>
            )}

            {similar.data?.repos && similar.data.repos.length > 0 && (
              <section className="similar-strip-box">
                <h3 className="section-title">
                  <IconSparkles size={13} />
                  <span>Similar Repositories</span>
                </h3>
                <div className="similar-strip">
                  {similar.data.repos.map((s) => (
                    <div key={s.ghr_id} className="similar-card-item">
                      <button
                        type="button"
                        className="similar-card"
                        onClick={() => onOpenRepo ? onOpenRepo(s.full_name) : undefined}
                      >
                        <div className="similar-name">{s.full_name}</div>
                        <div className="similar-meta">
                          {s.language && <span>{s.language}</span>}
                          <span>★ {fmtStars(s.stars)}</span>
                        </div>
                      </button>
                    </div>
                  ))}
                </div>
              </section>
            )}
          </div>

          {r.demand && (
            <section className="demand-box">
              <h3>
                What users ask for{" "}
                <span className="muted small">
                  {r.demand.help_wanted} help wanted · {r.demand.bounties} bounties
                </span>
              </h3>
              <ol className="demand-list">
                {r.demand.top_issues.map((i) => (
                  <li key={i.number}>
                    <a href={i.url} target="_blank" rel="noreferrer">
                      {i.title}
                    </a>{" "}
                    <span className="muted small">
                      👍 {i.reactions} · 💬 {i.comments}
                    </span>
                  </li>
                ))}
              </ol>
            </section>
          )}

          {r.readme_excerpt && (
            <section className="readme-window">
              <div className="readme-window-bar">
                <IconBookOpen size={14} />
                <span>README.md</span>
              </div>
              <div className="readme-content readme">
                <ReactMarkdown
                  urlTransform={transformUri}
                  rehypePlugins={[rehypeSanitize]}
                >
                  {r.readme_excerpt}
                </ReactMarkdown>
              </div>
              {r.readme_truncated && (
                <a className="readme-more" href={r.readme_url} target="_blank" rel="noreferrer noopener">
                  Read the full README on GitHub →
                </a>
              )}
            </section>
          )}
        </div>
      )}
    </>
  );

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <article
        className={`repo-modal ${maximized ? "maximized" : ""}`}
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label={name}
      >
        {content}
      </article>
    </div>
  );
}
