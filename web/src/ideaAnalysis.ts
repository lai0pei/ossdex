import type { RepoDetail } from "./types";

export interface LicensePosture {
  level: "safe" | "caution" | "restrictive";
  badge: string;
  summary: string;
  saasAllowed: boolean;
  needsSourceBoundary: boolean;
}

export interface ProductPlaybook {
  title: string;
  type: "saas" | "extension" | "vertical" | "services";
  description: string;
  rationale: string;
}

export interface SingleRepoAnalysis {
  licensePosture: LicensePosture;
  forkRatioPct: number | null;
  deploymentSignal: string;
  velocitySignal: string;
  businessPrecedents: string[];
  playbooks: ProductPlaybook[];
  risks: string[];
}

export function getLicensePosture(kind: string | null | undefined): LicensePosture {
  const k = (kind || "none").toLowerCase();
  switch (k) {
    case "permissive":
      return {
        level: "safe",
        badge: "Commercial / SaaS Safe",
        summary: "Can be used in closed-source proprietary products and SaaS with no source disclosure requirements.",
        saasAllowed: true,
        needsSourceBoundary: false,
      };
    case "weak_copyleft":
      return {
        level: "caution",
        badge: "Weak Copyleft (File-Level)",
        summary: "Can be used in a SaaS or proprietary product if kept as an unmodified dependency or library; modifications to this library itself must remain open.",
        saasAllowed: true,
        needsSourceBoundary: true,
      };
    case "copyleft":
      return {
        level: "caution",
        badge: "Copyleft (GPL / Distribution)",
        summary: "Safe for internal SaaS backend execution without distribution, but distributing binaries requires open-sourcing the entire derivative work.",
        saasAllowed: true,
        needsSourceBoundary: true,
      };
    case "network_copyleft":
      return {
        level: "restrictive",
        badge: "Network Copyleft (AGPL)",
        summary: "Running over a network / SaaS triggers reciprocal source code release. Keep strictly behind an independent API/microservice boundary or obtain commercial license.",
        saasAllowed: false,
        needsSourceBoundary: true,
      };
    case "other":
      return {
        level: "restrictive",
        badge: "Source-Available / Custom",
        summary: "Source-available (e.g. BSL, SSPL) or custom terms usually restrict hosting as a competing paid service. Verify LICENSE terms carefully.",
        saasAllowed: false,
        needsSourceBoundary: true,
      };
    default:
      return {
        level: "restrictive",
        badge: "No Open Source License",
        summary: "All rights reserved. Cannot legally be incorporated, hosted, or modified without explicit copyright owner permission.",
        saasAllowed: false,
        needsSourceBoundary: true,
      };
  }
}

export function analyzeSingleRepo(r: RepoDetail): SingleRepoAnalysis {
  const licensePosture = getLicensePosture(r.license_kind);
  const stars = r.stars || 0;
  const forks = r.forks || 0;
  const forkRatioPct = stars > 0 ? parseFloat(((forks / stars) * 100).toFixed(1)) : null;

  const fn = (r.full_name || "").toLowerCase();
  const desc = (r.description || "").toLowerCase();
  const topics = (r.topics || []).map((t) => t.toLowerCase());
  const isAwesomeOrList =
    fn.includes("awesome") ||
    topics.includes("awesome") ||
    topics.includes("awesome-list") ||
    desc.includes("curated list") ||
    desc.includes("awesome list");
  const isCourseOrBook =
    topics.includes("course") ||
    topics.includes("tutorial") ||
    topics.includes("book") ||
    desc.includes("course") ||
    desc.includes("tutorial");
  const isTemplate = topics.includes("template") || topics.includes("boilerplate") || topics.includes("starter");

  let deploymentSignal = "Standard open-source library";
  if (isAwesomeOrList) {
    deploymentSignal = "Curated list / reference repository (not a deployable runtime service) [F1]";
  } else if (isCourseOrBook) {
    deploymentSignal = "Educational tutorial / guide (not a deployable service) [F1]";
  } else if (isTemplate) {
    deploymentSignal = "Starter template / boilerplate (developer scaffolding, not deployable SaaS) [F1]";
  } else if (forkRatioPct !== null) {
    if (forkRatioPct >= 18) {
      deploymentSignal = `Very high fork ratio (${forkRatioPct}%): signals active enterprise self-hosting, customization, and deployment workflows.`;
    } else if (forkRatioPct >= 10) {
      deploymentSignal = `Healthy fork ratio (${forkRatioPct}%): users frequently clone and adapt this project for production.`;
    } else {
      deploymentSignal = `Consumer/library fork ratio (${forkRatioPct}%): predominantly imported or consumed as a reference dependency.`;
    }
  }

  let velocitySignal = "Stable baseline activity";
  if (r.gain_1d && r.gain_1d > 10) {
    velocitySignal = `High breakout velocity: gained +${r.gain_1d.toLocaleString()} stars in the last 24h (daily).`;
  } else if (r.gain_7d && r.gain_7d > 50) {
    velocitySignal = `Sustained momentum: gained +${r.gain_7d.toLocaleString()} stars in the last 7 days (weekly).`;
  }

  const businessPrecedents: string[] = [];
  if (r.money?.signals) {
    for (const sig of r.money.signals) {
      businessPrecedents.push(sig.replace("_", " "));
    }
  }
  if (r.homepage && !businessPrecedents.includes("cloud website")) {
    businessPrecedents.push("external web product");
  }

  // Derive actionable product playbooks
  const playbooks: ProductPlaybook[] = [];

  if (licensePosture.saasAllowed) {
    if (isAwesomeOrList || isCourseOrBook) {
      playbooks.push({
        title: "Productized Directory & Industry Resource Hub",
        type: "vertical",
        description: `Turn this curated collection into an interactive directory with verified listings, submission tiers, and sponsor placements.`,
        rationale: "Reference lists cannot be hosted as compute software; monetize via distribution, sponsorship, and search.",
      });
    } else {
      playbooks.push({
        title: "Managed Cloud & Multi-Tenant SaaS",
        type: "saas",
        description: `Package ${r.full_name.split("/")[1]} as a turnkey cloud service with managed auth, automated backups, and team collaboration.`,
        rationale: `${licensePosture.badge} allows proprietary hosted services. Relieves teams from managing self-hosted infrastructure.`,
      });
    }
  }


  if (forkRatioPct && forkRatioPct >= 12 && !isAwesomeOrList && !isCourseOrBook) {
    playbooks.push({
      title: "Verticalized Turnkey Edition",
      type: "vertical",
      description: `Tailor ${r.full_name.split("/")[1]} for a specific high-value industry (e.g. Healthcare, Legal, FinTech, DevSecOps) with prebuilt templates and compliance.`,
      rationale: `High fork volume (${forkRatioPct}%) confirms companies are currently spending engineering hours customizing this themselves.`,
    });
  }

  if (playbooks.length < 2) {
    playbooks.push({
      title: "Self-Hosted Implementation & Support SLA",
      type: "services",
      description: `Offer enterprise onboarding, bespoke customization, and guaranteed SLA support around ${r.full_name}.`,
      rationale: "Low-overhead business model requiring no separate proprietary codebase to generate early revenue.",
    });
  }

  const risks: string[] = [];
  if (isAwesomeOrList || isCourseOrBook) {
    risks.push("Category warning (F1): Repository is reference content/documentation; cannot be deployed directly as standalone SaaS.");
  }
  const readmeLower = (r.readme_excerpt || "").toLowerCase();
  if (
    readmeLower.includes("openai_api_key") ||
    readmeLower.includes("anthropic_api_key") ||
    readmeLower.includes("pinecone_api_key")
  ) {
    risks.push("Runtime lock-in (F2): README references third-party cloud API keys. Evaluate upstream vendor cost & dependency risk.");
  }
  if (!licensePosture.saasAllowed) {
    risks.push(`License gate: ${licensePosture.badge} limits commercial closed hosting.`);
  }
  if (r.pushed_at) {
    const daysSincePush = Math.floor((Date.now() - new Date(r.pushed_at).getTime()) / (86400 * 1000));
    if (daysSincePush > 90) {
      risks.push(`Maintenance lag: last commit was ${daysSincePush} days ago.`);
    }
  }
  if (r.open_issues && r.open_issues > 500) {
    risks.push(`High issue backlog (${r.open_issues.toLocaleString()} open issues) may signal triaging friction.`);
  }

  return {
    licensePosture,
    forkRatioPct,
    deploymentSignal,
    velocitySignal,
    businessPrecedents,
    playbooks,
    risks,
  };
}

export function buildMcpSingleBrief(
  repo: RepoDetail,
  draft?: { title?: string; targetUser?: string; notes?: string }
): string {
  const analysis = analyzeSingleRepo(repo);
  const promptLines = [
    `# Product Idea Brief: ${draft?.title || repo.full_name}`,
    `**Base Repository**: https://github.com/${repo.full_name} (${repo.stars?.toLocaleString() ?? 0}★, ${repo.forks?.toLocaleString() ?? 0} forks)`,
    `**License**: ${repo.license || "None"} (${analysis.licensePosture.badge})`,
    `**Target User / Market**: ${draft?.targetUser || "Developers and teams needing a robust solution"}`,
    "",
    "## Validation & Market Signals",
    `- **Deployment Ratio**: ${analysis.deploymentSignal}`,
    `- **Velocity**: ${analysis.velocitySignal}`,
    `- **Commercial Signals**: ${analysis.businessPrecedents.length > 0 ? analysis.businessPrecedents.join(", ") : "None detected in README"}`,
    "",
    "## Candidate Product Angles",
    ...analysis.playbooks.map((p) => `- **${p.title}** (${p.type}): ${p.description}\n  *Rationale*: ${p.rationale}`),
    "",
    draft?.notes ? `## User Concept Notes\n${draft.notes}\n` : "",
    "## MCP Exploration Instructions",
    "Use the ossdex MCP tools to validate and deepen this product concept:",
    `1. \`get_repo(full_name="${repo.full_name}")\` for star history and full README preview.`,
    `2. \`find_similar(full_name="${repo.full_name}", license_kinds=["permissive"])\` to discover alternative components or competitors.`,
    `3. \`saas_base(idea="${draft?.title || repo.full_name}")\` to evaluate commercial packaging tradeoffs.`,
  ];

  return promptLines.filter(Boolean).join("\n");
}
