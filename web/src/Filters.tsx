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
  IconSliders,
  IconSort,
  IconSparkles,
  IconX,
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

const GAIN_WINDOWS: [string, string, string][] = [
  ["1", "Day", "1d (daily)"],
  ["7", "Week", "7d (weekly)"],
  ["30", "Month", "30d (monthly)"],
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
      {isOpen && (
        <>
          <div className="filter-popover-backdrop" onClick={() => props.setOpenId(null)} />
          <div className="filter-popover">
            <div className="popover-mobile-head">
              <span className="popover-mobile-title">{props.label}</span>
              <button
                type="button"
                className="popover-mobile-close"
                onClick={() => props.setOpenId(null)}
                aria-label="Close filter"
              >
                <IconX size={15} />
              </button>
            </div>
            {props.children}
          </div>
        </>
      )}
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
                <span className="facet-name" title={f.value}>
                  {showColorDot && <span className="lang-dot" style={{ backgroundColor: langColor(f.value) }} />}
                  <span className="facet-text">{f.value}</span>
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

/** "1,500", "1.5k" or "2m" → "1500"; anything else → "". */
function parseCount(text: string): string {
  const m = text.trim().toLowerCase().replace(/[,_\s]/g, "").match(/^(\d+(?:\.\d+)?)([km]?)$/);
  if (!m) return "";
  return String(Math.round(Number(m[1]) * (m[2] === "k" ? 1e3 : m[2] === "m" ? 1e6 : 1)));
}

/** Number box that applies on blur or Enter, so typing doesn't refetch on every keystroke. */
function CountInput(props: { value: string; placeholder: string; label: string; onCommit: (v: string) => void }) {
  const [draft, setDraft] = useState(props.value);
  useEffect(() => setDraft(props.value), [props.value]);
  const commit = () => {
    const v = parseCount(draft);
    setDraft(v);
    if (v !== props.value) props.onCommit(v);
  };
  return (
    <input
      type="text"
      inputMode="numeric"
      className="adv-input"
      aria-label={props.label}
      placeholder={props.placeholder}
      value={draft}
      onChange={(e) => setDraft(e.target.value)}
      onBlur={commit}
      onKeyDown={(e) => {
        if (e.key === "Enter") commit();
      }}
    />
  );
}

function RangeField(props: {
  label: string;
  min: string;
  max: string;
  presets?: number[];
  onChange: (min: string, max: string) => void;
}) {
  const { label, min, max } = props;
  const commit = (lo: string, hi: string) => {
    if (lo && hi && Number(lo) > Number(hi)) [lo, hi] = [hi, lo];
    props.onChange(lo, hi);
  };
  return (
    <div className="adv-field">
      <span className="adv-label">{label}</span>
      <div className="adv-range">
        <CountInput value={min} placeholder="Min" label={`Minimum ${label.toLowerCase()}`} onCommit={(v) => commit(v, max)} />
        <span className="adv-dash" aria-hidden="true">–</span>
        <CountInput value={max} placeholder="Max" label={`Maximum ${label.toLowerCase()}`} onCommit={(v) => commit(min, v)} />
      </div>
      {props.presets && (
        <div className="preset-grid">
          {props.presets.map((p) => {
            const on = min === String(p) && !max;
            return (
              <button
                key={p}
                type="button"
                className={`preset-btn ${on ? "active" : ""}`}
                onClick={() => commit(on ? "" : String(p), "")}
              >
                {p >= 1000 ? `${p / 1000}k` : p}+
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

function DateField(props: { label: string; value: string; onChange: (v: string) => void; quick: [string, number][] }) {
  return (
    <div className="adv-field">
      <span className="adv-label">{props.label}</span>
      <input
        type="date"
        className="adv-input"
        aria-label={props.label}
        value={props.value}
        max={daysAgo(0)}
        onChange={(e) => props.onChange(e.target.value)}
      />
      <div className="adv-quick">
        {props.quick.map(([text, days]) => {
          const on = props.value === daysAgo(days);
          return (
            <button
              key={text}
              type="button"
              className={`preset-btn ${on ? "active" : ""}`}
              onClick={() => props.onChange(on ? "" : daysAgo(days))}
            >
              {text}
            </button>
          );
        })}
      </div>
    </div>
  );
}

function Toggle(props: { label: string; hint: string; checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={props.checked}
      className={`adv-toggle ${props.checked ? "on" : ""}`}
      onClick={() => props.onChange(!props.checked)}
    >
      <span className="adv-toggle-text">
        <span className="adv-toggle-label">{props.label}</span>
        <span className="adv-toggle-hint">{props.hint}</span>
      </span>
      <span className="adv-switch" aria-hidden="true" />
    </button>
  );
}

function AdvancedPanel(props: {
  state: ListState;
  facets: { topics: Facet[]; lists?: Facet[]; money?: Facet[] } | undefined;
  onChange: Patch;
  unlicensedKept?: boolean;
  activeCount: number;
  resultCount?: number;
  onClose: () => void;
}) {
  const { state: s, facets, onChange } = props;
  return (
    <>
      <div className="adv-backdrop" onClick={props.onClose} />
      <div className="adv-panel" role="region" aria-label="Advanced filters">
        <div className="popover-mobile-head">
          <span className="popover-mobile-title">Advanced filters</span>
          <button type="button" className="popover-mobile-close" onClick={props.onClose} aria-label="Close advanced filters">
            <IconX size={15} />
          </button>
        </div>

        <div className="adv-grid">
          <fieldset className="adv-section">
            <legend>Popularity</legend>
            <RangeField
              label="Stars"
              min={s.min_stars}
              max={s.max_stars}
              presets={[100, 1000, 10000, 50000]}
              onChange={(min_stars, max_stars) => onChange({ min_stars, max_stars })}
            />
            <RangeField
              label="Forks"
              min={s.min_forks}
              max={s.max_forks}
              onChange={(min_forks, max_forks) => onChange({ min_forks, max_forks })}
            />
          </fieldset>

          <fieldset className="adv-section">
            <legend>Momentum</legend>
            <div className="adv-field">
              <span className="adv-label">Gained at least</span>
              <div className="adv-range">
                <CountInput
                  value={s.min_gain}
                  placeholder="e.g. 50"
                  label="Minimum stars gained"
                  onCommit={(min_gain) => onChange({ min_gain })}
                />
                <span className="adv-unit">stars per</span>
              </div>
              <div className="segmented" role="radiogroup" aria-label="Gain window">
                {GAIN_WINDOWS.map(([days, label]) => (
                  <button
                    key={days}
                    type="button"
                    role="radio"
                    aria-checked={s.gain_days === days}
                    className={`seg-btn ${s.gain_days === days ? "active" : ""}`}
                    onClick={() => onChange({ gain_days: days })}
                  >
                    {label}
                  </button>
                ))}
              </div>
              <span className="adv-hint">Rising repos. Needs a few days of collected star history.</span>
            </div>
          </fieldset>

          <fieldset className="adv-section">
            <legend>Activity</legend>
            <DateField
              label="Updated after"
              value={s.pushed_after}
              quick={[["30 days", 30], ["6 months", 182], ["1 year", 365]]}
              onChange={(pushed_after) => onChange({ pushed_after })}
            />
            <DateField
              label="Created after"
              value={s.created_after}
              quick={[["90 days", 90], ["1 year", 365], ["3 years", 1095]]}
              onChange={(created_after) => onChange({ created_after })}
            />
            <DateField
              label="Not updated since"
              value={s.pushed_before}
              quick={[["1 year", 365], ["2 years", 730]]}
              onChange={(pushed_before) => onChange({ pushed_before })}
            />
          </fieldset>

          <fieldset className="adv-section">
            <legend>Quality</legend>
            <Toggle
              label="Has a README"
              hint="Skip repos with no documentation"
              checked={s.with_readme}
              onChange={(with_readme) => onChange({ with_readme })}
            />
            <Toggle
              label="Cites a research paper"
              hint="README links to an arXiv paper"
              checked={s.mentions_paper}
              onChange={(mentions_paper) => onChange({ mentions_paper })}
            />
            {props.unlicensedKept && (
              <Toggle
                label="Licensed only"
                hint="Hide repos with no license"
                checked={s.licensed_only}
                onChange={(licensed_only) => onChange({ licensed_only })}
              />
            )}
          </fieldset>

          {facets?.topics && facets.topics.length > 0 && (
            <fieldset className="adv-section">
              <legend>Topics</legend>
              <FacetMenu
                title="Topics"
                items={facets.topics}
                selected={s.topics}
                onChange={(topics) => onChange({ topics })}
              />
            </fieldset>
          )}

          {facets?.lists && facets.lists.length > 0 && (
            <fieldset className="adv-section">
              <legend><IconAward size={12} /> Curated lists</legend>
              <FacetMenu
                title="Awesome lists"
                items={facets.lists}
                selected={s.in_lists}
                onChange={(in_lists) => onChange({ in_lists })}
              />
            </fieldset>
          )}

          {facets?.money && facets.money.length > 0 && (
            <fieldset className="adv-section">
              <legend><IconSparkles size={12} /> Business signals</legend>
              <FacetMenu
                title="Business signals"
                items={facets.money}
                selected={s.money}
                onChange={(money) => onChange({ money })}
              />
            </fieldset>
          )}
        </div>

        <div className="adv-foot">
          <button
            type="button"
            className="reset-btn"
            disabled={props.activeCount === 0}
            onClick={() => onChange({
              min_stars: "", max_stars: "", min_forks: "", max_forks: "", min_gain: "",
              pushed_after: "", pushed_before: "", created_after: "",
              with_readme: false, mentions_paper: false, licensed_only: false,
              topics: [], in_lists: [], money: [],
            })}
          >
            <IconReset size={12} />
            <span>Clear advanced</span>
          </button>
          <button type="button" className="btn adv-done" onClick={props.onClose}>
            {props.resultCount != null ? `Show ${props.resultCount.toLocaleString()} repos` : "Done"}
          </button>
        </div>
      </div>
    </>
  );
}

export default function Filters(props: {
  state: ListState;
  facets: { languages: Facet[]; topics: Facet[]; licenses: Facet[]; lists?: Facet[]; money?: Facet[] } | undefined;
  onChange: Patch;
  unlicensedKept?: boolean;
  savedRepos?: string[];
  resultCount?: number;
}) {
  const {
    state: s,
    facets,
    onChange,
    savedRepos = [],
  } = props;
  const [openId, setOpenId] = useState<string | null>(null);
  const [advOpen, setAdvOpen] = useState(false);
  const barRef = useRef<HTMLElement>(null);

  useEffect(() => {
    if (!openId) return;
    const onDocClick = (e: MouseEvent) => {
      if (barRef.current && !barRef.current.contains(e.target as Node)) {
        setOpenId(null);
      }
    };
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, [openId]);

  useEffect(() => {
    if (!openId && !advOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setOpenId(null);
        setAdvOpen(false);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [openId, advOpen]);

  const hasStars = Boolean(s.min_stars || s.max_stars);
  const hasForks = Boolean(s.min_forks || s.max_forks);
  const licenseCount = s.licenses.length + s.license_kinds.length;
  const advancedCount =
    [hasStars, hasForks, s.min_gain, s.pushed_after, s.pushed_before, s.created_after, s.with_readme, s.mentions_paper, s.licensed_only]
      .filter(Boolean).length + s.topics.length + s.in_lists.length + s.money.length;
  const isShowingSaved = savedRepos.length > 0 && s.names.length === savedRepos.length && savedRepos.every((r) => s.names.includes(r));
  const searching = s.q.trim() !== "";
  const currentSort = s.sort || (searching ? "relevance" : "stars");
  const gainWindow = GAIN_WINDOWS.find(([d]) => d === s.gain_days)?.[2] ?? "1d (daily)";

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
      ? [{ key: "gain", label: `+${Number(s.min_gain).toLocaleString()} ★ / ${gainWindow}`, clear: () => onChange({ min_gain: "" }) }]
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
    ...(s.mentions_paper
      ? [{ key: "paper", label: "Mentions a paper", clear: () => onChange({ mentions_paper: false }) }]
      : []),
    ...(s.with_readme
      ? [{ key: "readme", label: "Has a README", clear: () => onChange({ with_readme: false }) }]
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
    <section className={`top-filters ${openId || advOpen ? "sheet-open" : ""}`} ref={barRef} aria-label="Filters">
      <div className="filter-bar-row">
        {/* Simple filters: horizontally scrollable rail on mobile */}
        <div className="filter-pills-scroll">
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
              className={`preset-pill ${s.mentions_paper ? "active" : ""}`}
              onClick={() => onChange({ mentions_paper: !s.mentions_paper })}
              title="Repositories whose README cites an arXiv research paper"
            >
              <IconFileText size={12} />
              <span>Papers</span>
            </button>
          </div>
        </div>

        {/* Advanced, View & Sort Controls Group: always visible, also on mobile */}
        <div className="filter-controls-group">
          <button
            type="button"
            className={`filter-pill adv-trigger ${advOpen ? "open" : ""} ${advancedCount > 0 ? "active" : ""}`}
            aria-expanded={advOpen}
            onClick={() => {
              setOpenId(null);
              setAdvOpen((o) => !o);
            }}
          >
            <IconSliders size={13} />
            <span>Advanced</span>
            {advancedCount > 0 && <span className="pill-badge">{advancedCount}</span>}
            <IconChevronDown size={12} className="chev" />
          </button>

          {/* Sort Dropdown */}
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

          {active && (
            <button
              type="button"
              className="reset-btn"
              onClick={() => onChange({ ...DEFAULTS, q: s.q, sort: s.sort, repo: s.repo })}
            >
              <IconReset size={12} />
              <span>Reset</span>
            </button>
          )}
        </div>
      </div>

      {advOpen && (
        <AdvancedPanel
          state={s}
          facets={facets}
          onChange={onChange}
          unlicensedKept={props.unlicensedKept}
          activeCount={advancedCount}
          resultCount={props.resultCount}
          onClose={() => setAdvOpen(false)}
        />
      )}

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
