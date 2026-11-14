import type { RepoDetail, AlternativesResponse } from "./types";
import {
  analyzeSingleRepo,
  type SingleRepoAnalysis,
} from "./ideaAnalysis";

export interface PromptTemplate<TContext> {
  id: string;
  title: string;
  category: string;
  badge: string;
  summary: string;
  toolsUsed: string[];
  generate: (ctx: TContext) => string;
}

export interface SingleRepoPromptContext {
  repo: RepoDetail;
  analysis?: SingleRepoAnalysis;
  draft?: {
    title?: string;
    targetUser?: string;
    notes?: string;
  };
}

// -------------------------------------------------------------
// Single Repository Prompts (15 Prompts across 6 Categories)
// -------------------------------------------------------------

export const SINGLE_REPO_CATEGORIES = [
  "All",
  "Ideation & Brainstorming",
  "Learning & 80/20 Mastery",
  "SaaS & Monetization",
  "Architecture & Forking",
  "Market & Demand",
  "Services & Research",
] as const;

export const SINGLE_REPO_PROMPTS: PromptTemplate<SingleRepoPromptContext>[] = [
  // Flagship Ideation: What Can I Build? Product Idea Articulator
  {
    id: "idea-articulator",
    title: "What Can I Build? Product Idea Articulator",
    category: "Ideation & Brainstorming",
    badge: "Idea Articulation",
    summary:
      "Explore this repo with ossdex tools to discover, brainstorm, and articulate 5 concrete, commercially viable product/startup ideas.",
    toolsUsed: [
      "classify_artifact",
      "get_repo",
      "classify_issues",
      "get_demand",
      "get_commercial_landscape",
      "license_audit",
    ],
    generate: ({ repo, analysis, draft }) => {
      const a = analysis || analyzeSingleRepo(repo);
      const targetUser = draft?.targetUser || "";
      const notes = draft?.notes || "";
      const demandLine = a.demandHighlight.fetched
        ? `${a.demandHighlight.bounties} bounties, ${a.demandHighlight.helpWanted} help-wanted tickets`
        : `Uncollected (run \`ossdex demand ${repo.full_name}\`)`;

      return [
        `# Product Idea Articulation & Brainstorming: ${repo.full_name}`,
        `Act as an Elite Product Strategist and Open-Source Venture Scout.`,
        `Your mission: Explore repository **${repo.full_name}** and articulate **5 concrete, commercially viable product/startup ideas** that can be built on top of or around this project.`,
        "",
        "## Repository Context",
        `- **Anchor Repository**: https://github.com/${repo.full_name} (${(repo.stars || 0).toLocaleString()}★, ${(repo.forks || 0).toLocaleString()} forks)`,
        `- **Language & Topics**: ${repo.language || "Unknown"} · ${(repo.topics || []).slice(0, 6).join(", ") || "None"}`,
        `- **License Claim**: ${repo.license || "None"} (${a.licensePosture.badge})`,
        `- **Observed Community Demand**: ${demandLine}`,
        a.demandHighlight.topWish ? `- **Top Community Wish**: "${a.demandHighlight.topWish}"` : "",
        targetUser ? `- **Target Persona Hint**: ${targetUser}` : "",
        notes ? `- **User Inspiration / Focus**: ${notes}` : "",
        "",
        "## Tool-Assisted Discovery Workflow",
        "Execute the following ossdex MCP diagnostic tools to uncover real capabilities and unmet user pain:",
        `1. Run \`classify_artifact(full_name='${repo.full_name}')\` to determine the artifact kind (app vs library vs framework vs cli vs template) and viable SaaS shapes.`,
        `2. Run \`get_repo(full_name='${repo.full_name}')\` and \`get_readme_section(full_name='${repo.full_name}', query='architecture api installation configuration')\` to inspect capabilities and technical friction.`,
        `3. Run \`classify_issues(full_name='${repo.full_name}')\` and \`get_demand(full_name='${repo.full_name}')\` to extract real user pain clusters, feature requests, and monetizable complaints.`,
        `4. Run \`get_commercial_landscape(full_name='${repo.full_name}')\` and \`find_similar(full_name='${repo.full_name}')\` to see what paid products or competitors exist in this niche.`,
        `5. Run \`license_audit(full_name='${repo.full_name}')\` to ensure that closed/hosted commercialization is permitted.`,
        "",
        "## Required Output Deliverables",
        "Formulate **5 distinct, high-conviction product concepts** (e.g., Turnkey Multi-Tenant SaaS, Managed Cloud API, Vertical Industry Edition, Developer DX/GUI Plugin, Productized Workflow Automation).",
        "",
        "For EACH of the 5 product concepts, provide:",
        "1. **Product Name & One-Sentence Articulation**: 'An [X] for [Persona Y] that solves [Pain Z] without [Friction W]'.",
        "2. **Feasible Commercial Shape**: Must match the artifact's true nature (e.g. hosted service, API wrapper, IDE plugin, or VPC appliance).",
        "3. **The 80/20 Value Split**: Exactly what this open-source repo provides out-of-the-box (80%) vs. what proprietary value you build on top (20%).",
        "4. **Grounded Demand Evidence**: Which specific issue cluster, community wish, or README gap proves people will pay for this.",
        "5. **Monetization & Pricing Wedge**: Free tier vs. Entry tier ($29-$99/mo) vs. Enterprise tier ($500+/mo).",
        "6. **14-Day MVP Scope & Kill Test**: The single leanest slice to build and 1 falsifiable test to validate demand in 48 hours.",
      ].filter(Boolean).join("\n");
    },
  },

  // Category: Ideation & Brainstorming
  {
    id: "persona-use-case-matrix",
    title: "Buyer Persona & Industry Use-Case Brainstormer",
    category: "Ideation & Brainstorming",
    badge: "Use Cases",
    summary:
      "Map this repository into 4 high-value vertical industries and formulate tailored product concepts, buyer titles, and workflows for each.",
    toolsUsed: [
      "classify_artifact",
      "get_repo",
      "get_readme_section",
      "classify_issues",
    ],
    generate: ({ repo, analysis, draft }) => {
      const a = analysis || analyzeSingleRepo(repo);
      return [
        `# Buyer Persona & Vertical Use-Case Brainstorming: ${repo.full_name}`,
        `Act as an Enterprise Market Strategist.`,
        `Your goal: Take the horizontal technical capabilities of **${repo.full_name}** and brainstorm **4 high-ACV vertical industry applications** where enterprise buyers have urgent budget.`,
        "",
        "## Base Project Data",
        `- **Repository**: https://github.com/${repo.full_name} (${(repo.stars || 0).toLocaleString()}★, ${(repo.forks || 0).toLocaleString()} forks)`,
        `- **Primary Language**: ${repo.language || "code"}`,
        `- **License**: ${repo.license || "None"} (${a.licensePosture.badge})`,
        `- **Deployment Signals**: ${a.deploymentSignal}`,
        draft?.notes ? `- **Domain Notes**: ${draft.notes}` : "",
        "",
        "## Tool-Assisted Investigation",
        `1. Run \`get_repo(full_name='${repo.full_name}')\` and \`get_readme_section(full_name='${repo.full_name}', query='features use-cases examples')\` to review core capabilities.`,
        `2. Run \`classify_issues(full_name='${repo.full_name}')\` to look for enterprise requests around security, auth, integrations, and compliance.`,
        "",
        "## Output Deliverables",
        "Formulate 4 non-obvious vertical market applications (e.g. FinTech / Wealth Management, Healthcare / BioTech, DevSecOps / Cloud Security, E-Commerce / Retail, LegalTech).",
        "",
        "For each vertical, articulate:",
        "1. **Target Buyer Persona**: Specific job title (e.g. VP of Security, Head of Claims Processing, Lead ML Engineer).",
        "2. **Painful Workflow Today**: How they currently solve this problem and what makes it slow, risky, or expensive.",
        "3. **Tailored Product Pitch**: How this repo is packaged into a solution tailored to their exact vocabulary and workflow.",
        "4. **Required Vertical Connectors & Compliance**: Mandatory domain standards (e.g., HIPAA, SOC2, PCI-DSS, FHIR, ERP/CRM hooks).",
        "5. **Estimated ACV (Annual Contract Value)**: Realistic price point ($10k-$50k/year) and ROI justification.",
      ].filter(Boolean).join("\n");
    },
  },

  // Category: Learning & 80/20 Mastery
  {
    id: "pareto-80-20-mastery",
    title: "80/20 Repo Mastery & Prerequisite Guide",
    category: "Learning & 80/20 Mastery",
    badge: "80/20 Learn",
    summary:
      "Learn what knowledge you need before starting, the 20% high-value core that delivers 80% of capabilities, what noise to skip, and a 60-minute fast-track lab.",
    toolsUsed: [
      "classify_artifact",
      "get_repo",
      "get_readme_section",
      "get_runtime_dependencies",
      "classify_issues",
    ],
    generate: ({ repo, draft }) => {
      const userBg = draft?.targetUser || draft?.notes ? `\n- **Learner Context / Background**: ${draft?.targetUser || draft?.notes}` : "";

      return [
        `# Pareto 80/20 Repo Mastery & Prerequisite Guide: ${repo.full_name}`,
        `Act as an Elite Principal Engineer and Technical Mentor.`,
        `Your mission: Help a developer master and practically use **${repo.full_name}** using the **Pareto 80/20 Rule**.`,
        `Focus relentlessly on the **20% core knowledge and abstractions that deliver 80% of real-world results**, while explicitly filtering out the 80% edge-case noise that slows beginners down.`,
        "",
        "## Repository Baseline",
        `- **Repository**: https://github.com/${repo.full_name} (${(repo.stars || 0).toLocaleString()}★, ${(repo.forks || 0).toLocaleString()} forks)`,
        `- **Language**: ${repo.language || "Unknown"}`,
        `- **Topics**: ${(repo.topics || []).slice(0, 8).join(", ") || "None listed"}`,
        `- **License**: ${repo.license || "None"}${userBg}`,
        "",
        "## Tool-Assisted Investigation Instructions",
        "Execute the following ossdex MCP tools to inspect this codebase:",
        `1. Run \`classify_artifact(full_name='${repo.full_name}')\` to determine the artifact kind (library, CLI, web app, framework, or template) and deployment profile.`,
        `2. Run \`get_repo(full_name='${repo.full_name}')\` and \`get_readme_section(full_name='${repo.full_name}', query='quickstart installation usage getting-started example api')\` to extract primary entry points and recommended DX.`,
        `3. Run \`get_runtime_dependencies(full_name='${repo.full_name}')\` to check required API keys, cloud backends, database engines, or system tools.`,
        `4. Run \`classify_issues(full_name='${repo.full_name}')\` to examine common real-world installation and environment friction clusters.`,
        "",
        "## Required Output Deliverables",
        "",
        "### 1. Prerequisite Knowledge Checklist (What Do I Need to Know?)",
        "Split into two strict lists:",
        "- **Must-Know Before Starting (The 20%)**: 2–4 foundational concepts, language syntax idioms, or runtime primitives without which the user will get immediately stuck.",
        "- **Learn On Demand Later (The 80%)**: Secondary topics, deep internals, advanced design patterns, or niche protocols that can safely be looked up later.",
        "",
        "### 2. The 20% High-Value Core (Learn This First)",
        "Identify the **3 to 5 core abstractions, APIs, classes, or CLI commands** that unlock 80% of what this repository actually does in production. For each core piece, explain:",
        "- What it is and why it's the high-leverage entry point.",
        "- A minimal, clean 5–10 line code snippet or CLI invocation showing its canonical usage.",
        "",
        "### 3. The 80% Noise (Safely Skip Initially)",
        "Explicitly list the 3–5 features, configuration flags, secondary adapters, legacy options, or advanced internal modules that beginners waste hours trying to learn but rarely need on Day 1.",
        "",
        "### 4. 60-Minute Hands-On Fast-Track Lab",
        "A minute-by-minute practical roadmap to get running and producing real output:",
        "- **Mins 0–15 (Environment & Dependencies)**: Exact runtime setup, dependency install commands, and environment variables verification.",
        "- **Mins 15–35 (First Working Execution)**: Running the simplest 'Hello World' or primary workflow, and inspecting the generated output.",
        "- **Mins 35–60 (First Custom Modification)**: Modifying a core parameter, writing a small wrapper function, or testing a custom input to prove practical understanding.",
        "",
        "### 5. Top 3 Beginner Pitfalls & Environment Traps",
        "Based on real GitHub issue patterns (`classify_issues`), highlight the 3 most common stumbling blocks (e.g. missing API keys, Python/Node version conflicts, OS-specific binaries, docker permissions) and provide the exact prevention/fix for each.",
      ].filter(Boolean).join("\n");
    },
  },

  {
    id: "codebase-mental-model",
    title: "Codebase Mental Model & Extension Walkthrough",
    category: "Learning & 80/20 Mastery",
    badge: "Mental Model",
    summary:
      "Build an architectural mental model of the codebase, pinpoint the top 20% files/directories to read first, and map clean extension points.",
    toolsUsed: [
      "classify_artifact",
      "get_repo",
      "get_readme_section",
      "analyze_forks",
    ],
    generate: ({ repo, draft }) => {
      const userBg = draft?.notes ? `\n- **Customization Goal**: ${draft.notes}` : "";

      return [
        `# Codebase Mental Model & Extension Walkthrough: ${repo.full_name}`,
        `Act as the Lead Architect of **${repo.full_name}**.`,
        `Your mission: Give a developer a clear mental model of how this codebase works, where data flows, which files to read first, and how to safely extend it without breaking upstream compatibility.`,
        "",
        "## Repository Context",
        `- **Repository**: https://github.com/${repo.full_name} (${(repo.stars || 0).toLocaleString()}★, ${(repo.forks || 0).toLocaleString()} forks)`,
        `- **Primary Language**: ${repo.language || "code"}${userBg}`,
        "",
        "## Tool-Assisted Investigation Instructions",
        `1. Run \`classify_artifact(full_name='${repo.full_name}')\` to review architecture and host ecosystem.`,
        `2. Run \`get_repo(full_name='${repo.full_name}')\` and \`get_readme_section(full_name='${repo.full_name}', query='architecture design components overview data-flow')\` to inspect architectural documentation.`,
        `3. Run \`analyze_forks(full_name='${repo.full_name}')\` to see whether forks modify deployment configs, UI, or core algorithms.`,
        "",
        "## Required Output Deliverables",
        "",
        "### 1. System Mental Model & Data Flow",
        "- Provide a concise mental model of how the system processes input: Input &rarr; Validation &rarr; Core Engine &rarr; State / Storage &rarr; Output.",
        "- Include a clean Mermaid flowchart or sequence diagram summarizing the component interactions.",
        "",
        "### 2. Top 20% Codebase Tour (5 Essential Files / Modules)",
        "Rank the top 5 most important directories, files, or classes to inspect first in order of reading (1 &rarr; 5):",
        "- For each file: file path / name, its single responsibility in the system, and what key pattern or function to observe.",
        "",
        "### 3. Clean Extension Seams",
        "How to add new capabilities, plugins, or custom logic cleanly:",
        "- Identify the official plugin interface, middleware pipeline, or subclassing points.",
        "- How to extend it *without* modifying core files so you can easily pull upstream git updates.",
        "",
        "### 4. 30-Minute Customization Challenge",
        "- A concrete, self-contained mini-challenge (e.g. 'Add a custom logging middleware', 'Plug in a new parser', or 'Expose a custom CLI flag') to prove you have mastered the codebase.",
      ].filter(Boolean).join("\n");
    },
  },

  // Flagship Audit: Product Idea Brief Evaluator (F1-F10)
  {
    id: "evaluate-brief",
    title: "Product Idea Brief Evaluator (F1–F10)",
    category: "SaaS & Monetization",
    badge: "F1–F10 Audit",
    summary:
      "Run evidence-based evaluation of a Product Idea Brief against the 10 commercialization failure modes (F1-F10) to verify claims and produce a pursue/narrow/reject verdict.",
    toolsUsed: [
      "classify_artifact",
      "get_runtime_dependencies",
      "classify_growth",
      "analyze_forks",
      "get_package_adoption",
      "classify_issues",
      "get_commercial_landscape",
      "check_name_collision",
      "license_audit",
      "platform_compat",
      "evaluate_brief",
    ],
    generate: ({ repo, analysis, draft }) => {
      const a = analysis || analyzeSingleRepo(repo);
      const targetUser = draft?.targetUser || "Technical teams & enterprises";
      const notes = draft?.notes || "Turnkey managed edition with team workspace & SSO";
      const demandLine = a.demandHighlight.fetched
        ? `${a.demandHighlight.bounties} bounties, ${a.demandHighlight.helpWanted} help-wanted tickets`
        : `Uncollected (run \`ossdex demand ${repo.full_name}\`)`;

      return [
        `Evaluate the following Product Idea Brief for repository: ${repo.full_name}.`,
        "",
        "### Proposed Product Brief",
        `- **Anchor Repository**: ${repo.full_name} (${(repo.stars || 0).toLocaleString()}★, ${(repo.forks || 0).toLocaleString()} forks)`,
        `- **License Claim**: ${repo.license || "None"} (${a.licensePosture.badge})`,
        `- **Proposed Target User**: ${targetUser}`,
        `- **Proposed Commercial Angle**: ${notes}`,
        `- **Observed Community Demand**: ${demandLine}`,
        "",
        "### Verification Workflow (Preventing F1–F10 Failure Modes)",
        "Please invoke the ossdex MCP diagnostic tools in sequence:",
        `1. **F1 & F10 (Category Error & Provenance)**: Call \`classify_artifact(full_name='${repo.full_name}')\`. Confirm whether it is a deployable app, library, template, or awesome-list, and which SaaS shapes are feasible.`,
        `2. **F2 (Hidden Lock-In)**: Call \`get_runtime_dependencies(full_name='${repo.full_name}')\`. Audit required upstream APIs, backends, or vendor credentials and evaluate lock-in risk.`,
        `3. **F3 (Velocity Misread)**: Call \`classify_growth(full_name='${repo.full_name}', days=60)\`. Distinguish launch spikes from sustained momentum; inspect half-life and 30-day projection.`,
        `4. **F4 (Fork Misread)**: Call \`analyze_forks(full_name='${repo.full_name}')\` and \`get_package_adoption(full_name='${repo.full_name}')\` to verify genuine production customization vs template copies.`,
        `5. **F5 (Commercial Precedent)**: Call \`get_commercial_landscape(full_name='${repo.full_name}')\` and \`get_company_events(full_name='${repo.full_name}')\` to audit existing paid vendors and funding history.`,
        `6. **F6 (Name Collision)**: Call \`check_name_collision(name='${repo.full_name.split("/")[1]}')\` to spot conflicting repos or trademarks.`,
        `7. **F7 (License Audit)**: Call \`license_audit(full_name='${repo.full_name}')\` to verify system binaries (e.g. ffmpeg), model weights, and reciprocal copyleft gates.`,
        `8. **F8 (Platform Compatibility)**: Call \`platform_compat(full_name='${repo.full_name}')\` to test serverless, GPU, and persistent disk constraints.`,
        `9. **F9 (Demand Clustering)**: Call \`classify_issues(full_name='${repo.full_name}')\` and \`get_demand(full_name='${repo.full_name}')\` to identify monetizable pain clusters without false-zero assumptions.`,
        `10. **Composite Synthesis**: Call \`evaluate_brief(full_name='${repo.full_name}', angles=['saas', 'services', 'vertical', 'plugin'])\`.`,
        "",
        "### Required Output Deliverables",
        "1. **Signal Verdict**: Clear verdict (`pursue`, `narrow`, or `reject`) with corrected assumptions.",
        "2. **Angle Assessment**: Scored viable commercial shapes (SaaS, managed API, vertical edition, or services) and specific blockers.",
        "3. **Recommended Wedge**: The single sharpest entry-point product offer.",
        "4. **Concrete Kill Tests**: 2 falsifiable tests to run within 48 hours before committing capital.",
      ].join("\n");
    },
  },
  // Category: SaaS & Monetization
  {
    id: "managed-cloud",
    title: "Managed Cloud SaaS Wrapper",
    category: "SaaS & Monetization",
    badge: "SaaS",
    summary:
      "Turn this open-source tool into a turnkey multi-tenant SaaS with authentication, managed infrastructure, and team billing.",
    toolsUsed: ["get_repo", "find_similar", "saas_base"],
    generate: ({ repo, analysis, draft }) => {
      const a = analysis || analyzeSingleRepo(repo);
      return [
        `# Product Idea: Managed Cloud SaaS Wrapper for ${repo.full_name}`,
        `**Base Repository**: https://github.com/${repo.full_name} (${repo.stars?.toLocaleString() ?? 0}★, ${repo.forks?.toLocaleString() ?? 0} forks)`,
        `**License**: ${repo.license || "None"} (${a.licensePosture.badge})`,
        `**Proposed Product**: ${draft?.title || `Cloud edition of ${repo.full_name.split("/")[1]}`}`,
        `**Target Customer**: ${draft?.targetUser || "Teams and businesses that want this capability without self-hosting operations"}`,
        "",
        "## Validation & Architecture Signals",
        `- **License Gate**: ${a.licensePosture.summary}`,
        `- **Deployment Signal**: ${a.deploymentSignal}`,
        `- **Growth Velocity**: ${a.velocitySignal}`,
        `- **Commercial Precedents**: ${a.businessPrecedents.length > 0 ? a.businessPrecedents.join(", ") : "None detected in README"}`,
        draft?.notes ? `\n## User Product Notes\n${draft.notes}\n` : "",
        "## MCP Client Instructions",
        "Act as a Principal Product Architect. Run the following ossdex MCP tools to validate and design the hosted SaaS product:",
        `1. Execute \`get_repo(full_name="${repo.full_name}")\` to inspect recent star velocity, releases, and README dependencies.`,
        `2. Execute \`find_similar(full_name="${repo.full_name}", license_kinds=["permissive"])\` to map alternative engines or competitor products.`,
        `3. Execute \`saas_base(idea="${draft?.title || repo.full_name}", language="${repo.language || ""}")\` to evaluate commercial hosting considerations.`,
        "",
        "## Output Deliverables",
        "- **Value Proposition**: Why users will pay $29-$199/month rather than self-host (e.g. 1-click deploys, automated upgrades, SOC2/SSO, managed storage).",
        "- **Technical SaaS Architecture**: How to wrap the open-source backend with a multi-tenant API gateway, tenant database isolation, and billing (Stripe).",
        "- **Pricing & Packaging Matrix**: Free self-hosted tier vs. Managed Cloud Starter vs. Business Team tier.",
        "- **Go-To-Market Wedge**: Where early users hang out and how to convert existing self-hosters into paid cloud subscribers.",
      ]
        .filter(Boolean)
        .join("\n");
    },
  },

  {
    id: "vertical-saas",
    title: "Vertical Industry Edition",
    category: "SaaS & Monetization",
    badge: "Vertical",
    summary:
      "Specialize this project for an underserved vertical (FinTech, Healthcare, Legal, Cyber) with compliance and prebuilt workflows.",
    toolsUsed: ["get_repo", "get_demand", "saas_base"],
    generate: ({ repo, analysis, draft }) => {
      const a = analysis || analyzeSingleRepo(repo);
      return [
        `# Product Idea: Vertical Industry Edition for ${repo.full_name}`,
        `**Base Repository**: https://github.com/${repo.full_name} (${repo.stars?.toLocaleString() ?? 0}★, ${repo.language || "code"})`,
        `**License**: ${repo.license || "None"} (${a.licensePosture.badge})`,
        `**Vertical Concept**: ${draft?.title || `Verticalized ${repo.full_name.split("/")[1]}`}`,
        `**Target Industry & Buyer**: ${draft?.targetUser || "Regulated enterprises (Healthcare, Legal, Financial Services, or Defense)"}`,
        "",
        "## Market Signals",
        `- **Fork Volume**: ${a.forkRatioPct != null ? `${a.forkRatioPct}% forks to stars ratio` : "N/A"} (${a.deploymentSignal})`,
        `- **Community Demand**: ${a.demandHighlight.fetched ? `${a.demandHighlight.bounties} bounties, ${a.demandHighlight.helpWanted} help-wanted tickets` : `Uncollected (run \`ossdex demand ${repo.full_name}\`)`}`,
        draft?.notes ? `\n## Context & Domain Specifics\n${draft.notes}\n` : "",
        "## MCP Client Instructions",
        "Use the ossdex MCP server to uncover industry pain points and design a high-ACV vertical SaaS:",
        `1. Run \`get_demand(full_name="${repo.full_name}")\` to inspect feature requests around compliance, security, audit trails, and data sovereignty.`,
        `2. Run \`get_repo(full_name="${repo.full_name}")\` to check whether enterprise money signals or integrations already exist.`,
        "",
        "## Output Deliverables",
        "- **Target Vertical Fit**: Specific industry workflows and regulations (HIPAA, GDPR, SOC2, FINRA) addressed.",
        "- **Differentiating Moat**: Prebuilt templates, schemas, and compliance connectors that general-purpose tools do not provide.",
        "- **Enterprise Packaging**: On-prem / VPC private deployment options alongside cloud SaaS.",
        "- **Sales Strategy**: Inbound content and partner-channel strategy to close \$10k-\$50k annual contracts.",
      ]
        .filter(Boolean)
        .join("\n");
    },
  },

  {
    id: "open-core-gate",
    title: "Open-Core & Enterprise Gate Split",
    category: "SaaS & Monetization",
    badge: "Open-Core",
    summary:
      "Define what remains open-source in the community edition vs. what gets gated into a paid enterprise license.",
    toolsUsed: ["get_repo", "get_readme_section"],
    generate: ({ repo, analysis, draft }) => {
      const a = analysis || analyzeSingleRepo(repo);
      return [
        `# Product Strategy: Open-Core Feature Gate Split for ${repo.full_name}`,
        `**Base Repository**: https://github.com/${repo.full_name} (${repo.stars?.toLocaleString() ?? 0}★)`,
        `**License**: ${repo.license || "None"} (${a.licensePosture.badge})`,
        `**Product Goal**: ${draft?.title || "Commercial Open-Core Offering"}`,
        "",
        "## Base Technical Posture",
        `- **License Terms**: ${a.licensePosture.summary}`,
        `- **Commercial Hints**: ${a.businessPrecedents.join(", ") || "Community baseline"}`,
        draft?.notes ? `\n## Notes & Existing Modules\n${draft.notes}\n` : "",
        "## MCP Client Instructions",
        `1. Run \`get_readme_section(full_name="${repo.full_name}", query="features architecture plugins extensions")\` to map the codebase's modular boundaries.`,
        `2. Run \`get_repo(full_name="${repo.full_name}")\` to verify the exact license terms and contributors.`,
        "",
        "## Output Deliverables",
        "- **Community Edition (Open Source)**: Core engine, single-user/developer experience, standard CLI/API, self-hosting documentation.",
        "- **Enterprise Edition (Proprietary / Paid License)**: SSO/SAML 2.0, SCIM provisioning, RBAC & granular permissions, immutable audit logs, team workspaces, multi-region sync.",
        "- **Licensing Model**: Dual-licensing (AGPL + Commercial) vs. Open-Core (Apache 2.0 core + proprietary enterprise extension modules).",
        "- **Pricing Structure**: Developer Free vs. Pro (\$20/seat) vs. Enterprise (\$50+/seat + dedicated support).",
      ]
        .filter(Boolean)
        .join("\n");
    },
  },

  {
    id: "paid-extension",
    title: "Paid Plugin & Bounty Monetization",
    category: "SaaS & Monetization",
    badge: "Extension",
    summary:
      "Capitalize on unmet community demand by building a paid connector, plugin, or enterprise integration.",
    toolsUsed: ["get_demand", "get_repo"],
    generate: ({ repo, analysis, draft }) => {
      const a = analysis || analyzeSingleRepo(repo);
      return [
        `# Product Strategy: Paid Plugin & Commercial Extension for ${repo.full_name}`,
        `**Base Repository**: https://github.com/${repo.full_name} (${repo.stars?.toLocaleString() ?? 0}★)`,
        `**Unmet Demand Signals**: ${a.demandHighlight.fetched ? `${a.demandHighlight.bounties} bounties, ${a.demandHighlight.helpWanted} help-wanted tickets` : `Uncollected (run \`ossdex demand ${repo.full_name}\`)`}`,
        a.demandHighlight.topWish ? `**Top Requested Community Feature**: "${a.demandHighlight.topWish}"` : "",
        draft?.notes ? `\n## User Notes\n${draft.notes}\n` : "",
        "## MCP Client Instructions",
        `1. Run \`get_demand(full_name="${repo.full_name}")\` to inspect the top-upvoted feature requests and issues with reactions and comments.`,
        `2. Run \`get_repo(full_name="${repo.full_name}")\` to see if an official marketplace or plugin architecture exists.`,
        "",
        "## Output Deliverables",
        "- **Highest-ROI Extension Idea**: The single most requested plugin/connector based on verified community demand.",
        "- **Integration Architecture**: How the extension hooks into the base project without maintaining a fork.",
        "- **Distribution & Monetization**: One-time license key vs. monthly subscription vs. marketplace revenue share.",
        "- **Validation Plan**: How to reach out directly to the issue upvoters and bounty posters with an MVP preview.",
      ]
        .filter(Boolean)
        .join("\n");
    },
  },

  // Category: Architecture & Forking
  {
    id: "fork-rebrand",
    title: "Fork, Rebrand & White-Label Audit",
    category: "Architecture & Forking",
    badge: "Rebrand",
    summary:
      "Create a white-label derivative product by safely forking, stripping upstream branding, and setting up merge sync.",
    toolsUsed: ["get_repo", "get_readme_section"],
    generate: ({ repo, analysis, draft }) => {
      const a = analysis || analyzeSingleRepo(repo);
      return [
        `# Technical Plan: Fork, Rebrand & White-Label Audit for ${repo.full_name}`,
        `**Upstream Repository**: https://github.com/${repo.full_name} (${repo.license || "No license"} - ${a.licensePosture.badge})`,
        `**New Product Identity**: ${draft?.title || "White-labeled Derivative Product"}`,
        `**Target Buyer**: ${draft?.targetUser || "B2B customers requiring customized branded portals"}`,
        "",
        "## Legal & Maintenance Posture",
        `- **License Verdict**: ${a.licensePosture.summary}`,
        `- **Upstream Maintenance**: Last pushed ${repo.pushed_at || "unknown"}. Risks: ${a.risks.join("; ") || "None highlighted"}.`,
        draft?.notes ? `\n## User Notes\n${draft.notes}\n` : "",
        "## MCP Client Instructions",
        `1. Run \`get_repo(full_name="${repo.full_name}")\` to review the full license text and repository metadata.`,
        `2. Run \`get_readme_section(full_name="${repo.full_name}", query="contributing license trademark building")\` to check for trademark guidelines and build instructions.`,
        "",
        "## Output Deliverables",
        "- **Trademark & Copyright Compliance**: How to preserve required copyright notices while renaming and removing upstream trademarks/logos.",
        "- **Codebase Rebranding Checklist**: Front-end assets, UI color schemes, API endpoints, package names, and telemetry/analytics stripping.",
        "- **Upstream Merge Maintenance Strategy**: Git branching strategy (upstream tracking branch) to pull security patches without breaking customizations.",
      ]
        .filter(Boolean)
        .join("\n");
    },
  },

  {
    id: "license-boundary",
    title: "License Compliance & Clean-Room Boundary",
    category: "Architecture & Forking",
    badge: "Compliance",
    summary:
      "Architect a clean microservice/API boundary to safely consume copyleft/AGPL or restrictive components without source disclosure.",
    toolsUsed: ["get_repo", "find_similar"],
    generate: ({ repo, analysis, draft }) => {
      const a = analysis || analyzeSingleRepo(repo);
      return [
        `# Architecture Spec: Clean-Room Boundary & License Isolation for ${repo.full_name}`,
        `**Component Repository**: https://github.com/${repo.full_name} (${repo.license || "None"})`,
        `**License Posture**: ${a.licensePosture.level.toUpperCase()} - ${a.licensePosture.badge}`,
        `**Rule**: ${a.licensePosture.summary}`,
        draft?.notes ? `\n## Integration Context\n${draft.notes}\n` : "",
        "## MCP Client Instructions",
        `1. Run \`get_repo(full_name="${repo.full_name}")\` to review license kind and dependency structure.`,
        `2. Run \`find_similar(full_name="${repo.full_name}", license_kinds=["permissive"])\` to discover permissive drop-in alternatives if boundary isolation is too costly.`,
        "",
        "## Output Deliverables",
        "- **Architectural Isolation Boundary**: Network protocol (gRPC / REST / message queue / CLI sub-process) isolating this component from proprietary code.",
        "- **Distribution vs. Network SaaS Risk Analysis**: Exact triggers for copyleft obligations and how the proposed boundary mitigates them.",
        "- **Permissive Alternative Comparison**: Tradeoffs of keeping this component behind a boundary vs. switching to a permissive alternative.",
      ]
        .filter(Boolean)
        .join("\n");
    },
  },

  // Category: Market & Demand
  {
    id: "demand-roadmap",
    title: "Unmet Demand & Pain-Point MVP",
    category: "Market & Demand",
    badge: "MVP Wedge",
    summary:
      "Mine community upvotes, feature requests, and complaints to define a sharp 30-day MVP product roadmap.",
    toolsUsed: ["get_demand", "get_repo"],
    generate: ({ repo, analysis, draft }) => {
      const a = analysis || analyzeSingleRepo(repo);
      return [
        `# Product Roadmap: Unmet Demand & Pain-Point MVP for ${repo.full_name}`,
        `**Base Repository**: https://github.com/${repo.full_name} (${repo.stars?.toLocaleString() ?? 0}★, ${repo.open_issues?.toLocaleString() ?? 0} open issues)`,
        `**Top Community Wish**: ${a.demandHighlight.topWish || "See demand issues"}`,
        `**Bounties & Help Wanted**: ${a.demandHighlight.fetched ? `${a.demandHighlight.bounties} bounties, ${a.demandHighlight.helpWanted} help-wanted tickets` : `Uncollected (run \`ossdex demand ${repo.full_name}\`)`}`,
        draft?.notes ? `\n## User Notes\n${draft.notes}\n` : "",
        "## MCP Client Instructions",
        `1. Execute \`get_demand(full_name="${repo.full_name}")\` to inspect the top issues ranked by user reactions and comments.`,
        `2. Execute \`get_repo(full_name="${repo.full_name}")\` to check recent commit cadence and issue triage responsiveness.`,
        "",
        "## Output Deliverables",
        "- **Top 3 Core User Frustrations**: What real users complain about most frequently in the issue tracker.",
        "- **30-Day MVP Scope**: The leanest standalone product or wrapper that solves these top 3 frustrations.",
        "- **User Feedback Loop**: How to contact the users who reported or upvoted these issues to recruit design partners.",
      ]
        .filter(Boolean)
        .join("\n");
    },
  },

  {
    id: "competitive-moat",
    title: "Competitive Matrix & Positioning Wedge",
    category: "Market & Demand",
    badge: "Moat",
    summary:
      "Benchmark against closest open-source competitors and commercial incumbents to find an underserved positioning gap.",
    toolsUsed: ["find_similar", "compare_repos"],
    generate: ({ repo, analysis, draft }) => {
      const a = analysis || analyzeSingleRepo(repo);
      return [
        `# Market Analysis: Competitive Moat & Positioning Wedge for ${repo.full_name}`,
        `**Target Project**: https://github.com/${repo.full_name} (${repo.stars?.toLocaleString() ?? 0}★, ${repo.language || "code"})`,
        `**Market Context**: ${draft?.title || "Competitive Positioning"}`,
        `**Target Buyer**: ${draft?.targetUser || "Teams choosing between open-source and proprietary platforms"}`,
        "",
        "## Known Signals",
        `- **Velocity**: ${a.velocitySignal}`,
        `- **Commercial Hints**: ${a.businessPrecedents.join(", ") || "None"}`,
        draft?.notes ? `\n## Strategy Notes\n${draft.notes}\n` : "",
        "## MCP Client Instructions",
        `1. Run \`find_similar(full_name="${repo.full_name}", limit=6)\` to find the 5 closest alternative open-source projects.`,
        `2. Run \`compare_repos(full_names=["${repo.full_name}", ...top_alternatives])\` to compare star velocity, fork ratios, and open issues side-by-side.`,
        "",
        "## Output Deliverables",
        "- **Feature Comparison Matrix**: Strengths, weaknesses, and architectural differences across all compared projects.",
        "- **Positioning Wedge**: The specific niche (e.g. 10x faster setup, edge deployment, compliance-first, local-first) where you can win.",
        "- **Defensibility & Moat**: What prevents upstream or other competitors from quickly copying this angle.",
      ]
        .filter(Boolean)
        .join("\n");
    },
  },

  // Category: Services & Research
  {
    id: "agency-retainer",
    title: "Productized Agency & Managed Support SLA",
    category: "Services & Research",
    badge: "Services",
    summary:
      "Package high-ticket implementation, migration, and 24/7 SLA support retainers for enterprises deploying this project.",
    toolsUsed: ["get_repo", "get_demand"],
    generate: ({ repo, analysis, draft }) => {
      const a = analysis || analyzeSingleRepo(repo);
      return [
        `# Business Offer: Productized Agency & Support SLA for ${repo.full_name}`,
        `**Ecosystem Platform**: https://github.com/${repo.full_name} (${repo.stars?.toLocaleString() ?? 0}★, ${repo.forks?.toLocaleString() ?? 0} forks)`,
        `**Fork Ratio**: ${a.forkRatioPct != null ? `${a.forkRatioPct}%` : "N/A"} (${a.deploymentSignal})`,
        `**Offer Goal**: High-margin productized services and enterprise SLA retainers`,
        draft?.notes ? `\n## Notes\n${draft.notes}\n` : "",
        "## MCP Client Instructions",
        `1. Run \`get_repo(full_name="${repo.full_name}")\` to inspect commercial signals, funding, and enterprise adoption.`,
        `2. Run \`get_demand(full_name="${repo.full_name}")\` to identify common deployment hurdles and help-wanted tickets.`,
        "",
        "## Output Deliverables",
        "- **Tier 1: Turnkey Deployment Package (\$3,000 - \$7,500 one-off)**: Hardened deployment, SSO configuration, custom branding, and automated backups.",
        "- **Tier 2: Monthly Support SLA Retainer (\$1,000 - \$4,000/month)**: Guaranteed 4-hour response time, security patching, and capacity planning.",
        "- **Tier 3: Bespoke Custom Integrations (\$150 - \$250/hour)**: Custom plugin, CRM/ERP connectors, and data pipeline authoring.",
        "- **Client Acquisition Script**: Cold outreach template to companies hiring or actively building on this tech stack.",
      ]
        .filter(Boolean)
        .join("\n");
    },
  },

  {
    id: "paper-to-product",
    title: "Research Paper to Commercial API/SDK",
    category: "Services & Research",
    badge: "Research",
    summary:
      "Transform an academic paper or algorithm into a production-grade, developer-friendly API or SDK product.",
    toolsUsed: ["get_repo", "get_readme_section"],
    generate: ({ repo, analysis, draft }) => {
      const a = analysis || analyzeSingleRepo(repo);
      const papers = repo.papers || [];
      const paperText =
        papers.length > 0
          ? papers.map((p) => `- [${p.title || p.arxiv_id}](${p.url}) (arXiv:${p.arxiv_id})`).join("\n")
          : "No linked arXiv papers detected in README.";

      return [
        `# Product Strategy: Research Paper to Commercial API/SDK for ${repo.full_name}`,
        `**Repository**: https://github.com/${repo.full_name} (${repo.stars?.toLocaleString() ?? 0}★, ${a.licensePosture.badge})`,
        `**Referenced Academic Papers**:\n${paperText}`,
        draft?.notes ? `\n## Concept Notes\n${draft.notes}\n` : "",
        "## MCP Client Instructions",
        `1. Run \`get_readme_section(full_name="${repo.full_name}", query="benchmark paper citation algorithm math evaluation")\` to analyze the research foundation.`,
        `2. Run \`get_repo(full_name="${repo.full_name}")\` to inspect performance, GPU/hardware requirements, and library dependencies.`,
        "",
        "## Output Deliverables",
        "- **Commercialization Feasibility**: Is this algorithm or architecture ready for production inference/runtime or does it need heavy refactoring?",
        "- **Developer DX Friction**: What makes the academic repo hard for ordinary developers to run (CUDA dependencies, complex config, memory bloat)?",
        "- **Packaged API Product**: Design an ultra-clean REST/Python SDK (e.g. `client.predict(...)`) that abstracts the paper's complexity.",
        "- **Monetization Model**: Usage-based API pricing (per token / per request / per hour of compute).",
      ]
        .filter(Boolean)
        .join("\n");
    },
  },
];

// -------------------------------------------------------------
// Alternatives & Workflow Prompts (3 Prompts)
// -------------------------------------------------------------

export interface AlternativePromptContext {
  paidProduct: string;
  category?: string;
  os?: string;
  habits: string[];
  installedTools: string[];
  alternatives: AlternativesResponse["alternatives"];
  articulationGuide?: AlternativesResponse["articulation_guide"];
  userNotes?: string;
}

export const ALTERNATIVE_CATEGORIES = [
  "All",
  "Migration & Replacement",
  "Habit & Toolchain Fit",
  "Full Workflow Audit",
] as const;

export const ALTERNATIVE_PROMPTS: PromptTemplate<AlternativePromptContext>[] = [
  {
    id: "personal-migration-advisor",
    title: "Personal OSS Alternative & 15-Minute Migration Advisor",
    category: "Migration & Replacement",
    badge: "Personal Migration",
    summary:
      "Deep-dive recommendation and migration path to replace this paid product with the best open-source software matching your local OS and habits.",
    toolsUsed: ["find_oss_alternatives", "compare_repos", "get_readme_section"],
    generate: ({ paidProduct, category, os, habits, installedTools, alternatives, articulationGuide, userNotes }) => {
      const osName = os ? os.toUpperCase() : "Current OS";
      const habitStr = habits.length > 0 ? habits.join(", ") : "Standard workflow";
      const topPick = articulationGuide?.best_overall_pick || alternatives[0]?.full_name || "Top alternative";
      const topCandidates = alternatives.slice(0, 4);

      return [
        `# Open-Source Alternative & Personal Migration Plan: ${paidProduct}`,
        `Act as an Elite Open-Source Software Architect and Workstation Engineer.`,
        `Your mission: Help me replace commercial/paid product **${paidProduct}** with the best, most suited open-source software for my exact local machine and habits.`,
        "",
        "## My Local Environment & Workflow Context",
        `- **Operating System**: ${osName}`,
        category ? `- **Commercial Category**: ${category}` : "",
        installedTools.length > 0
          ? `- **Installed Workflow Tools**: ${installedTools.slice(0, 10).join(", ")}`
          : "",
        `- **My Habits & Preferences**: ${habitStr}`,
        userNotes ? `- **Specific Requirements / Notes**: ${userNotes}` : "",
        "",
        "## Top Scored Open-Source Candidates from ossdex",
        `- **#1 Best Match**: ${topPick}`,
        ...topCandidates.map(
          (c) =>
            `- **${c.full_name}** (${(c.stars || 0).toLocaleString()}★, ${c.fit_score}% fit, badge: "${c.fit_badge}"): ` +
            `Form factor: ${c.form_factor}. Tailored install: \`${c.tailored_install_command || "N/A"}\``,
        ),
        "",
        "## Tool-Assisted Investigation Instructions",
        `1. Ask me which package managers and CLI tools I have installed, unless listed above.`,
        `2. Run \`find_oss_alternatives(paid_product="${paidProduct}")\` to inspect full candidate rankings and fit evidence.`,
        `3. For the top 2-3 finalists, run \`get_readme_section\` and \`compare_repos\` to inspect features and configuration.`,
        "",
        "## Required Output Deliverables",
        `1. **Executive Verdict & #1 Recommendation**: Why **${topPick}** is the sharpest fit for my ${osName} setup and ${habitStr} habits.`,
        "2. **Habit & Workflow Synergy Breakdown**: How the top picks connect with my installed tools (e.g. Vim bindings, Docker container, local files, terminal multiplexer).",
        "3. **Honest Feature Parity & Trade-offs**: What features from the paid product are missing or require extra setup, and how to bridge the gap.",
        "4. **Exact Tailored Install & Setup Commands**: Copy-paste terminal commands matching my package manager.",
        "5. **15-Minute Migration Guide**: Step-by-step instructions to export data from the commercial product, import it into the open-source alternative, and verify it works.",
      ].filter(Boolean).join("\n");
    },
  },

  {
    id: "habit-shootout",
    title: "Habit & Keybinding Head-to-Head Shootout",
    category: "Habit & Toolchain Fit",
    badge: "Habit Shootout",
    summary:
      "Compare the top open-source finalists specifically against your daily habits, modal/Vim bindings, offline privacy, and local toolchain.",
    toolsUsed: ["find_oss_alternatives", "compare_repos", "get_readme_section"],
    generate: ({ paidProduct, os, habits, installedTools, alternatives, userNotes }) => {
      const finalists = alternatives.slice(0, 3).map((a) => a.full_name);
      return [
        `# Open-Source Habit & Workflow Shootout for ${paidProduct}`,
        `Act as a Staff Developer Tools Specialist.`,
        `Benchmark the top open-source alternatives to **${paidProduct}** specifically through the lens of my daily working habits.`,
        "",
        "## My Daily Habits",
        `- **Habits**: ${habits.join(", ") || "CLI-first, lightweight"}`,
        `- **OS**: ${os?.toUpperCase() || "Desktop OS"}`,
        installedTools.length > 0 ? `- **Core Tools**: ${installedTools.join(", ")}` : "",
        userNotes ? `- **User Notes**: ${userNotes}` : "",
        "",
        "## Finalists to Compare",
        finalists.map((f) => `- ${f}`).join("\n"),
        "",
        "## MCP Instructions",
        `1. Run \`compare_repos(full_names=[${finalists.map((f) => `"${f}"`).join(", ")}])\` to inspect activity, velocity, and maintenance.`,
        `2. Run \`get_readme_section\` on each finalist for keybindings, shortcuts, and configuration.`,
        "",
        "## Output Deliverables",
        "- **Speed & Latency**: Startup time, UI responsiveness, and resource footprint.",
        "- **Keyboard & Navigation Ergonomics**: Full keyboard accessibility, modal/Vim navigation, and command palette support.",
        "- **Local Data Ownership**: Plaintext/SQLite vs proprietary SQLite vs remote cloud storage.",
        "- **Clear Winner**: The single best tool for my daily muscle memory.",
      ].filter(Boolean).join("\n");
    },
  },

  {
    id: "workflow-replacement-audit",
    title: "Full Local Workflow & Subscription Replacement Audit",
    category: "Full Workflow Audit",
    badge: "Workflow Audit",
    summary:
      "Audit all detected commercial subscriptions and craft a cohesive, open-source workstation ecosystem.",
    toolsUsed: ["find_oss_alternatives", "compose_product_stack"],
    generate: ({ os, habits, userNotes }) => {

      return [
        `# Full Workstation Open-Source Subscription Replacement Audit`,
        `Act as a Chief Workstation Architect and Open-Source Strategist.`,
        `Audit my current workstation software and design a cohesive, self-sufficient open-source software stack that eliminates recurring SaaS fees.`,
        "",
        "## My Commercial Software",
        "Ask me which paid apps and subscriptions I use today, unless I list them under Personal Focus.",
        "",
        "## My Environment & Habits",
        `- **OS**: ${os?.toUpperCase() || "Current OS"}`,
        `- **Habit Profile**: ${habits.join(", ") || "Productive developer"}`,
        userNotes ? `- **Personal Focus**: ${userNotes}` : "",
        "",
        "## MCP Client Instructions",
        "1. For each paid app I name, run `find_oss_alternatives(paid_product=..., os=..., habits=[...])` to fetch replacement options.",
        "",
        "## Output Deliverables",
        "- **Subscription Replacement Roadmap**: For each proprietary tool, the top open-source replacement with monthly cost savings ($/mo).",
        "- **Cohesive Toolchain Integration**: How these replacements talk to each other (e.g. shared markdown files, local git repos, Docker containers).",
        "- **Zero-Regret Transition Plan**: Priority order of migration (easiest 1-day swaps first -> high-data migrations last).",
      ].filter(Boolean).join("\n");
    },
  },
];
