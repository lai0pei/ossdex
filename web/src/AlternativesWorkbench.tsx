import { useState, useMemo, useCallback } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchAlternatives } from "./api";
import type { AlternativeCandidate } from "./types";
import {
  ALTERNATIVE_PROMPTS,
  type AlternativePromptContext,
} from "./promptLibrary";
import { fmtStars, OwnerAvatar } from "./RepoList";
import { langColor } from "./ago";
import {
  IconCheck,
  IconCopy,
  IconGitHub,
  IconGlobe,
  IconSearch,
  IconSparkles,
  IconStar,
  IconTrendingUp,
  IconX,
  IconSliders,
  IconShieldCheck,
  IconActivity,
  IconCode,
} from "./icons";

interface AlternativesWorkbenchProps {
  onOpenRepo: (fullName: string) => void;
  savedRepos?: string[];
  onToggleSaved?: (fullName: string) => void;
}

const AVAILABLE_HABITS = [
  { id: "cli-first", label: "CLI & Terminal First", desc: "Prefers command-line & TUI apps" },
  { id: "keyboard-driven", label: "Keyboard & Vim Driven", desc: "Vim keybindings & modal navigation" },
  { id: "native-gui", label: "Native Desktop GUI", desc: "Prefers graphical windowed desktop apps" },
  { id: "local-first", label: "Local-First & Offline", desc: "Plaintext/SQLite, zero mandatory cloud" },
  { id: "self-hosted-docker", label: "Self-Hosted & Docker", desc: "Containerized self-hosting ready" },
  { id: "ai-assisted", label: "Local AI Assisted", desc: "Integrates with local LLMs (Ollama)" },
  { id: "lightweight", label: "Lightweight & Fast", desc: "Minimal CPU/memory footprint" },
];

const POPULAR_PRESETS = [
  "Notion",
  "Postman",
  "TablePlus",
  "Docker Desktop",
  "Raycast",
  "1Password",
  "Slack",
  "Linear",
  "Zapier",
  "Vercel",
  "Datadog",
  "Firebase",
];

type TargetOS = "macos" | "linux" | "windows";
const OS_OPTIONS: TargetOS[] = ["macos", "linux", "windows"];

/** The visitor's own OS, from their browser. */
function guessOS(): TargetOS {
  const ua = typeof navigator === "undefined" ? "" : navigator.userAgent;
  if (/Mac/i.test(ua)) return "macos";
  if (/Win/i.test(ua)) return "windows";
  return "linux";
}

export default function AlternativesWorkbench({
  onOpenRepo,
  savedRepos = [],
  onToggleSaved,
}: AlternativesWorkbenchProps) {
  // 1. State for user selections. The server never inspects its own machine: the visitor says
  // which OS and habits to score for (the OS defaults from their own browser).
  const [selectedProduct, setSelectedProduct] = useState<string>("Notion");
  const [searchInput, setSearchInput] = useState<string>("");
  const [selectedHabits, setSelectedHabits] = useState<string[]>(["cli-first", "keyboard-driven"]);
  const [targetOS, setTargetOS] = useState<TargetOS>(guessOS);
  const [selectedPromptId, setSelectedPromptId] = useState<string>("personal-migration-advisor");
  const [userNotes, setUserNotes] = useState<string>("");
  const [copiedPrompt, setCopiedPrompt] = useState<boolean>(false);
  const [copiedCmd, setCopiedCmd] = useState<string | null>(null);

  // 2. Fetch Alternatives Query
  const altParams = useMemo(() => {
    const p = new URLSearchParams();
    p.set("product", selectedProduct);
    p.set("os", targetOS);
    p.set("limit", "10");
    selectedHabits.forEach((h) => p.append("habits", h));
    return p;
  }, [selectedProduct, targetOS, selectedHabits]);

  const alternativesQuery = useQuery({
    queryKey: ["alternatives", altParams.toString()],
    queryFn: ({ signal }) => fetchAlternatives(altParams, signal),
    staleTime: 30_000,
  });

  const altsData = alternativesQuery.data;
  const candidates: AlternativeCandidate[] = altsData?.alternatives || [];

  // Toggle habit chip
  const toggleHabit = (habitId: string) => {
    setSelectedHabits((prev) =>
      prev.includes(habitId) ? prev.filter((h) => h !== habitId) : [...prev, habitId],
    );
  };

  // Submit search
  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (searchInput.trim()) {
      setSelectedProduct(searchInput.trim());
    }
  };

  // 4. Generate LLM Prompt
  const activePromptTemplate = useMemo(() => {
    return ALTERNATIVE_PROMPTS.find((p) => p.id === selectedPromptId) || ALTERNATIVE_PROMPTS[0];
  }, [selectedPromptId]);

  const generatedPrompt = useMemo(() => {
    const ctx: AlternativePromptContext = {
      paidProduct: selectedProduct,
      category: altsData?.category,
      os: targetOS,
      habits: selectedHabits,
      installedTools: [],
      alternatives: candidates,
      articulationGuide: altsData?.articulation_guide,
      userNotes,
    };
    return activePromptTemplate.generate(ctx);
  }, [activePromptTemplate, selectedProduct, altsData, targetOS, selectedHabits, candidates, userNotes]);

  const copyPromptToClipboard = useCallback(() => {
    navigator.clipboard.writeText(generatedPrompt);
    setCopiedPrompt(true);
    setTimeout(() => setCopiedPrompt(false), 2200);
  }, [generatedPrompt]);

  const copyCommand = (cmd: string) => {
    navigator.clipboard.writeText(cmd);
    setCopiedCmd(cmd);
    setTimeout(() => setCopiedCmd(null), 1800);
  };

  return (
    <div className="alt-workbench">
      {/* 1. Header Deck: OS & Habit Personalizer */}
      <section className="alt-profile-deck">
        <div className="alt-profile-header">
          <div className="alt-profile-brand">
            <span className="alt-profile-badge">
              <IconSparkles size={14} />
              <span>Personalized for Your Setup</span>
            </span>
            <h2>Open-Source Alternative Finder & Workflow Articulator</h2>
            <p className="alt-profile-sub">
              Discovers and ranks open-source replacements for commercial software based on the operating system and daily habits you choose.
            </p>
          </div>

          <div className="alt-os-selector-wrap">
            <label className="alt-label">Target OS</label>
            <div className="alt-os-pill-group">
              {OS_OPTIONS.map((osKey) => (
                <button
                  key={osKey}
                  type="button"
                  className={`alt-os-pill ${targetOS === osKey ? "active" : ""}`}
                  onClick={() => setTargetOS(osKey)}
                >
                  {osKey.toUpperCase()}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Habit Toggles */}
        <div className="alt-habits-section">
          <div className="alt-habits-title-row">
            <span className="alt-label">
              <IconSliders size={12} />
              <span>Your Workflow Habits & Preferences</span>
            </span>
            <span className="alt-habits-hint">
              Toggle habits to re-score candidates in real-time
            </span>
          </div>
          <div className="alt-habits-list">
            {AVAILABLE_HABITS.map((h) => {
              const active = selectedHabits.includes(h.id);
              return (
                <button
                  key={h.id}
                  type="button"
                  className={`alt-habit-btn ${active ? "active" : ""}`}
                  onClick={() => toggleHabit(h.id)}
                  title={h.desc}
                >
                  <span className="habit-checkbox">{active ? <IconCheck size={11} /> : null}</span>
                  <span>{h.label}</span>
                </button>
              );
            })}
          </div>
        </div>
      </section>

      {/* 2. Search Bar */}
      <section className="alt-search-section">
        {/* Search Bar */}
        <div className="alt-search-bar-row">
          <form className="alt-search-form" onSubmit={handleSearchSubmit}>
            <span className="alt-search-icon">
              <IconSearch size={15} />
            </span>
            <input
              type="text"
              className="alt-search-input"
              placeholder="Enter commercial product (e.g. Notion, Postman, TablePlus, Docker Desktop, Zapier, 1Password)…"
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
            />
            {searchInput && (
              <button
                type="button"
                className="alt-clear-btn"
                onClick={() => setSearchInput("")}
                aria-label="Clear"
              >
                <IconX size={13} />
              </button>
            )}
            <button type="submit" className="alt-submit-btn">
              Find Alternatives
            </button>
          </form>
        </div>

        {/* Popular Presets */}
        <div className="alt-presets-row">
          <span className="alt-presets-label">Popular Products:</span>
          <div className="alt-presets-list">
            {POPULAR_PRESETS.map((preset) => (
              <button
                key={preset}
                type="button"
                className={`alt-preset-chip ${selectedProduct.toLowerCase() === preset.toLowerCase() ? "active" : ""}`}
                onClick={() => {
                  setSelectedProduct(preset);
                  setSearchInput(preset);
                }}
              >
                {preset}
              </button>
            ))}
          </div>
        </div>
      </section>

      {/* 3. Ranked Results & Fit Analysis */}
      <section className="alt-results-section">
        <div className="alt-results-header">
          <div className="alt-results-title">
            <h3>
              Open-Source Alternatives for <strong>{selectedProduct}</strong>
            </h3>
            {altsData && (
              <span className="alt-category-pill">
                {altsData.category}
              </span>
            )}
          </div>

          {altsData?.articulation_guide?.summary && (
            <p className="alt-guide-summary">
              {altsData.articulation_guide.summary}
            </p>
          )}
        </div>

        {/* Loading state */}
        {alternativesQuery.isFetching && (
          <div className="alt-loading-deck">
            <div className="skeleton-line w-70" />
            <div className="skeleton-block h-120" />
            <div className="skeleton-block h-120" />
          </div>
        )}

        {/* Error state */}
        {alternativesQuery.isError && (
          <div className="alt-error-banner">
            Failed to search alternatives: {String(alternativesQuery.error)}
          </div>
        )}

        {/* Candidates Grid */}
        <div className="alt-candidates-grid">
          {candidates.map((c, idx) => {
            const isSaved = savedRepos.includes(c.full_name);
            const [owner] = c.full_name.split("/", 2);

            return (
              <div key={c.full_name} className={`alt-card rank-${idx + 1}`}>
                {/* Card Top: Rank, Avatar, Fit Score, Actions */}
                <div className="alt-card-top">
                  <div className="alt-card-id-row">
                    <span className="alt-rank-badge">#{idx + 1}</span>
                    <OwnerAvatar owner={owner} size={32} />
                    <div className="alt-name-wrap">
                      <button
                        type="button"
                        className="alt-repo-title-btn"
                        onClick={() => onOpenRepo(c.full_name)}
                      >
                        {c.full_name}
                      </button>
                      <div className="alt-meta-badges">
                        {c.language && (
                          <span className="alt-lang-pill">
                            <span
                              className="lang-dot"
                              style={{ backgroundColor: langColor(c.language) }}
                            />
                            <span>{c.language}</span>
                          </span>
                        )}
                        <span className="alt-meta-stars">
                          <IconStar size={11} filled className="star-icon" />
                          <span>{fmtStars(c.stars)}</span>
                        </span>
                        {c.gain_1d ? (
                          <span className="alt-gain-pill">
                            <IconTrendingUp size={10} />
                            <span>+{fmtStars(c.gain_1d)}/1d</span>
                          </span>
                        ) : c.gain_7d ? (
                          <span className="alt-gain-pill">
                            <IconTrendingUp size={10} />
                            <span>+{fmtStars(c.gain_7d)}/7d</span>
                          </span>
                        ) : null}
                      </div>
                    </div>
                  </div>

                  {/* Fit Score & Badge */}
                  <div className="alt-fit-cell">
                    <div className="alt-score-circle" data-score={c.fit_score}>
                      <span className="alt-score-num">{c.fit_score}%</span>
                      <span className="alt-score-lbl">FIT</span>
                    </div>
                    <span className="alt-fit-badge-lbl">{c.fit_badge}</span>
                  </div>
                </div>

                {/* Description */}
                <p className="alt-desc line-clamp-2">
                  {c.description || "No repository description provided."}
                </p>

                {/* Form Factor & OS Compat */}
                <div className="alt-form-row">
                  <span className="alt-form-chip">
                    <IconCode size={11} />
                    <span>{c.form_factor.replace("_", " ").toUpperCase()}</span>
                  </span>
                  <span className={`alt-os-compat-chip ${c.os_compatible ? "ok" : "warn"}`}>
                    <IconShieldCheck size={11} />
                    <span>{c.os_compatible ? `${targetOS.toUpperCase()} Supported` : "Verify OS"}</span>
                  </span>
                  {c.license && (
                    <span className="alt-lic-chip">
                      <span>{c.license}</span>
                    </span>
                  )}
                </div>

                {/* Habit reasons & Synergies */}
                {(c.habit_reasons.length > 0 || c.workflow_synergies.length > 0) && (
                  <div className="alt-reasons-block">
                    {c.habit_reasons.map((r, i) => (
                      <div key={i} className="alt-reason-line">
                        <span className="check-bullet">✓</span>
                        <span>{r}</span>
                      </div>
                    ))}
                    {c.workflow_synergies.map((s, i) => (
                      <div key={i} className="alt-synergy-line">
                        <span className="synergy-bullet">⚡</span>
                        <span>{s}</span>
                      </div>
                    ))}
                  </div>
                )}

                {/* Tailored Install Command */}
                {c.tailored_install_command && (
                  <div className="alt-install-box">
                    <span className="alt-install-label">Tailored Install:</span>
                    <div className="alt-install-code-row">
                      <code className="alt-install-code font-mono">
                        {c.tailored_install_command}
                      </code>
                      <button
                        type="button"
                        className="alt-copy-cmd-btn"
                        onClick={() => copyCommand(c.tailored_install_command!)}
                        title="Copy command"
                      >
                        {copiedCmd === c.tailored_install_command ? (
                          <IconCheck size={12} />
                        ) : (
                          <IconCopy size={12} />
                        )}
                      </button>
                    </div>
                  </div>
                )}

                {/* Trade-offs Note */}
                {c.tradeoffs && (
                  <div className="alt-tradeoff-box">
                    <span className="tradeoff-icon">ℹ</span>
                    <span className="tradeoff-text">{c.tradeoffs}</span>
                  </div>
                )}

                {/* Footer Actions */}
                <div className="alt-card-actions">
                  <button
                    type="button"
                    className="btn-subtle"
                    onClick={() => onOpenRepo(c.full_name)}
                  >
                    <IconActivity size={12} />
                    <span>Deep Dive</span>
                  </button>

                  {onToggleSaved && (
                    <button
                      type="button"
                      className={`btn-subtle ${isSaved ? "active" : ""}`}
                      onClick={() => onToggleSaved(c.full_name)}
                    >
                      <span>{isSaved ? "Saved" : "Save"}</span>
                    </button>
                  )}

                  {c.homepage && (
                    <a
                      href={c.homepage}
                      target="_blank"
                      rel="noreferrer"
                      className="btn-link alt-ext-link"
                      title="Visit homepage"
                    >
                      <IconGlobe size={11} />
                      <span>Site</span>
                    </a>
                  )}

                  <a
                    href={`https://github.com/${c.full_name}`}
                    target="_blank"
                    rel="noreferrer"
                    className="btn-link alt-ext-link"
                    title="Open on GitHub"
                  >
                    <IconGitHub size={11} />
                    <span>GitHub</span>
                  </a>
                </div>
              </div>
            );
          })}
        </div>
      </section>

      {/* 4. LLM Articulation & Migration Prompt Workbench */}
      <section className="alt-prompt-workbench">
        <div className="alt-prompt-header">
          <div className="alt-prompt-title">
            <span className="alt-prompt-badge">
              <IconSparkles size={13} />
              <span>LLM Articulation & Migration Plan</span>
            </span>
            <h3>Copy 1-Click Tailored Prompt for Claude, ChatGPT & Gemini</h3>
            <p className="alt-prompt-desc">
              Grounds your LLM with your exact local OS, installed package managers, active habits, and the top scored candidates from ossdex.
            </p>
          </div>

          <div className="alt-prompt-tabs">
            {ALTERNATIVE_PROMPTS.map((t) => (
              <button
                key={t.id}
                type="button"
                className={`alt-prompt-tab ${selectedPromptId === t.id ? "active" : ""}`}
                onClick={() => setSelectedPromptId(t.id)}
              >
                <span>{t.badge}</span>
              </button>
            ))}
          </div>
        </div>

        {/* Optional Custom User Requirements */}
        <div className="alt-prompt-custom-row">
          <label className="alt-label">Personal Priorities / Notes (Optional)</label>
          <input
            type="text"
            className="alt-prompt-notes-input"
            placeholder="e.g. Must support end-to-end encryption, local SQLite, dark mode, zero subscription"
            value={userNotes}
            onChange={(e) => setUserNotes(e.target.value)}
          />
        </div>

        {/* Generated Prompt Box */}
        <div className="alt-prompt-box">
          <div className="alt-prompt-box-top">
            <span className="alt-prompt-template-name font-mono">
              Template: {activePromptTemplate.title}
            </span>
            <button
              type="button"
              className={`alt-copy-prompt-btn ${copiedPrompt ? "copied" : ""}`}
              onClick={copyPromptToClipboard}
            >
              {copiedPrompt ? <IconCheck size={13} /> : <IconCopy size={13} />}
              <span>{copiedPrompt ? "Copied to Clipboard!" : "Copy Prompt for LLM"}</span>
            </button>
          </div>
          <pre className="alt-prompt-preview font-mono">{generatedPrompt}</pre>
        </div>
      </section>
    </div>
  );
}
