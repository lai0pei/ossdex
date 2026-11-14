import { useEffect, useRef, useState, type ReactNode } from "react";
import type { Facet } from "./types";
import type { ListState } from "./state";
import { DEFAULTS } from "./state";
import { langColor } from "./ago";
import {
  IconAward,
  IconBookmark,
  IconChevronDown,
  IconCode,
  IconFileText,
  IconReset,
  IconShieldCheck,
  IconSort,
  IconSparkles,
} from "./icons";

type Patch = (p: Partial<ListState>) => void;

const LICENSE_KINDS = [
  { id: "permissive", label: "Permissive", hint: "MIT, Apache 2.0, BSD (business friendly)" },
  { id: "weak_copyleft", label: "Weak Copyleft", hint: "LGPL, MPL (library copyleft)" },
  { id: "copyleft", label: "Copyleft", hint: "GPL (source sharing required)" },
  { id: "network_copyleft", label: "Network Copyleft", hint: "AGPL (covers SaaS usage)" },
  { id: "other", label: "Other / Source-Available", hint: "BSL, SSPL, custom licenses" },
];

export const SORTS: [string, string][] = [
  ["relevance", "Relevance"],
  ["stars", "Most stars"],
  ["gain_1d", "Rising (Daily)"],
  ["gain_7d", "Rising (Weekly)"],
  ["pushed", "Recently updated"],
  ["created", "Newest"],
  ["oldest", "Oldest"],
  ["forks", "Most forks"],
];

function PopoverFilter(props: {
  id: string;
  openId: string | null;
  setOpenId: (id: string | null) => void;
  icon: ReactNode;
  label: string;
  activeCount?: number;
  children: ReactNode;
}) {
  const isOpen = props.openId === props.id;
  return (
    <div className="filter-pop-wrap">
      <button
        type="button"
        className={`filter-pill ${isOpen ? "open" : ""} ${(props.activeCount ?? 0) > 0 ? "active" : ""}`}
        onClick={() => props.setOpenId(isOpen ? null : props.id)}
      >
        {props.icon}
        <span>{props.label}</span>
        {(props.activeCount ?? 0) > 0 && <span className="pill-badge">{props.activeCount}</span>}
        <IconChevronDown size={12} className="chev" />
      </button>
      {isOpen && <div className="filter-popover">{props.children}</div>}
    </div>
  );
}

function FacetMenu(props: {
  title: string;
  items: Facet[];
  selected: string[];
  showColorDot?: boolean;
  onChange: (v: string[]) => void;
}) {
  const [text, setText] = useState("");
  const { items, selected, showColorDot } = props;
  const shown = items
    .filter((f) => f.value.toLowerCase().includes(text.toLowerCase()))
    .slice(0, 12);
  const toggle = (v: string) =>
    props.onChange(selected.includes(v) ? selected.filter((x) => x !== v) : [...selected, v]);

  return (
    <div className="pop-menu">
      <input
        type="search"
        autoFocus
        className="filter-search"
        placeholder={`Filter ${props.title.toLowerCase()}…`}
        value={text}
        onChange={(e) => setText(e.target.value)}
      />
      <ul className="facet-list">
        {shown.map((f) => {
          const isSel = selected.includes(f.value);
          return (
            <li key={f.value}>
              <button
                type="button"
                className={isSel ? "selected" : ""}
                onClick={() => toggle(f.value)}
              >
                <span className="facet-name">
                  {showColorDot && <span className="lang-dot" style={{ backgroundColor: langColor(f.value) }} />}
                  {f.value}
                </span>
                <span className="count">{isSel ? "✓" : f.count.toLocaleString()}</span>
              </button>
            </li>
          );
        })}
        {shown.length === 0 && <li className="muted small empty-facet">No matches</li>}
      </ul>
    </div>
  );
}

function daysAgo(n: number): string {
  const d = new Date();
  d.setUTCDate(d.getUTCDate() - n);
  return d.toISOString().slice(0, 10);
}

function rangeText(min: string, max: string): string {
  const lo = min ? `≥ ${Number(min).toLocaleString()}` : "";
  const hi = max ? `≤ ${Number(max).toLocaleString()}` : "";
  return lo && hi ? `${lo} – ${hi}` : lo || hi;
}

export default function Filters(props: {
  state: ListState;
  facets: { languages: Facet[]; topics: Facet[]; licenses: Facet[]; lists?: Facet[]; money?: Facet[] } | undefined;
  onChange: Patch;
  unlicensedKept?: boolean;
  savedRepos?: string[];
}) {
  const { state: s, facets, onChange, savedRepos = [] } = props;
  const [openId, setOpenId] = useState<string | null>(null);
  const barRef = useRef<HTMLElement>(null);

  useEffect(() => {
    if (!openId) return;
    const onDocClick = (e: MouseEvent) => {
      if (barRef.current && !barRef.current.contains(e.target as Node)) {
        setOpenId(null);
      }
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpenId(null);
    };
    document.addEventListener("mousedown", onDocClick);
    window.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDocClick);
      window.removeEventListener("keydown", onKey);
    };
  }, [openId]);

  const hasStars = Boolean(s.min_stars || s.max_stars);
  const hasForks = Boolean(s.min_forks || s.max_forks);
  const licenseCount = s.licenses.length + s.license_kinds.length;
  const isShowingSaved = savedRepos.length > 0 && s.names.length === savedRepos.length && savedRepos.every((r) => s.names.includes(r));
  const searching = s.q.trim() !== "";
  const currentSort = s.sort || (searching ? "relevance" : "stars");

  const chips: { key: string; label: string; dot?: string; clear: () => void }[] = [
    ...(s.names.length > 0
      ? [{
          key: "names",
          label: isShowingSaved ? `Saved (${s.names.length})` : `${s.names.length} selected repos`,
          clear: () => onChange({ names: [] }),
        }]
      : []),
    ...s.languages.map((v) => ({
      key: `lang-${v}`,
      label: v,
      dot: langColor(v),
      clear: () => onChange({ languages: s.languages.filter((x) => x !== v) }),
    })),
    ...s.topics.map((v) => ({
      key: `topic-${v}`,
      label: `#${v}`,
      clear: () => onChange({ topics: s.topics.filter((x) => x !== v) }),
    })),
    ...s.license_kinds.map((v) => ({
      key: `kind-${v}`,
      label: `License: ${v}`,
      clear: () => onChange({ license_kinds: s.license_kinds.filter((x) => x !== v) }),
    })),
    ...s.licenses.map((v) => ({
      key: `lic-${v}`,
      label: v,
      clear: () => onChange({ licenses: s.licenses.filter((x) => x !== v) }),
    })),
    ...(hasStars
      ? [{ key: "stars", label: `★ ${rangeText(s.min_stars, s.max_stars)}`, clear: () => onChange({ min_stars: "", max_stars: "" }) }]
      : []),
    ...(hasForks
      ? [{ key: "forks", label: `Forks ${rangeText(s.min_forks, s.max_forks)}`, clear: () => onChange({ min_forks: "", max_forks: "" }) }]
      : []),
    ...(s.min_gain
      ? [{ key: "gain", label: `+${Number(s.min_gain).toLocaleString()} ★ / ${s.gain_days === "7" || s.sort === "gain_7d" ? "7d (weekly)" : "1d (daily)"}`, clear: () => onChange({ min_gain: "" }) }]
      : []),
    ...s.in_lists.map((l) => ({
      key: `list:${l}`,
      label: `In ${l.split("/").pop()}`,
      clear: () => onChange({ in_lists: s.in_lists.filter((x) => x !== l) }),
    })),
    ...s.money.map((m) => ({
      key: `money:${m}`,
      label: `Business: ${m.replace("_", " ")}`,
      clear: () => onChange({ money: s.money.filter((x) => x !== m) }),
    })),
    ...(s.has_bounties
      ? [{ key: "bounties", label: "Has bounties", clear: () => onChange({ has_bounties: false }) }]
      : []),
    ...(s.mentions_paper
      ? [{ key: "paper", label: "Mentions a paper", clear: () => onChange({ mentions_paper: false }) }]
      : []),
    ...(s.licensed_only
      ? [{ key: "licensed", label: "Licensed only", clear: () => onChange({ licensed_only: false }) }]
      : []),
    ...(s.pushed_after
      ? [{ key: "pushed_after", label: `Updated ≥ ${s.pushed_after}`, clear: () => onChange({ pushed_after: "" }) }]
      : []),
    ...(s.pushed_before
      ? [{ key: "pushed_before", label: `Updated < ${s.pushed_before}`, clear: () => onChange({ pushed_before: "" }) }]
      : []),
    ...(s.created_after
      ? [{ key: "created_after", label: `Created ≥ ${s.created_after}`, clear: () => onChange({ created_after: "" }) }]
      : []),
  ];
  const active = chips.length > 0;

  const toggleLicenseKind = (kind: string) => {
    const next = s.license_kinds.includes(kind)
      ? s.license_kinds.filter((k) => k !== kind)
      : [...s.license_kinds, kind];
    onChange({ license_kinds: next });
  };

  return (
    <section className="top-filters" ref={barRef} aria-label="Filters">
      <div className="filter-bar-row">
        <PopoverFilter
          id="lang"
          openId={openId}
          setOpenId={setOpenId}
          icon={<IconCode size={13} />}
          label="Language"
          activeCount={s.languages.length}
        >
          <FacetMenu
            title="Language"
            items={facets?.languages ?? []}
            selected={s.languages}
            showColorDot
            onChange={(languages) => onChange({ languages })}
          />
        </PopoverFilter>

        <PopoverFilter
          id="license"
          openId={openId}
          setOpenId={setOpenId}
          icon={<IconShieldCheck size={13} />}
          label="License"
          activeCount={licenseCount}
        >
          <div className="pop-form" style={{ minWidth: 280 }}>
            <div className="pop-label">License Type</div>
            <div className="license-kind-list">
              {LICENSE_KINDS.map((k) => {
                const checked = s.license_kinds.includes(k.id);
                return (
                  <button
                    key={k.id}
                    type="button"
                    className={`license-kind-btn ${checked ? "active" : ""}`}
                    onClick={() => toggleLicenseKind(k.id)}
                  >
                    <div className="kind-header">
                      <span className="kind-title">{k.label}</span>
                      {checked && <span className="kind-check">✓</span>}
                    </div>
                    <span className="kind-hint">{k.hint}</span>
                  </button>
                );
              })}
            </div>
            {facets?.licenses && facets.licenses.length > 0 && (
              <>
                <div className="pop-label" style={{ marginTop: 6 }}>Specific Licenses (SPDX)</div>
                <FacetMenu
                  title="License"
                  items={facets.licenses}
                  selected={s.licenses}
                  onChange={(licenses) => onChange({ licenses })}
                />
              </>
            )}
          </div>
        </PopoverFilter>

        {facets?.lists && facets.lists.length > 0 && (
          <PopoverFilter
            id="lists"
            openId={openId}
            setOpenId={setOpenId}
            icon={<IconAward size={13} />}
            label="Curated Lists"
            activeCount={s.in_lists.length}
          >
            <FacetMenu
              title="Awesome List"
              items={facets.lists}
              selected={s.in_lists}
              onChange={(in_lists) => onChange({ in_lists })}
            />
          </PopoverFilter>
        )}

        {facets?.money && facets.money.length > 0 && (
          <PopoverFilter
            id="money"
            openId={openId}
            setOpenId={setOpenId}
            icon={<IconSparkles size={13} />}
            label="Business"
            activeCount={s.money.length}
          >
            <FacetMenu
              title="Companies already pay for…"
              items={facets.money.map((m) => ({ ...m, value: m.value }))}
              selected={s.money}
              onChange={(money) => onChange({ money })}
            />
          </PopoverFilter>
        )}

        {savedRepos.length > 0 && (
          <button
            type="button"
            className={`filter-pill ${isShowingSaved ? "active" : ""}`}
            title="Show your bookmarked repositories"
            onClick={() => onChange({ names: isShowingSaved ? [] : savedRepos })}
          >
            <IconBookmark size={13} filled={isShowingSaved} />
            <span>Saved</span>
            <span className="pill-badge">{savedRepos.length}</span>
          </button>
        )}

        {/* 1-Click Discovery Lenses */}
        <div className="inline-lenses">
          <button
            type="button"
            className={`preset-pill ${s.license_kinds.includes("permissive") && s.pushed_after === daysAgo(30) ? "active" : ""}`}
            onClick={() => {
              const isActive = s.license_kinds.includes("permissive") && s.pushed_after === daysAgo(30);
              onChange({
                license_kinds: isActive ? [] : ["permissive"],
                pushed_after: isActive ? "" : daysAgo(30),
              });
            }}
            title="Permissive license (MIT/Apache/BSD) and updated within 30 days"
          >
            <IconShieldCheck size={12} />
            <span>SaaS-Safe</span>
          </button>
          <button
            type="button"
            className={`preset-pill ${s.mentions_paper ? "active" : ""}`}
            onClick={() => onChange({ mentions_paper: !s.mentions_paper })}
            title="Repositories whose README cites an arXiv research paper"
          >
            <IconFileText size={12} />
            <span>Papers</span>
          </button>
        </div>

        {/* Sort Dropdown embedded cleanly in second row */}
        {s.view === "cards" && (
          <div className="filter-sort-wrap">
            <span className="sort-icon-cue"><IconSort size={12} /></span>
            <select
              className="filter-sort-select"
              aria-label="Sort repositories"
              value={currentSort}
              onChange={(e) => {
                const nextSort = e.target.value;
                if (nextSort === "gain_7d") {
                  onChange({ sort: nextSort, gain_days: "7" });
                } else if (nextSort === "gain_1d") {
                  onChange({ sort: nextSort, gain_days: "1" });
                } else {
                  onChange({ sort: nextSort });
                }
              }}
            >
              {SORTS.filter(([v]) => v !== "relevance" || searching).map(([v, label]) => (
                <option key={v} value={v}>{label}</option>
              ))}
            </select>
          </div>
        )}

        {active && (
          <button
            type="button"
            className="reset-btn"
            onClick={() => onChange({ ...DEFAULTS, q: s.q, sort: s.sort, repo: s.repo, view: s.view })}
          >
            <IconReset size={12} />
            <span>Reset</span>
          </button>
        )}
      </div>

      {active && (
        <div className="active-chips-row">
          {chips.map((c) => (
            <button key={c.key} className="chip on" onClick={c.clear}>
              {c.dot && <span className="lang-dot" style={{ backgroundColor: c.dot }} />}
              <span>{c.label}</span>
              <span className="chip-x">×</span>
            </button>
          ))}
        </div>
      )}
    </section>
  );
}
