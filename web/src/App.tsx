import { lazy, Suspense, useCallback, useEffect, useRef, useState } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { fetchFacets, fetchRepos, fetchStatus } from "./api";
import Filters from "./Filters";
import {
  IconBookOpen,
  IconLayoutGrid,
  IconLogo,
  IconMoon,
  IconSearch,
  IconSparkles,
  IconSun,
  IconX,
} from "./icons";
import RepoList from "./RepoList";
import GuideModal from "./GuideModal";
import { serialize, useListState, type ViewMode } from "./state";

const RepoDrawer = lazy(() => import("./RepoDrawer"));

const PAGE_SIZE = 50;

export default function App() {
  const [state, update] = useListState();
  const [query, setQuery] = useState(state.q);
  const [theme, setTheme] = useState<"light" | "dark">(() => {
    const saved = localStorage.getItem("ossdex.theme");
    if (saved === "light" || saved === "dark") return saved;
    return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  });
  const [savedRepos, setSavedRepos] = useState<string[]>(() => {
    try {
      const raw = localStorage.getItem("ossdex.savedRepos");
      return raw ? (JSON.parse(raw) as string[]) : [];
    } catch {
      return [];
    }
  });
  const [showGuide, setShowGuide] = useState(false);
  const searchRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try { localStorage.setItem("ossdex.theme", theme); } catch { /* ignore */ }
  }, [theme]);

  const toggleSaved = useCallback((fullName: string) => {
    setSavedRepos((prev) => {
      const next = prev.includes(fullName) ? prev.filter((r) => r !== fullName) : [...prev, fullName];
      try { localStorage.setItem("ossdex.savedRepos", JSON.stringify(next)); } catch { /* ignore */ }
      return next;
    });
  }, []);

  const pushed = useRef(state.q);
  useEffect(() => {
    if (state.q !== pushed.current) {
      pushed.current = state.q;
      setQuery(state.q);
    }
  }, [state.q]);
  useEffect(() => {
    if (query === pushed.current) return;
    const t = setTimeout(() => {
      pushed.current = query;
      update({ q: query });
    }, 300);
    return () => clearTimeout(t);
  }, [query, update]);

  // Global keyboard shortcut: '/' or Cmd/Ctrl+K focuses search, Esc closes inspector if open
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        searchRef.current?.focus();
        searchRef.current?.select();
        return;
      }
      if (e.key === "Escape" && state.repo) {
        update({ repo: "" }, false);
        return;
      }
      if (e.key === "/" && !e.metaKey && !e.ctrlKey && !e.altKey) {
        const tag = (e.target as HTMLElement | null)?.tagName;
        const editable = (e.target as HTMLElement | null)?.isContentEditable;
        if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || editable) return;
        e.preventDefault();
        searchRef.current?.focus();
        searchRef.current?.select();
      }
      if (e.key === "?" && !e.metaKey && !e.ctrlKey && !e.altKey) {
        const tag = (e.target as HTMLElement | null)?.tagName;
        const editable = (e.target as HTMLElement | null)?.isContentEditable;
        if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || editable) return;
        e.preventDefault();
        setShowGuide(true);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [state.repo, update]);

  const api = serialize(state, false);
  const listParams = new URLSearchParams(api);
  listParams.set("page", String(state.page));
  listParams.set("page_size", String(PAGE_SIZE));
  const facetParams = new URLSearchParams(api);
  facetParams.delete("q");
  facetParams.delete("sort");

  const status = useQuery({ queryKey: ["status"], queryFn: fetchStatus, staleTime: 30_000 });
  const repos = useQuery({
    queryKey: ["repos", listParams.toString()],
    queryFn: ({ signal }) => fetchRepos(listParams, signal),
    placeholderData: keepPreviousData,
  });
  const facets = useQuery({
    queryKey: ["facets", facetParams.toString()],
    queryFn: ({ signal }) => fetchFacets(facetParams, signal),
    placeholderData: keepPreviousData,
  });
  const openRepo = useCallback((repo: string) => update({ repo }, false), [update]);
  const viewMode: ViewMode = state.view || "cards";

  const st = status.data;
  const hasInspector = Boolean(state.repo);

  return (
    <div className={`app ${hasInspector ? "has-split-inspector" : ""}`}>
      {/* Sticky 2-Row Top Deck: Row 1 = Brand, Search, View Switcher, Status & Theme */}
      <header className="topbar">
        <div className="topbar-row-main">
          <div className="brand">
            <span className="brand-logo">
              <IconLogo size={17} />
            </span>
            <h1>ossdex</h1>
          </div>

          <div className="search-wrap">
            <span className="search-icon">
              <IconSearch size={15} />
            </span>
            <input
              ref={searchRef}
              className="search"
              type="search"
              autoFocus
              placeholder="Search repositories by meaning or keyword…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Escape") searchRef.current?.blur();
              }}
            />
            {query ? (
              <button
                className="search-clear"
                onClick={() => { setQuery(""); pushed.current = ""; update({ q: "" }); searchRef.current?.focus(); }}
                aria-label="Clear search"
              >
                <IconX size={13} />
              </button>
            ) : (
              <kbd className="search-kbd" title="Press / or ⌘K to focus search">/</kbd>
            )}
          </div>

          {/* View Mode Switcher */}
          <div className="view-mode-tabs" role="tablist" aria-label="View mode">
            <button
              type="button"
              className={`view-tab ${viewMode === "cards" ? "active" : ""}`}
              onClick={() => update({ view: "cards" }, false)}
              title="Cards view"
              role="tab"
              aria-selected={viewMode === "cards"}
            >
              <IconLayoutGrid size={13} />
              <span>Cards</span>
            </button>
            <button
              type="button"
              className={`view-tab ${viewMode === "alternatives" ? "active" : ""}`}
              onClick={() => update({ view: "alternatives" }, false)}
              title="Find personalized open-source alternatives for paid products"
              role="tab"
              aria-selected={viewMode === "alternatives"}
            >
              <IconSparkles size={13} />
              <span>Alternatives</span>
            </button>
          </div>

          <div className="topbar-actions">
            {(st || repos.data?.total !== undefined) && (
              <div
                className="status-pill muted small font-mono"
                title={
                  repos.data?.total !== undefined && st
                    ? `${repos.data.total.toLocaleString()} matching repositories out of ${st.repos.toLocaleString()} total in database.${st.as_of ? ` Fresh as of ${st.as_of}` : ""}`
                    : `Database has ${st?.repos.toLocaleString() ?? repos.data?.total?.toLocaleString()} repositories.`
                }
              >
                <span className="status-dot online" />
                <span>
                  {repos.data?.total !== undefined && st
                    ? `${repos.data.total.toLocaleString()} / ${st.repos.toLocaleString()} repos`
                    : `${(repos.data?.total ?? st?.repos)?.toLocaleString()} repos`}
                </span>
              </div>
            )}
            <button
              type="button"
              className="btn-link guide-topbar-btn"
              onClick={() => setShowGuide(true)}
              title="User Guide & Desktop MCP Setup (Press ?)"
            >
              <IconBookOpen size={13} />
              <span>Guide & MCP</span>
            </button>
            <button
              className="icon-btn"
              onClick={() => setTheme((t) => (t === "dark" ? "light" : "dark"))}
              title={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
              aria-label="Toggle theme"
            >
              {theme === "dark" ? <IconSun size={14} /> : <IconMoon size={14} />}
            </button>
          </div>
        </div>
      </header>

      {/* Main Workspace: Full-Width List & Workbench */}
      <div className="workspace">
        <section className="pane-list">
          <main className="main-container">
            {/* Top Deck Row 2: Streamlined Filters & Lenses Bar */}
            <Filters
              state={state}
              facets={facets.data}
              onChange={update}
              unlicensedKept={st ? !st.require_license : false}
              savedRepos={savedRepos}
            />

            <RepoList
              data={repos.data}
              loading={repos.isFetching}
              error={repos.error}
              state={state}
              pageSize={PAGE_SIZE}
              onChange={update}
              savedRepos={savedRepos}
              onToggleSaved={toggleSaved}
            />
          </main>
        </section>
      </div>

      {/* Default Modal Popup Dialog */}
      {hasInspector && (
        <Suspense
          fallback={
            <div className="modal-backdrop">
              <div className="repo-modal loading-modal">
                <div className="skeleton-line w-70" />
                <div className="skeleton-block" />
              </div>
            </div>
          }
        >
          {(() => {
            const repoItems = repos.data?.items ?? [];
            const curIdx = repoItems.findIndex((r) => r.full_name.toLowerCase() === state.repo.toLowerCase());
            const prevRepo = curIdx > 0 ? repoItems[curIdx - 1].full_name : null;
            const nextRepo = curIdx >= 0 && curIdx < repoItems.length - 1 ? repoItems[curIdx + 1].full_name : null;

            return (
              <RepoDrawer
                name={state.repo}
                onClose={() => update({ repo: "" }, false)}
                onOpenRepo={openRepo}
                onPrevRepo={prevRepo ? () => openRepo(prevRepo) : undefined}
                onNextRepo={nextRepo ? () => openRepo(nextRepo) : undefined}
                hasPrev={Boolean(prevRepo)}
                hasNext={Boolean(nextRepo)}
                onFilterMoney={(m) => update({ money: [...new Set([...state.money, m])] })}
                onFilterList={(list) => update({ in_lists: [...new Set([...state.in_lists, list])] })}
                onFilterTopic={(topic) => update({ topics: [...new Set([...state.topics, topic])] })}
                onFilterLanguage={(lang) => update({ languages: [lang] })}
                isSaved={savedRepos.includes(state.repo)}
                onToggleSaved={toggleSaved}
              />
            );
          })()}
        </Suspense>
      )}

      {/* Interactive Guide & MCP Setup Modal */}
      <GuideModal
        isOpen={showGuide}
        onClose={() => setShowGuide(false)}
        onNavigateView={(view) => update({ view }, false)}
        onApplyQuickFilter={(patch) => {
          const updates: any = {};
          if (patch.saasSafe !== undefined) updates.licensed_only = patch.saasSafe;
          if (patch.money) updates.money = patch.money;
          update(updates, false);
        }}
      />
    </div>
  );
}
