import { useState, useEffect } from "react";
import {
  IconBookOpen,
  IconCheck,
  IconCode,
  IconCopy,
  IconFileText,
  IconSparkles,
  IconX,
} from "./icons";

interface GuideModalProps {
  isOpen: boolean;
  onClose: () => void;
  onApplyQuickFilter?: (patch: { saasSafe?: boolean; money?: string[] }) => void;
}

function CopyCodeBlock({ text, title }: { text: string; title?: string }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  return (
    <div className="guide-code-box">
      {title && (
        <div className="guide-code-bar">
          <span className="guide-code-title">{title}</span>
          <button
            type="button"
            className="btn-subtle small-btn"
            onClick={handleCopy}
            title="Copy snippet to clipboard"
          >
            {copied ? <IconCheck size={11} /> : <IconCopy size={11} />}
            <span>{copied ? "Copied!" : "Copy"}</span>
          </button>
        </div>
      )}
      <div className="guide-code-inner">
        <pre className="guide-code-pre">{text}</pre>
        {!title && (
          <button
            type="button"
            className="btn-subtle small-btn guide-float-copy"
            onClick={handleCopy}
            title="Copy snippet"
          >
            {copied ? <IconCheck size={11} /> : <IconCopy size={11} />}
            <span>{copied ? "Copied" : "Copy"}</span>
          </button>
        )}
      </div>
    </div>
  );
}

export default function GuideModal({
  isOpen,
  onClose,
  onApplyQuickFilter,
}: GuideModalProps) {
  const [activeTab, setActiveTab] = useState<"desktop-mcp" | "playbook" | "reference">("desktop-mcp");
  const [desktopPlatform, setDesktopPlatform] = useState<"claude" | "gemini" | "chatgpt">("claude");

  // The MCP endpoint is served by the same process as this page, so its URL is this origin + /mcp.
  const mcpUrl = `${window.location.origin}/mcp`;
  const isLocal = ["localhost", "127.0.0.1", "[::1]"].includes(window.location.hostname);

  useEffect(() => {
    if (!isOpen) return;
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);

    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = prevOverflow;
    };
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const claudeCodeCli = `claude mcp add --transport http ossdex ${mcpUrl}`;

  // Claude Desktop's config file only launches local processes; mcp-remote bridges it to the HTTP endpoint.
  const claudeDesktopConfig = JSON.stringify(
    { mcpServers: { ossdex: { command: "npx", args: ["-y", "mcp-remote", mcpUrl] } } },
    null,
    2
  );

  const geminiCli = `gemini mcp add --transport http ossdex ${mcpUrl}`;
  const geminiSettings = JSON.stringify({ mcpServers: { ossdex: { httpUrl: mcpUrl } } }, null, 2);
  const antigravityConfig = JSON.stringify({ mcpServers: { ossdex: { serverUrl: mcpUrl } } }, null, 2);

  const codexCli = `codex mcp add ossdex --url ${mcpUrl}`;
  const mcpInspector = "npx @modelcontextprotocol/inspector";

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <article
        className="repo-modal guide-modal-dialog"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label="ossdex User & MCP Guide"
      >
        <header className="modal-header">
          <div className="modal-title-wrap">
            <span className="brand-logo">
              <IconBookOpen size={16} />
            </span>
            <div className="modal-title-text">
              <h2>User Guide & Desktop MCP Setup</h2>
              <span className="muted small">
                Connect ossdex to Claude, Gemini, and ChatGPT · Maximize product discovery in the web app
              </span>
            </div>
          </div>
          <button className="icon-btn" onClick={onClose} title="Close guide (Esc)" aria-label="Close guide">
            <IconX size={16} />
          </button>
        </header>

        {/* Guide Navigation Tabs */}
        <div className="guide-nav-bar">
          <div className="guide-nav-tabs">
            <button
              type="button"
              className={`guide-nav-tab ${activeTab === "desktop-mcp" ? "active" : ""}`}
              onClick={() => setActiveTab("desktop-mcp")}
            >
              <IconCode size={13} />
              <span>1. Connect Desktop MCP (Claude, Gemini, ChatGPT)</span>
            </button>
            <button
              type="button"
              className={`guide-nav-tab ${activeTab === "playbook" ? "active" : ""}`}
              onClick={() => setActiveTab("playbook")}
            >
              <IconSparkles size={13} />
              <span>2. Web App Mastery Playbook</span>
            </button>
            <button
              type="button"
              className={`guide-nav-tab ${activeTab === "reference" ? "active" : ""}`}
              onClick={() => setActiveTab("reference")}
            >
              <IconFileText size={13} />
              <span>3. MCP Tools & Prompts Reference</span>
            </button>
          </div>
        </div>

        <div className="modal-body guide-modal-body">
          {/* TAB 1: DESKTOP MCP CONNECTIVITY */}
          {activeTab === "desktop-mcp" && (
            <div className="guide-section-content">
              <div className="guide-intro-banner">
                <p>
                  <strong>ossdex</strong> provides a Model Context Protocol (MCP) server exposing 24 tools and
                  13 prompts over Streamable HTTP, from the same server as this page. It never calls GitHub or
                  third-party LLMs while answering, and it never looks at the machine it runs on. Every client below
                  connects to this URL:
                </p>
                <CopyCodeBlock text={mcpUrl} title="MCP Server URL" />
                {isLocal && (
                  <p className="muted small">
                    This is a local server: keep <code>ossdex-server serve</code> running while you use it. Cloud-hosted
                    connectors (claude.ai, ChatGPT) cannot reach <code>localhost</code>; give them the public
                    URL of a hosted ossdex instead.
                  </p>
                )}
              </div>

              {/* Platform Selector */}
              <div className="platform-tabs">
                <button
                  type="button"
                  className={`platform-btn ${desktopPlatform === "claude" ? "active" : ""}`}
                  onClick={() => setDesktopPlatform("claude")}
                >
                  <span className="platform-icon">🟣</span>
                  <span>Claude Desktop & Claude Code</span>
                </button>
                <button
                  type="button"
                  className={`platform-btn ${desktopPlatform === "gemini" ? "active" : ""}`}
                  onClick={() => setDesktopPlatform("gemini")}
                >
                  <span className="platform-icon">🔵</span>
                  <span>Gemini CLI & Antigravity</span>
                </button>
                <button
                  type="button"
                  className={`platform-btn ${desktopPlatform === "chatgpt" ? "active" : ""}`}
                  onClick={() => setDesktopPlatform("chatgpt")}
                >
                  <span className="platform-icon">🟢</span>
                  <span>ChatGPT Desktop & Codex</span>
                </button>
              </div>

              {/* CLAUDE PLATFORM */}
              {desktopPlatform === "claude" && (
                <div className="platform-guide-pane">
                  <h3>🟣 Claude Desktop & Claude Code</h3>
                  <p className="muted small">
                    Claude has native Model Context Protocol support for both the desktop app and the terminal agent.
                  </p>

                  <div className="guide-card">
                    <h4>Option A: Claude Code (CLI)</h4>
                    <p className="small">Run this single terminal command to connect ossdex to Claude Code:</p>
                    <CopyCodeBlock text={claudeCodeCli} title="Terminal Command" />
                  </div>

                  <div className="guide-card">
                    <h4>Option B: Claude Desktop Application</h4>
                    {!isLocal && (
                      <p className="small">
                        In <strong>Settings → Connectors → Add custom connector</strong>, name it <code>ossdex</code> and
                        paste the URL above. This also makes it available on claude.ai and the mobile app.
                      </p>
                    )}
                    <p className="small">
                      {isLocal ? "Add" : "Or add"} ossdex to your Claude Desktop configuration file (needs Node.js for{" "}
                      <code>mcp-remote</code>, which connects the app to the HTTP endpoint):
                      <br />
                      <span className="font-mono muted small">
                        macOS: ~/Library/Application Support/Claude/claude_desktop_config.json
                        <br />
                        Windows: %APPDATA%\Claude\claude_desktop_config.json
                      </span>
                    </p>
                    <CopyCodeBlock text={claudeDesktopConfig} title="claude_desktop_config.json" />
                    <ol className="guide-steps-list small">
                      <li>Save the configuration file and restart Claude Desktop.</li>
                      <li>
                        Look for the <strong>hammer (🔨)</strong> icon in the chat input bar showing connected tools
                        (e.g. <code>search_repos</code>, <code>compare_repos</code>, <code>find_niches</code>).
                      </li>
                      <li>
                        Type <code>/</code> or click the attachment menu to run prebuilt prompts like{" "}
                        <code>saas_base</code>, <code>vertical_saas_idea</code>, or <code>compose_product_stack</code>.
                      </li>
                    </ol>
                  </div>
                </div>
              )}

              {/* GEMINI PLATFORM */}
              {desktopPlatform === "gemini" && (
                <div className="platform-guide-pane">
                  <h3>🔵 Google Gemini CLI & Antigravity</h3>
                  <p className="muted small">
                    Connect ossdex tools directly to the Gemini CLI agent or Antigravity developer workspace.
                  </p>

                  <div className="guide-card">
                    <h4>Option A: Gemini CLI</h4>
                    <p className="small">Register the tool server directly using the Gemini CLI:</p>
                    <CopyCodeBlock text={geminiCli} title="Terminal Command" />
                  </div>

                  <div className="guide-card">
                    <h4>Option B: Gemini Settings File</h4>
                    <p className="small">
                      Or add it by hand to <code>~/.gemini/settings.json</code> (<code>httpUrl</code> selects Streamable HTTP):
                    </p>
                    <CopyCodeBlock text={geminiSettings} title="settings.json" />
                  </div>

                  <div className="guide-card">
                    <h4>Option C: Antigravity</h4>
                    <p className="small">
                      Open <strong>Manage MCP servers → View raw config</strong> and add this to <code>mcp_config.json</code>{" "}
                      (Antigravity reads remote servers from <code>serverUrl</code>):
                    </p>
                    <CopyCodeBlock text={antigravityConfig} title="mcp_config.json" />
                    <p className="muted small">
                      Once added, ask Gemini or Antigravity:{" "}
                      <em>"Search ossdex for high-velocity permissive vector search engines and compare the top 3."</em>
                    </p>
                  </div>
                </div>
              )}

              {/* CHATGPT PLATFORM */}
              {desktopPlatform === "chatgpt" && (
                <div className="platform-guide-pane">
                  <h3>🟢 ChatGPT Desktop & OpenAI Codex</h3>
                  <p className="muted small">
                    Use the ChatGPT connector, the Codex CLI, or the instant zero-setup Prompt Library workflow.
                  </p>

                  <div className="guide-card">
                    <h4>Method 1: Zero-Setup Prompt Library Workflow (Recommended & Instant)</h4>
                    <p className="small">
                      You don't need any local connectors or MCP configuration to get full value from ChatGPT:
                    </p>
                    <ol className="guide-steps-list small">
                      <li>Open any repository card in this web app.</li>
                      <li>
                        Select your preferred lens in the <strong>MCP Prompt Library</strong> (e.g. <em>Managed Cloud SaaS Wrapper</em>).
                      </li>
                      <li>Click <strong>Copy</strong> and paste directly into ChatGPT Desktop or web.</li>
                      <li>ChatGPT will immediately analyze the validated architecture with all signals pre-loaded.</li>
                    </ol>
                  </div>

                  <div className="guide-card">
                    <h4>Method 2: ChatGPT Connector (Streamable HTTP)</h4>
                    <p className="small">
                      ChatGPT connects from OpenAI's servers, so it needs a public <code>https://</code> URL
                      {isLocal ? " (a hosted ossdex, not this local one)" : " like the one above"}. With developer mode on, go to{" "}
                      <strong>Settings → Connectors → Create</strong>:
                    </p>
                    <ul className="guide-steps-list small">
                      <li>Name: <code>ossdex</code></li>
                      <li>MCP Server URL: <code>{isLocal ? "https://ossdex.<your-domain>/mcp" : mcpUrl}</code></li>
                      <li>Authentication: <strong>No authentication</strong></li>
                    </ul>
                  </div>

                  <div className="guide-card">
                    <h4>Method 3: OpenAI Codex CLI (Streamable HTTP)</h4>
                    <CopyCodeBlock text={codexCli} title="Codex Terminal Command" />
                  </div>
                </div>
              )}

              {/* Verification & Inspector */}
              <div className="guide-card inspector-card">
                <h4>🛠️ Test & Verify Your MCP Server</h4>
                <p className="small">
                  You can inspect and test all 24 tools and 13 prompts in your browser using the official MCP Inspector.
                  Choose the <strong>Streamable HTTP</strong> transport and paste the URL above:
                </p>
                <CopyCodeBlock text={mcpInspector} title="Run MCP Inspector" />
              </div>
            </div>
          )}

          {/* TAB 2: WEB APP MASTERY PLAYBOOK */}
          {activeTab === "playbook" && (
            <div className="guide-section-content">
              <div className="guide-intro-banner">
                <p>
                  <strong>The 3-Stage Product Ideation Loop</strong>: How to move systematically from a filtered shortlist
                  down to validated single-repo architectures.
                </p>
              </div>

              <div className="playbook-steps-container">
                {/* Stage 1 */}
                <div className="playbook-step-card">
                  <div className="step-badge">Stage 1</div>
                  <div className="step-body">
                    <h4>Opportunity Filtering</h4>
                    <p className="small">
                      Use the filter bar to narrow the catalog to projects with commercial precedent:
                    </p>
                    <ul className="guide-bullet-list small">
                      <li>
                        <strong>Fast-Track Filter</strong>: Combine <code>SaaS-Safe</code> + <code>Business</code> to isolate repos
                        companies are already paying for.
                      </li>
                    </ul>
                    {onApplyQuickFilter && (
                      <button
                        type="button"
                        className="btn small-btn"
                        style={{ marginTop: 8 }}
                        onClick={() => {
                          onApplyQuickFilter({ saasSafe: true, money: ["hosted_cloud", "enterprise"] });
                          onClose();
                        }}
                      >
                        <IconSparkles size={12} />
                        <span>Apply SaaS-Safe + Business Filter</span>
                      </button>
                    )}
                  </div>
                </div>

                {/* Stage 2 */}
                <div className="playbook-step-card">
                  <div className="step-badge">Stage 2</div>
                  <div className="step-body">
                    <div className="step-head">
                      <h4>Single-Project Commercial Signal Auditing</h4>
                    </div>
                    <p className="small">
                      Click any repository card to open the large inspector modal. Read these 4 critical signals:
                    </p>
                    <div className="signal-cheatsheet-grid">
                      <div className="cheatsheet-item">
                        <strong>Fork Ratio ≥ 12%</strong>
                        <span>Signals active enterprise self-hosting. Companies already spend hours customizing it.</span>
                      </div>
                      <div className="cheatsheet-item">
                        <strong>License Posture</strong>
                        <span>
                          <em>Permissive</em> (MIT/Apache 2.0) = closed SaaS safe.
                          <br />
                          <em>Weak Copyleft</em> = library modifications must be open.
                          <br />
                          <em>AGPL</em> = requires clean-room API microservice boundary.
                        </span>
                      </div>
                      <div className="cheatsheet-item">
                        <strong>MCP Prompt Library</strong>
                        <span>Choose from 10 specialized lenses (e.g. <em>Vertical SaaS</em>, <em>Managed Cloud</em>, <em>White-Label Audit</em>) and copy in 1 click.</span>
                      </div>
                    </div>
                  </div>
                </div>

                {/* Stage 3 */}
                <div className="playbook-step-card">
                  <div className="step-badge">Stage 3</div>
                  <div className="step-body">
                    <h4>Deepening Data with the CLI</h4>
                    <p className="small">
                      Supercharge the web app and MCP tools by keeping star history and new repos fresh:
                    </p>
                    <CopyCodeBlock
                      text={`# Daily update (refreshes star gains and new repos):\nuv run --package ossdex-collector ossdex-collector update`}
                      title="Terminal Commands"
                    />
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* TAB 3: MCP TOOLS & PROMPTS REFERENCE */}
          {activeTab === "reference" && (
            <div className="guide-section-content">
              <h3>🛠️ 25 Built-in MCP Tools</h3>
              <p className="muted small">
                Every tool follows strict repo-agnostic conventions: closed-set enums, null preservation for missing metrics,
                evidence chains, and standardized envelopes (<code>as_of</code>, <code>data_coverage</code>, <code>sources</code>).
              </p>

              <h4 style={{ marginTop: 16 }}>Search, Discovery & Sizing (12 Tools)</h4>
              <div className="guide-table-wrap">
                <table className="guide-table">
                  <thead>
                    <tr>
                      <th>Tool</th>
                      <th>Purpose</th>
                      <th>Key Arguments</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr>
                      <td><code>search_repos</code></td>
                      <td>Search repos by keywords (FTS5) plus names, topics and descriptions</td>
                      <td><code>query</code>, <code>languages</code>, <code>license_kinds</code>, <code>min_forks</code></td>
                    </tr>
                    <tr>
                      <td><code>list_repos</code></td>
                      <td>Filter and sort repos by structured metrics without text query</td>
                      <td><code>sort</code> (stars, gain_1d, gain_7d, forks), <code>money</code></td>
                    </tr>
                    <tr>
                      <td><code>get_repo</code></td>
                      <td>Full record: README intro, license notes, star history, signals</td>
                      <td><code>full_name</code></td>
                    </tr>
                    <tr>
                      <td><code>find_similar</code></td>
                      <td>Discover closest alternatives and competitors by shared keywords and topics</td>
                      <td><code>full_name</code>, <code>license_kinds</code></td>
                    </tr>
                    <tr>
                      <td><code>compare_repos</code></td>
                      <td>Side-by-side comparison of 2–6 repos: velocity, license, age</td>
                      <td><code>full_names</code> (list)</td>
                    </tr>
                    <tr>
                      <td><code>count_repos</code></td>
                      <td>Size a niche: group counts by language, license, topic, year</td>
                      <td><code>group_by</code>, filters</td>
                    </tr>
                    <tr>
                      <td><code>opportunity_report</code></td>
                      <td>Fastest-growing niches + rising repos with business hints</td>
                      <td><code>language</code>, <code>days</code> (1 or 7)</td>
                    </tr>
                    <tr>
                      <td><code>find_niches</code></td>
                      <td>Rank topics by star growth rate and momentum per repo</td>
                      <td><code>days</code>, <code>sort</code> (growth, momentum)</td>
                    </tr>
                    <tr>
                      <td><code>get_readme_section</code></td>
                      <td>Targeted search inside a repository's README</td>
                      <td><code>full_name</code>, <code>query</code></td>
                    </tr>
                    <tr>
                      <td><code>get_rising</code></td>
                      <td>Repos gaining the most stars over 1 day (daily) or 7 days (weekly)</td>
                      <td><code>days</code>, <code>language</code></td>
                    </tr>
                    <tr>
                      <td><code>facets</code></td>
                      <td>Available languages, licenses, and topics in the database</td>
                      <td>none</td>
                    </tr>
                  </tbody>
                </table>
              </div>

              <h4 style={{ marginTop: 24 }}>Diagnostic & Brief Evaluation Tools (14 Tools, F1–F10 Guardrails)</h4>
              <div className="guide-table-wrap">
                <table className="guide-table">
                  <thead>
                    <tr>
                      <th>Tool</th>
                      <th>Failure Mode Guarded</th>
                      <th>Output & Analysis</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr>
                      <td><code>classify_artifact</code></td>
                      <td><span className="badge-tag">F1</span> <span className="badge-tag">F10</span> Category error & Provenance</td>
                      <td>Kind (app, library, sdk, framework, template, awesome_list) and feasible SaaS shapes.</td>
                    </tr>
                    <tr>
                      <td><code>get_runtime_dependencies</code></td>
                      <td><span className="badge-tag">F2</span> Hidden lock-in</td>
                      <td>Required/optional cloud services, API keys, self-hostability, and lock-in risk (low/med/high).</td>
                    </tr>
                    <tr>
                      <td><code>classify_growth</code></td>
                      <td><span className="badge-tag">F3</span> Velocity misread</td>
                      <td>Star curve pattern (launch_spike, sustained, flat, declining), half-life days, and 30d projection.</td>
                    </tr>
                    <tr>
                      <td><code>get_package_adoption</code></td>
                      <td><span className="badge-tag">F3</span> <span className="badge-tag">F4</span> Library adoption</td>
                      <td>Registry package coordinates (npm, pypi, crates, go, packagist, docker_hub).</td>
                    </tr>
                    <tr>
                      <td><code>analyze_forks</code></td>
                      <td><span className="badge-tag">F4</span> Fork misread</td>
                      <td>Separates production customization from template copies and abandoned forks.</td>
                    </tr>
                    <tr>
                      <td><code>get_maintainer_health</code></td>
                      <td>Services & SLA risk</td>
                      <td>Push recency, release cadence, corporate backing, and bus factor risk.</td>
                    </tr>
                    <tr>
                      <td><code>get_commercial_landscape</code></td>
                      <td><span className="badge-tag">F5</span> Missed precedent</td>
                      <td>Paid products, managed offerings, pricing models (per_seat, usage, flat), and source URLs.</td>
                    </tr>
                    <tr>
                      <td><code>get_company_events</code></td>
                      <td><span className="badge-tag">F5</span> Corporate history</td>
                      <td>Funding rounds, sponsorships, archival, and shutdowns tied to maintainers.</td>
                    </tr>
                    <tr>
                      <td><code>check_name_collision</code></td>
                      <td><span className="badge-tag">F6</span> Name collision</td>
                      <td>Trademarks and existing repos sharing name stems, with collision risk score.</td>
                    </tr>
                    <tr>
                      <td><code>license_audit</code></td>
                      <td><span className="badge-tag">F7</span> License blindspot</td>
                      <td>Audits system binaries (ffmpeg), vendor ToS, and outputs hosted SaaS & closed distribution verdicts.</td>
                    </tr>
                    <tr>
                      <td><code>platform_compat</code></td>
                      <td><span className="badge-tag">F8</span> Platform blindspot</td>
                      <td>Audits runtime requirements (GPU, persistent disk, background daemons) against serverless vs containers.</td>
                    </tr>
                    <tr>
                      <td><code>saas_base</code></td>
                      <td>Commercial Packaging</td>
                      <td>Composite packaging: recommended shape, blockers, moat, COGS drivers, and kill tests.</td>
                    </tr>
                    <tr>
                      <td><code>evaluate_brief</code></td>
                      <td>End-to-End Evaluation</td>
                      <td>Fact-checks claims, scores candidate angles, and returns pursue/narrow/reject verdict with kill tests.</td>
                    </tr>
                  </tbody>
                </table>
              </div>

              <h3 style={{ marginTop: 28 }}>✨ 13 Pre-Engineered Prompts</h3>
              <p className="muted small">Invokable in Claude, Gemini, ChatGPT Desktop, or via the web app's Prompt Library:</p>

              <div className="guide-table-wrap">
                <table className="guide-table">
                  <thead>
                    <tr>
                      <th>Prompt</th>
                      <th>Category</th>
                      <th>What It Generates</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr>
                      <td><code>learn_repo_80_20</code></td>
                      <td>80/20 Learning</td>
                      <td>Pareto 80/20 repo mastery guide: prerequisites (must-know vs look up later), 20% core abstractions, 80% noise to skip, 60-min lab, and pitfalls.</td>
                    </tr>
                    <tr>
                      <td><code>learn_stack_80_20</code></td>
                      <td>Stack Mastery</td>
                      <td>Pareto 80/20 multi-repo learning path: cross-stack prerequisite matrix, 20% integration surface of each repo, and 48-hr build lab.</td>
                    </tr>
                    <tr>
                      <td><code>articulate_repo_ideas</code></td>
                      <td>Idea Articulation</td>
                      <td>Brainstorms and articulates 5 concrete product/startup ideas based on a repository, with 80/20 value split and 14-day MVP wedge.</td>
                    </tr>
                    <tr>
                      <td><code>articulate_stack_ideas</code></td>
                      <td>Mashup Ideation</td>
                      <td>Brainstorms 4 high-synergy '1+1=3' product mashup ideas combining 2 to 6 composed repos with assigned subsystem roles.</td>
                    </tr>
                    <tr>
                      <td><code>evaluate_product_brief</code></td>
                      <td>Flagship Brief Audit</td>
                      <td>Evaluates a Product Idea Brief against the 10 failure modes (F1–F10) with an evidence-based verdict.</td>
                    </tr>
                    <tr>
                      <td><code>saas_base</code></td>
                      <td>SaaS Discovery</td>
                      <td>Finds permissive, maintained projects to build a hosted SaaS on.</td>
                    </tr>
                    <tr>
                      <td><code>vertical_saas_idea</code></td>
                      <td>Vertical SaaS</td>
                      <td>Tailors an open-source project to a specific regulated industry (Health, Legal, FinTech).</td>
                    </tr>
                    <tr>
                      <td><code>compose_product_stack</code></td>
                      <td>Multi-Repo Stack</td>
                      <td>Architects a multi-component product with role assignments and license checks.</td>
                    </tr>
                    <tr>
                      <td><code>fork_and_rebrand_audit</code></td>
                      <td>Architecture</td>
                      <td>Checklist for trademark stripping, white-labeling, and git upstream tracking.</td>
                    </tr>
                    <tr>
                      <td><code>competitive_moat_analysis</code></td>
                      <td>Strategy</td>
                      <td>Moat benchmark against closest alternatives to find an underserved wedge.</td>
                    </tr>
                    <tr>
                      <td><code>breakout_opportunity_scan</code></td>
                      <td>Market Scanning</td>
                      <td>Scans fast-rising topics with few competitors to spot new product bets.</td>
                    </tr>
                    <tr>
                      <td><code>freelance_niches</code></td>
                      <td>Services</td>
                      <td>Finds platforms businesses deploy and pay consultants to customize.</td>
                    </tr>
                    <tr>
                      <td><code>oss_solution</code></td>
                      <td>Evaluation</td>
                      <td>Evaluates the best open-source solution for a problem with trade-offs.</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      </article>
    </div>
  );
}
