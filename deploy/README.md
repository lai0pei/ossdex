# Deploying ossdex on a VPS

One machine runs both halves: the collector (daily cron) writes `data/ossdex.db`, the server reads it.
Placeholders: `ossdex.example.com` is your hostname.

## 1. Install
```sh
useradd --system --create-home --shell /usr/sbin/nologin ossdex   # or any service user
git clone <repo> /srv/ossdex && chown -R ossdex: /srv/ossdex
cd /srv/ossdex
sudo -u ossdex uv sync --all-packages
# UI: build it on the VPS (needs node), or build locally and copy web/dist
cd web && npm ci && npm run build
```
Install `uv` to `/usr/local/bin` (the unit and cron file expect it there).

## 2. First data load
```sh
install -m 600 -o ossdex /dev/null /srv/ossdex/.env
echo 'GITHUB_TOKEN=ghp_...' >> /srv/ossdex/.env        # a token with no scopes is enough
sudo -u ossdex uv run --package ossdex-collector ossdex-collector update
```
Then install the daily job: `cp deploy/ossdex-collector.cron /etc/cron.d/ossdex-collector`.

## 3. The server
```sh
mkdir -p /etc/ossdex
install -m 640 -o root -g ossdex deploy/server.env.example /etc/ossdex/server.env   # edit host and workers
cp deploy/ossdex-server.service /etc/systemd/system/
systemctl daemon-reload && systemctl enable --now ossdex-server
curl http://127.0.0.1:8200/api/status
```
`OSSDEX_WORKERS` should be the number of CPU cores. Each worker answers one request at a time, so this
is how many requests are served in parallel.

## 4. Caddy and Cloudflare
1. Cloudflare: add a proxied DNS record for the host. SSL/TLS mode **Full (strict)**.
2. SSL/TLS -> Origin Server -> create an Origin Certificate; save as `/etc/caddy/origin.pem` and
   `origin.key` (readable by `caddy`).
3. Put `deploy/Caddyfile` at `/etc/caddy/Caddyfile` (change the host), then `systemctl reload caddy`.
4. Caching -> Cache Rules: cache `/api/*` (respect origin headers).
5. Security: keep **Bot Fight Mode off**. It can challenge Anthropic's server-to-server connector
   requests, and the connector then fails.
6. `sudo deploy/cloudflare-firewall.sh` -- 443 only from Cloudflare, plus SSH.

The rate limiter takes the client address from `CF-Connecting-IP` only when the request arrives from
127.0.0.1 (Caddy). Port 8200 stays bound to localhost; do not expose it.

## 5. Add the connector
claude.ai -> Settings -> Connectors -> Add custom connector -> `https://ossdex.example.com/mcp`, no
authentication. It then shows up in the Claude mobile app. No account is needed to use it.

## 6. Check
```sh
curl https://ossdex.example.com/api/status
npx @modelcontextprotocol/inspector      # Streamable HTTP, URL https://ossdex.example.com/mcp
uv run python scripts/loadtest.py --help # then run it against the public URL
```
The load test goes through Cloudflare, so use a high `OSSDEX_RATE_WEB`/`OSSDEX_RATE_MCP` while testing
and put them back afterwards. Finally, run `search_repos` from the Claude mobile app.

## Operating
- Logs: `journalctl -u ossdex-server`, `/srv/ossdex/data/update.log`, `/var/log/caddy/ossdex.log`.
- After a data update the server notices the new commit and drops its response cache by itself.
- Update the code: `git pull && uv sync --all-packages && (cd web && npm ci && npm run build) && systemctl restart ossdex-server`.
- Back up `data/ossdex.db` with `sqlite3 data/ossdex.db ".backup backup.db"`, not a plain copy.
