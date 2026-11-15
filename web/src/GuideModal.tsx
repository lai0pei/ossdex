import { useState, useEffect, type ReactNode } from "react";
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


/** A one-line suggestion with its own copy button, for questions to paste into Claude. */
function CopyChip({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      className="guide-try"
      onClick={() =>
        navigator.clipboard.writeText(text).then(() => {
          setCopied(true);
          setTimeout(() => setCopied(false), 2000);
        })
      }
      title="Click to copy"
    >
      <span>{text}</span>
      <span className="guide-try-copy">
        {copied ? <IconCheck size={11} /> : <IconCopy size={11} />}
        {copied ? "Copied" : "Copy"}
      </span>
    </button>
  );
}

function Step({ n, title, children }: { n: number; title: string; children?: ReactNode }) {
  return (
    <li className="guide-step">
      <span className="guide-step-n">{n}</span>
      <div className="guide-step-body">
        <h4>{title}</h4>
        {children}
      </div>
    </li>
  );
}

/** A button-styled link that opens an app's settings page in a new tab. */
function OpenLink({ href, label }: { href: string; label: string }) {
  return (
    <a className="guide-open-link" href={href} target="_blank" rel="noopener noreferrer">
      {label} ↗
    </a>
  );
}

type AppId = "claude" | "chatgpt" | "gemini";

// Menu names follow each vendor's help pages as of late 2026; the notes cover plan and account limits.
const APPS: { id: AppId; name: string; note: string }[] = [
  {
    id: "claude",
    name: "Claude",
    note:
      "On a Team or Enterprise plan only an owner can add connectors: they add ossdex in Organization settings → " +
      "Connectors, then you click Connect. The Free plan allows one custom connector.",
  },
  {
    id: "chatgpt",
    name: "ChatGPT",
    note:
      "Custom MCP servers depend on your plan. If Plugins has no \"Add custom MCP server\", turn on Settings → " +
      "Apps → Advanced settings → Developer mode, then click Create app and paste the same link. On a Business " +
      "workspace only an admin can add it.",
  },
  {
    id: "gemini",
    name: "Gemini",
    note:
      "Custom apps need a personal Google account (not work or school), age 18+ in the US, Gemini in English, " +
      "and Keep Activity turned on. They can only be added in the web app.",
  },
];

const STARTER_QUESTIONS = [
  "Use ossdex to find fast-growing open-source projects I could build a business on",
  "Use ossdex to find the best open-source alternatives to Notion and compare them",
  "Use ossdex: which open-source AI projects gained the most stars this week?",
];

const CAN_DO: { ask: string; tool: string }[] = [
  { ask: "Find projects for an idea or a keyword", tool: "search_repos" },
  { ask: "See what is trending this week", tool: "get_rising" },
  { ask: "Compare 2 to 6 projects side by side", tool: "compare_repos" },
  { ask: "Spot fast-growing niches", tool: "find_niches · opportunity_report" },
  { ask: "Check if you may sell it (license check)", tool: "license_audit" },
  { ask: "Check if it is still maintained", tool: "get_maintainer_health" },
  { ask: "See who already sells it as a product", tool: "get_commercial_landscape" },
  { ask: "Stress-test your product idea", tool: "evaluate_brief" },
];

export default function GuideModal({
  isOpen,
  onClose,
}: GuideModalProps) {
  const [activeTab, setActiveTab] = useState<"connect" | "site" | "can-do">("connect");
  const [app, setApp] = useState<AppId>("claude");
  const [devPlatform, setDevPlatform] = useState<"claude" | "gemini" | "chatgpt">("claude");

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
  const claudeConfigCmd = "uv run --package ossdex-server ossdex-server claude-config --install";


  return (
    <div className="modal-backdrop" onClick={onClose}>
      <article
        className="repo-modal guide-modal-dialog"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label="ossdex Guide"
      >
        <header className="modal-header">
          <div className="modal-title-wrap">
            <span className="brand-logo">
              <IconBookOpen size={16} />
            </span>
            <div className="modal-title-text">
              <h2>Guide</h2>
              <span className="muted small">Add ossdex to Claude, ChatGPT or Gemini with one link</span>
            </div>
          </div>
          <button className="icon-btn" onClick={onClose} title="Close guide (Esc)" aria-label="Close guide">
            <IconX size={16} />
          </button>
        </header>

        <div className="guide-nav-bar">
          <div className="guide-nav-tabs">
            <button
              type="button"
              className={`guide-nav-tab ${activeTab === "connect" ? "active" : ""}`}
              onClick={() => setActiveTab("connect")}
            >
              <IconCode size={13} />
              <span>Connect your AI</span>
            </button>
            <button
              type="button"
              className={`guide-nav-tab ${activeTab === "site" ? "active" : ""}`}
              onClick={() => setActiveTab("site")}
            >
              <IconSparkles size={13} />
              <span>Using this site</span>
            </button>
            <button
              type="button"
              className={`guide-nav-tab ${activeTab === "can-do" ? "active" : ""}`}
              onClick={() => setActiveTab("can-do")}
            >
              <IconFileText size={13} />
              <span>What you can ask</span>
            </button>
          </div>
        </div>

        <div className="modal-body guide-modal-body">
          {/* TAB 1: CONNECT YOUR AI APP, STEP BY STEP */}
          {activeTab === "connect" && (
            <div className="guide-section-content">
              <div className="guide-intro-banner">
                <p>
                  Connect ossdex to your AI app and it can search, compare and analyse thousands of open-source
                  projects for you, right in the chat. It only reads ossdex's own data, and no account is needed.
                </p>
              </div>

              <div className="platform-tabs guide-app-picker" role="tablist" aria-label="Your AI app">
                {APPS.map((a) => (
                  <button
                    key={a.id}
                    type="button"
                    role="tab"
                    aria-selected={app === a.id}
                    className={`platform-btn ${app === a.id ? "active" : ""}`}
                    onClick={() => setApp(a.id)}
                  >
                    <span>{a.name}</span>
                  </button>
                ))}
              </div>

              <ol className="guide-steps">
                <Step n={1} title="Copy your ossdex link">
                  <CopyCodeBlock text={mcpUrl} title="Your ossdex link" />
                  {isLocal && (
                    <p className="muted small">
                      This is a local address. AI apps connect over the internet, so use the link from the public
                      ossdex site instead.
                    </p>
                  )}
                </Step>

                {app === "claude" && (
                  <>
                    <Step n={2} title="Open Claude's Connectors page">
                      <OpenLink href="https://claude.ai/customize/connectors" label="Open Claude connectors" />
                      <p className="small">
                        Or in Claude Desktop: <strong>Customize → Connectors</strong> (older versions:{" "}
                        <strong>Settings → Connectors</strong>). Connectors belong to your account, so one added on the
                        web also shows up in Claude Desktop and on your phone.
                      </p>
                    </Step>
                    <Step n={3} title='Click "+ Add", then "Add custom connector"'>
                      <p className="small">
                        Name it <code>ossdex</code>, paste the link and click <strong>Continue</strong>. When asked
                        about signing in, choose <strong>No sign in</strong>, then click <strong>Add</strong>.
                      </p>
                    </Step>
                    <Step n={4} title="Switch ossdex on in a new chat">
                      <p className="small">
                        Start a new chat, click <strong>+</strong> at the bottom left of the message box, choose{" "}
                        <strong>Connectors</strong> and turn <strong>ossdex</strong> on.
                      </p>
                    </Step>
                  </>
                )}

                {app === "chatgpt" && (
                  <>
                    <Step n={2} title="Open ChatGPT's Plugins page">
                      <OpenLink href="https://chatgpt.com/plugins" label="Open ChatGPT plugins" />
                    </Step>
                    <Step n={3} title='Click "+", then "Add custom MCP server"'>
                      <p className="small">
                        Name it <code>ossdex</code> and paste the link under <strong>Connection</strong>. Set
                        authentication to <strong>No authentication</strong>, tick{" "}
                        <strong>I understand and want to continue</strong>, click{" "}
                        <strong>Create as a plugin</strong>, then install it.
                      </p>
                    </Step>
                    <Step n={4} title="Pick ossdex in a new chat">
                      <p className="small">
                        Start a new chat, type <strong>@</strong> in the message box and choose{" "}
                        <strong>ossdex</strong>.
                      </p>
                    </Step>
                  </>
                )}

                {app === "gemini" && (
                  <>
                    <Step n={2} title="Open Gemini's Connected Apps on a computer">
                      <OpenLink href="https://gemini.google.com" label="Open Gemini" />
                      <p className="small">
                        At the bottom left click <strong>Settings → Connected Apps</strong> (if it's not there:{" "}
                        <strong>Personal Intelligence → Connected Apps</strong>).
                      </p>
                    </Step>
                    <Step n={3} title='Under "Custom apps", click "Add a custom app"'>
                      <p className="small">
                        Paste the link, click <strong>Next</strong> and follow the screens. Once added, it works in the
                        Gemini phone app too.
                      </p>
                    </Step>
                    <Step n={4} title="Pick ossdex in a new chat">
                      <p className="small">
                        Start a new chat, type <strong>@</strong> in the message box and choose{" "}
                        <strong>ossdex</strong>.
                      </p>
                    </Step>
                  </>
                )}

                <Step n={5} title="Ask a question that names ossdex">
                  <p className="small">Click a question to copy it, then paste it into the chat:</p>
                  <div className="guide-try-list">
                    {STARTER_QUESTIONS.map((q) => (
                      <CopyChip key={q} text={q} />
                    ))}
                  </div>
                  <p className="muted small">
                    Starting with <strong>"Use ossdex…"</strong> makes the AI look it up instead of answering from
                    memory. If it asks permission to use ossdex, choose <strong>Always allow</strong>: ossdex only reads
                    its own data.
                  </p>
                </Step>
              </ol>

              <div className="guide-card guide-app-note">
                <h4>Can't find the add button?</h4>
                <p className="small">{APPS.find((a) => a.id === app)?.note}</p>
              </div>

              <details className="guide-fold">
                <summary>Something not working?</summary>
                <ul className="guide-bullet-list small">
                  <li>
                    <strong>The AI answered without ossdex?</strong> Check that ossdex is switched on or picked (step
                    4) and start your question with "Use ossdex to…".
                  </li>
                  <li>
                    <strong>Error when adding the link?</strong> Paste the full link, starting with{" "}
                    <code>https://</code> and ending in <code>/mcp</code>. If it still fails, the owner of the site needs
                    to finish its setup (see the developer notes below).
                  </li>
                  <li>
                    <strong>Menus look different?</strong> These apps move their settings often. Look for{" "}
                    <strong>Connectors</strong>, <strong>Plugins</strong> or <strong>Connected apps</strong>, or update
                    the app.
                  </li>
                </ul>
              </details>

              <div className="guide-card">
                <h4>No setup at all: copy a prompt</h4>
                <p className="small">
                  Open any project card, find the <strong>MCP Prompt Library</strong>, click <strong>Copy Prompt</strong>
                  and paste it into any chat app (Claude, ChatGPT, Gemini). The project's facts come with it.
                </p>
              </div>

              <details className="guide-fold">
                <summary>For developers: other apps and manual setup</summary>
                <div className="guide-fold-body">
                  <p className="small">
                    ossdex serves MCP over Streamable HTTP, from the same server as this page. Every client connects to
                    this URL:
                  </p>
                  <CopyCodeBlock text={mcpUrl} title="MCP Server URL" />
                  <p className="muted small">
                    Site owners: a public server must set <code>OSSDEX_PUBLIC_HOST=&lt;your-domain&gt;</code>, or{" "}
                    <code>/mcp</code> answers "Invalid Host" and the connector cannot be added.
                  </p>
                  {isLocal && (
                    <>
                      <h4>Running ossdex on your own computer?</h4>
                      <p className="muted small">
                        Cloud connectors cannot reach <code>localhost</code>. To use this local copy in Claude Desktop,
                        run this in a new terminal tab, then fully quit and reopen Claude:
                      </p>
                      <CopyCodeBlock text={claudeConfigCmd} title="Terminal command" />
                    </>
                  )}

                  <div className="platform-tabs">
                    <button
                      type="button"
                      className={`platform-btn ${devPlatform === "claude" ? "active" : ""}`}
                      onClick={() => setDevPlatform("claude")}
                    >
                      <span>Claude Code & JSON</span>
                    </button>
                    <button
                      type="button"
                      className={`platform-btn ${devPlatform === "gemini" ? "active" : ""}`}
                      onClick={() => setDevPlatform("gemini")}
                    >
                      <span>Gemini CLI & Antigravity</span>
                    </button>
                    <button
                      type="button"
                      className={`platform-btn ${devPlatform === "chatgpt" ? "active" : ""}`}
                      onClick={() => setDevPlatform("chatgpt")}
                    >
                      <span>Codex CLI</span>
                    </button>
                  </div>

                  {devPlatform === "claude" && (
                    <div className="platform-guide-pane">
                      <div className="guide-card">
                        <h4>Claude Code (CLI)</h4>
                        <CopyCodeBlock text={claudeCodeCli} title="Terminal command" />
                      </div>
                      <div className="guide-card">
                        <h4>Claude Desktop config file (needs Node.js)</h4>
                        <p className="small">
                          <code>mcp-remote</code> bridges the app's config file to the HTTP endpoint. Merge this into{" "}
                          <code>mcpServers</code>, then fully quit and reopen Claude:
                          <br />
                          <span className="font-mono muted small">
                            macOS: ~/Library/Application Support/Claude/claude_desktop_config.json
                            <br />
                            Windows: %APPDATA%\Claude\claude_desktop_config.json
                          </span>
                        </p>
                        <CopyCodeBlock text={claudeDesktopConfig} title="claude_desktop_config.json" />
                      </div>
                    </div>
                  )}

                  {devPlatform === "gemini" && (
                    <div className="platform-guide-pane">
                      <div className="guide-card">
                        <h4>Gemini CLI</h4>
                        <CopyCodeBlock text={geminiCli} title="Terminal command" />
                        <p className="small">
                          Or add it by hand to <code>~/.gemini/settings.json</code> (<code>httpUrl</code> selects
                          Streamable HTTP):
                        </p>
                        <CopyCodeBlock text={geminiSettings} title="settings.json" />
                      </div>
                      <div className="guide-card">
                        <h4>Antigravity</h4>
                        <p className="small">
                          Open <strong>Manage MCP servers → View raw config</strong> and add this to{" "}
                          <code>mcp_config.json</code> (remote servers use <code>serverUrl</code>):
                        </p>
                        <CopyCodeBlock text={antigravityConfig} title="mcp_config.json" />
                      </div>
                    </div>
                  )}

                  {devPlatform === "chatgpt" && (
                    <div className="platform-guide-pane">
                      <div className="guide-card">
                        <h4>OpenAI Codex CLI</h4>
                        <CopyCodeBlock text={codexCli} title="Terminal command" />
                      </div>
                    </div>
                  )}

                  <div className="guide-card inspector-card">
                    <h4>Test the server</h4>
                    <p className="small">
                      Try every tool and prompt in the official MCP Inspector. Choose the{" "}
                      <strong>Streamable HTTP</strong> transport and paste the URL above:
                    </p>
                    <CopyCodeBlock text={mcpInspector} title="Run MCP Inspector" />
                  </div>
                </div>
              </details>
            </div>
          )}

          {/* TAB 2: USING THIS SITE */}
          {activeTab === "site" && (
            <div className="guide-section-content">
              <div className="guide-intro-banner">
                <p>
                  <strong>From a long list to one good idea in three steps.</strong> Narrow the list, check one project
                  closely, then ask Claude.
                </p>
              </div>

              <div className="playbook-steps-container">
                <div className="playbook-step-card">
                  <div className="step-badge">Step 1</div>
                  <div className="step-body">
                    <h4>Narrow the list</h4>
                    <p className="small">Use the filter bar above the cards. A good starting point:</p>
                    <ul className="guide-bullet-list small">
                      <li>
                        <strong>Companies already pay for it</strong>: choose <code>License → Permissive</code> and
                        <code> Advanced → Business signals</code>.
                      </li>
                    </ul>
                  </div>
                </div>

                <div className="playbook-step-card">
                  <div className="step-badge">Step 2</div>
                  <div className="step-body">
                    <h4>Open a project and read the signals</h4>
                    <p className="small">Click any card to open the details. Three things matter most:</p>
                    <div className="signal-cheatsheet-grid">
                      <div className="cheatsheet-item">
                        <strong>Fork ratio of 12% or more</strong>
                        <span>Companies are running and customising it themselves.</span>
                      </div>
                      <div className="cheatsheet-item">
                        <strong>License</strong>
                        <span>
                          <em>Permissive</em> (MIT, Apache 2.0): safe to sell in a closed product.
                          <br />
                          <em>Weak copyleft</em>: changes to the library itself must be shared.
                          <br />
                          <em>AGPL</em>: keep it behind a separate service, or get a lawyer's advice.
                        </span>
                      </div>
                      <div className="cheatsheet-item">
                        <strong>MCP Prompt Library</strong>
                        <span>Pick a lens (e.g. <em>Vertical SaaS</em>, <em>White-Label Audit</em>) and copy it in 1 click.</span>
                      </div>
                    </div>
                  </div>
                </div>

                <div className="playbook-step-card">
                  <div className="step-badge">Step 3</div>
                  <div className="step-body">
                    <h4>Ask your AI</h4>
                    <p className="small">
                      Paste the copied prompt into any chat, or connect Claude, ChatGPT or Gemini (first tab) and just
                      ask in your own words.
                    </p>
                  </div>
                </div>
              </div>

              <details className="guide-fold">
                <summary>For developers: keep the data fresh</summary>
                <div className="guide-fold-body">
                  <CopyCodeBlock
                    text={`# Daily update (refreshes star gains and new repos):\nuv run --package ossdex-collector ossdex-collector update`}
                    title="Terminal commands"
                  />
                </div>
              </details>
            </div>
          )}

          {/* TAB 3: WHAT CLAUDE CAN DO */}
          {activeTab === "can-do" && (
            <div className="guide-section-content">
              <div className="guide-intro-banner">
                <p>Once connected, ask Claude in plain words. Behind the scenes it picks the right ossdex tool:</p>
              </div>

              <ul className="guide-can-do">
                {CAN_DO.map((c) => (
                  <li key={c.tool}>
                    <span>{c.ask}</span>
                    <code>{c.tool}</code>
                  </li>
                ))}
              </ul>
              <p className="muted small">
                There are also ready-made prompts (idea brainstorming, learning plans, moat analysis). In Claude, click{" "}
                <strong>+</strong> in the chat box and look under ossdex.
              </p>

              <details className="guide-fold">
                <summary>Full tool and prompt reference</summary>
                <div className="guide-fold-body">
              <h4 style={{ marginTop: 16 }}>Search, Discovery & Sizing (11 tools)</h4>
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

              <h4 style={{ marginTop: 24 }}>Diagnostic & Brief Evaluation (13 tools, F1–F10 guardrails)</h4>
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

              <h3 style={{ marginTop: 28 }}>13 ready-made prompts</h3>
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
              </details>
            </div>
          )}
        </div>
      </article>
    </div>
  );
}
