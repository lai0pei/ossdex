const UNITS: [Intl.RelativeTimeFormatUnit, number][] = [
  ["year", 365 * 86400],
  ["month", 30 * 86400],
  ["week", 7 * 86400],
  ["day", 86400],
  ["hour", 3600],
  ["minute", 60],
];
const rtf = new Intl.RelativeTimeFormat("en", { numeric: "auto" });

/** Clean relative timestamp ("3 days ago"); falls back to YYYY-MM-DD. */
export function agoWithDate(iso: string): string {
  const date = iso.slice(0, 10);
  const secs = (Date.now() - new Date(iso).getTime()) / 1000;
  if (!Number.isFinite(secs)) return date;
  if (secs < 60) return "just now";
  const [unit, size] = UNITS.find(([, s]) => secs >= s) ?? UNITS[UNITS.length - 1];
  return rtf.format(-Math.floor(secs / size), unit);
}

const LANG_COLORS: Record<string, string> = {
  typescript: "#3178c6",
  javascript: "#f1e05a",
  python: "#3572A5",
  go: "#00ADD8",
  rust: "#dea584",
  java: "#b07219",
  "c++": "#f34b7d",
  c: "#555555",
  "c#": "#178600",
  ruby: "#701516",
  php: "#4F5D95",
  swift: "#F05138",
  kotlin: "#A97BFF",
  dart: "#00B4AB",
  shell: "#89e051",
  html: "#e34c26",
  css: "#563d7c",
  vue: "#41b883",
  svelte: "#ff3e00",
  zig: "#ec915c",
  elixir: "#6e4a7e",
  haskell: "#5e5086",
  lua: "#000080",
  scala: "#c22d40",
  r: "#198CE7",
  julia: "#a270ba",
  clojure: "#db5855",
  jupyter: "#DA5B0B",
  "jupyter notebook": "#DA5B0B",
};

/** Returns a GitHub-style hex color for a programming language, or a deterministic fallback. */
export function langColor(lang: string | null | undefined): string {
  if (!lang) return "#8b95a7";
  const key = lang.toLowerCase();
  if (LANG_COLORS[key]) return LANG_COLORS[key];
  let hash = 0;
  for (let i = 0; i < key.length; i++) {
    hash = key.charCodeAt(i) + ((hash << 5) - hash);
  }
  const hue = Math.abs(hash) % 360;
  return `hsl(${hue}, 62%, 52%)`;
}
