import type { SVGProps } from "react";

type IconProps = SVGProps<SVGSVGElement> & { size?: number };

const base = (size = 14): SVGProps<SVGSVGElement> => ({
  width: size,
  height: size,
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.85,
  strokeLinecap: "round",
  strokeLinejoin: "round",
  "aria-hidden": true,
});

/**
 * Custom ossdex brand mark: an isometric indexed prism with a central discovery core
 * and connected knowledge nodes.
 */
export function IconLogo({ size = 18, ...p }: IconProps) {
  return (
    <svg {...base(size)} viewBox="0 0 24 24" {...p}>
      {/* Top facet with soft fill */}
      <path
        d="M12 2.2 20.5 7 12 11.8 3.5 7 12 2.2Z"
        fill="currentColor"
        fillOpacity="0.22"
        stroke="currentColor"
        strokeWidth="1.85"
      />
      {/* Left & right isometric wings */}
      <path
        d="M3.5 7v10L12 21.8V11.8"
        fill="currentColor"
        fillOpacity="0.08"
      />
      <path d="M20.5 7v10L12 21.8" />
      {/* Middle index layer */}
      <path d="M3.5 12 12 16.8 20.5 12" strokeOpacity="0.75" />
      {/* Central beacon node */}
      <circle cx="12" cy="7" r="1.4" fill="currentColor" stroke="none" />
    </svg>
  );
}

export function IconSearch({ size = 15, ...p }: IconProps) {
  return (
    <svg {...base(size)} {...p}>
      <circle cx="11" cy="11" r="7.5" fill="currentColor" fillOpacity="0.07" />
      <path d="m20.5 20.5-4.15-4.15" />
    </svg>
  );
}

export function IconSparkles({ size = 15, ...p }: IconProps) {
  return (
    <svg {...base(size)} {...p}>
      <path
        d="M11.5 2.5 9.8 7.9a2 2 0 0 1-1.4 1.4L3 11l5.4 1.7a2 2 0 0 1 1.4 1.4l1.7 5.4 1.7-5.4a2 2 0 0 1 1.4-1.4L20 11l-5.4-1.7a2 2 0 0 1-1.4-1.4L11.5 2.5Z"
        fill="currentColor"
        fillOpacity="0.16"
      />
      <path d="M19 3v3.5" />
      <path d="M17.25 4.75h3.5" />
    </svg>
  );
}

export function IconSliders({ size = 14, ...p }: IconProps) {
  return (
    <svg {...base(size)} {...p}>
      <line x1="4" x2="10" y1="6" y2="6" />
      <line x1="14" x2="20" y1="6" y2="6" />
      <circle cx="12" cy="6" r="2" fill="currentColor" fillOpacity="0.15" />
      <line x1="4" x2="6" y1="12" y2="12" />
      <line x1="10" x2="20" y1="12" y2="12" />
      <circle cx="8" cy="12" r="2" fill="currentColor" fillOpacity="0.15" />
      <line x1="4" x2="14" y1="18" y2="18" />
      <line x1="18" x2="20" y1="18" y2="18" />
      <circle cx="16" cy="18" r="2" fill="currentColor" fillOpacity="0.15" />
    </svg>
  );
}

export function IconReset({ size = 12, ...p }: IconProps) {
  return (
    <svg {...base(size)} {...p}>
      <path d="M3 12a9 9 0 1 0 3-6.7L3 8" />
      <path d="M3 3v5h5" />
    </svg>
  );
}

export function IconCode({ size = 13, ...p }: IconProps) {
  return (
    <svg {...base(size)} {...p}>
      <path d="m16 17 5-5-5-5" />
      <path d="m8 7-5 5 5 5" />
      <path d="m13.5 4-3 16" strokeOpacity="0.65" />
    </svg>
  );
}

export function IconStar({ size = 13, filled = false, ...p }: IconProps & { filled?: boolean }) {
  return (
    <svg {...base(size)} fill={filled ? "currentColor" : "none"} {...p}>
      <path d="M12 2.4 14.95 8.4l6.62.96-4.79 4.67 1.13 6.59L12 17.5l-5.91 3.12 1.13-6.59-4.79-4.67 6.62-.96L12 2.4Z" />
    </svg>
  );
}

export function IconTrendingUp({ size = 13, ...p }: IconProps) {
  return (
    <svg {...base(size)} {...p}>
      <path d="m22 7-8.5 8.5-5-5L2 17" />
      <path d="M16 7h6v6" />
    </svg>
  );
}

export function IconAward({ size = 13, ...p }: IconProps) {
  return (
    <svg {...base(size)} {...p}>
      <circle cx="12" cy="8.5" r="5.5" fill="currentColor" fillOpacity="0.12" />
      <path d="M15.477 12.89 17 22l-5-3-5 3 1.523-9.11" />
    </svg>
  );
}

export function IconFileText({ size = 13, ...p }: IconProps) {
  return (
    <svg {...base(size)} {...p}>
      <path
        d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z"
        fill="currentColor"
        fillOpacity="0.08"
      />
      <polyline points="14 2 14 8 20 8" />
      <line x1="8" x2="16" y1="13" y2="13" />
      <line x1="8" x2="13" y1="17" y2="17" />
    </svg>
  );
}

export function IconClock({ size = 13, ...p }: IconProps) {
  return (
    <svg {...base(size)} {...p}>
      <circle cx="12" cy="12" r="9.5" fill="currentColor" fillOpacity="0.07" />
      <polyline points="12 6.5 12 12 15.5 14" />
    </svg>
  );
}

export function IconFork({ size = 13, ...p }: IconProps) {
  return (
    <svg {...base(size)} {...p}>
      <circle cx="12" cy="18" r="2.5" />
      <circle cx="6" cy="6" r="2.5" />
      <circle cx="18" cy="6" r="2.5" />
      <path d="M18 8.5v2a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2v-2" />
      <path d="M12 12.5v3" />
    </svg>
  );
}

export function IconRepo({ size = 15, ...p }: IconProps) {
  return (
    <svg {...base(size)} {...p}>
      <path
        d="M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H20v20H6.5a2.5 2.5 0 0 1 0-5H20"
        fill="currentColor"
        fillOpacity="0.08"
      />
      <path d="M8 7h6" />
      <path d="M8 11h4" />
    </svg>
  );
}

export function IconExternal({ size = 13, ...p }: IconProps) {
  return (
    <svg {...base(size)} {...p}>
      <path d="M7 17 17 7" />
      <path d="M8 7h9v9" />
    </svg>
  );
}

export function IconGitHub({ size = 14, ...p }: IconProps) {
  return (
    <svg {...base(size)} fill="currentColor" stroke="none" {...p}>
      <path d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.53 1.032 1.53 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0 1 12 6.844a9.59 9.59 0 0 1 2.504.337c1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.02 10.02 0 0 0 22 12.017C22 6.484 17.522 2 12 2Z" />
    </svg>
  );
}

export function IconGlobe({ size = 13, ...p }: IconProps) {
  return (
    <svg {...base(size)} {...p}>
      <circle cx="12" cy="12" r="9.5" />
      <path d="M12 2.5a14.5 14.5 0 0 0 0 19 14.5 14.5 0 0 0 0-19" />
      <path d="M2.5 12h19" />
    </svg>
  );
}

export function IconSort({ size = 13, ...p }: IconProps) {
  return (
    <svg {...base(size)} {...p}>
      <path d="m21 16-4 4-4-4" />
      <path d="M17 20V4" />
      <path d="m3 8 4-4 4 4" />
      <path d="M7 4v16" />
    </svg>
  );
}

export function IconChevronLeft({ size = 14, ...p }: IconProps) {
  return (
    <svg {...base(size)} {...p}>
      <path d="m15 18-6-6 6-6" />
    </svg>
  );
}

export function IconChevronRight({ size = 14, ...p }: IconProps) {
  return (
    <svg {...base(size)} {...p}>
      <path d="m9 18 6-6-6-6" />
    </svg>
  );
}

export function IconChevronDown({ size = 13, ...p }: IconProps) {
  return (
    <svg {...base(size)} {...p}>
      <path d="m6 9 6 6 6-6" />
    </svg>
  );
}

export function IconHistory({ size = 13, ...p }: IconProps) {
  return (
    <svg {...base(size)} {...p}>
      <path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8" />
      <path d="M3 3v5h5" />
      <path d="M12 7v5l3.5 2" />
    </svg>
  );
}

export function IconTrash({ size = 14, ...p }: IconProps) {
  return (
    <svg {...base(size)} {...p}>
      <path d="M3 6h18" />
      <path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6" />
      <path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2" />
    </svg>
  );
}

export function IconEdit({ size = 13, ...p }: IconProps) {
  return (
    <svg {...base(size)} {...p}>
      <path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z" />
      <path d="m15 5 4 4" />
    </svg>
  );
}

export function IconCopy({ size = 13, ...p }: IconProps) {
  return (
    <svg {...base(size)} {...p}>
      <rect width="13" height="13" x="9" y="9" rx="2" ry="2" fill="currentColor" fillOpacity="0.08" />
      <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
    </svg>
  );
}

export function IconDownload({ size = 13, ...p }: IconProps) {
  return (
    <svg {...base(size)} {...p}>
      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
      <polyline points="7 10 12 15 17 10" />
      <line x1="12" x2="12" y1="15" y2="3" />
    </svg>
  );
}

export function IconMaximize({ size = 14, ...p }: IconProps) {
  return (
    <svg {...base(size)} {...p}>
      <polyline points="15 3 21 3 21 9" />
      <polyline points="9 21 3 21 3 15" />
      <line x1="21" x2="14" y1="3" y2="10" />
      <line x1="3" x2="10" y1="21" y2="14" />
    </svg>
  );
}

export function IconMinimize({ size = 14, ...p }: IconProps) {
  return (
    <svg {...base(size)} {...p}>
      <polyline points="4 14 10 14 10 20" />
      <polyline points="20 10 14 10 14 4" />
      <line x1="14" x2="21" y1="10" y2="3" />
      <line x1="3" x2="10" y1="21" y2="14" />
    </svg>
  );
}

export function IconSidebar({ size = 13, ...p }: IconProps) {
  return (
    <svg {...base(size)} {...p}>
      <rect width="18" height="18" x="3" y="3" rx="2.5" />
      <path d="M15 3v18" />
    </svg>
  );
}

export function IconX({ size = 15, ...p }: IconProps) {
  return (
    <svg {...base(size)} {...p}>
      <path d="M18 6 6 18" />
      <path d="m6 6 12 12" />
    </svg>
  );
}

export function IconLoader({ size = 13, ...p }: IconProps) {
  return (
    <svg {...base(size)} className="spin" {...p}>
      <path d="M21 12a9 9 0 1 1-6.219-8.56" />
    </svg>
  );
}

export function IconCheck({ size = 13, ...p }: IconProps) {
  return (
    <svg {...base(size)} {...p}>
      <path d="M20 6 9 17l-5-5" />
    </svg>
  );
}

export function IconBookOpen({ size = 14, ...p }: IconProps) {
  return (
    <svg {...base(size)} {...p}>
      <path
        d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"
        fill="currentColor"
        fillOpacity="0.08"
      />
      <path
        d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"
        fill="currentColor"
        fillOpacity="0.08"
      />
    </svg>
  );
}

export function IconLayoutList({ size = 14, ...p }: IconProps) {
  return (
    <svg {...base(size)} {...p}>
      <rect width="7" height="5" x="3" y="4" rx="1" fill="currentColor" fillOpacity="0.12" />
      <rect width="7" height="5" x="3" y="15" rx="1" fill="currentColor" fillOpacity="0.12" />
      <path d="M14 5h7" />
      <path d="M14 8h5" />
      <path d="M14 16h7" />
      <path d="M14 19h5" />
    </svg>
  );
}

export function IconLayoutGrid({ size = 14, ...p }: IconProps) {
  return (
    <svg {...base(size)} {...p}>
      <rect width="7" height="7" x="3" y="3" rx="1.75" fill="currentColor" fillOpacity="0.12" />
      <rect width="7" height="7" x="14" y="3" rx="1.75" fill="currentColor" fillOpacity="0.12" />
      <rect width="7" height="7" x="14" y="14" rx="1.75" fill="currentColor" fillOpacity="0.12" />
      <rect width="7" height="7" x="3" y="14" rx="1.75" fill="currentColor" fillOpacity="0.12" />
    </svg>
  );
}

export function IconSun({ size = 14, ...p }: IconProps) {
  return (
    <svg {...base(size)} {...p}>
      <circle cx="12" cy="12" r="4" fill="currentColor" fillOpacity="0.16" />
      <path d="M12 2v2" />
      <path d="M12 20v2" />
      <path d="m4.93 4.93 1.41 1.41" />
      <path d="m17.66 17.66 1.41 1.41" />
      <path d="M2 12h2" />
      <path d="M20 12h2" />
      <path d="m6.34 17.66-1.41 1.41" />
      <path d="m19.07 4.93-1.41 1.41" />
    </svg>
  );
}

export function IconMoon({ size = 14, ...p }: IconProps) {
  return (
    <svg {...base(size)} {...p}>
      <path
        d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"
        fill="currentColor"
        fillOpacity="0.14"
      />
    </svg>
  );
}

export function IconBookmark({ size = 13, filled = false, ...p }: IconProps & { filled?: boolean }) {
  return (
    <svg {...base(size)} fill={filled ? "currentColor" : "none"} {...p}>
      <path d="m19 21-7-4-7 4V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2v16z" />
    </svg>
  );
}

export function IconTable({ size = 14, ...p }: IconProps) {
  return (
    <svg {...base(size)} {...p}>
      <rect width="18" height="18" x="3" y="3" rx="2.2" />
      <path d="M3 9h18" />
      <path d="M3 15h18" />
      <path d="M9 9v12" />
    </svg>
  );
}

export function IconShieldCheck({ size = 14, ...p }: IconProps) {
  return (
    <svg {...base(size)} {...p}>
      <path
        d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"
        fill="currentColor"
        fillOpacity="0.1"
      />
      <path d="m9 12 2 2 4-4" />
    </svg>
  );
}

export function IconActivity({ size = 14, ...p }: IconProps) {
  return (
    <svg {...base(size)} {...p}>
      <path d="M22 12h-4l-3 9L9 3l-3 9H2" />
    </svg>
  );
}

export function IconInfo({ size = 13, ...p }: IconProps) {
  return (
    <svg {...base(size)} {...p}>
      <circle cx="12" cy="12" r="9.5" />
      <path d="M12 16v-4" />
      <path d="M12 8h.01" />
    </svg>
  );
}
