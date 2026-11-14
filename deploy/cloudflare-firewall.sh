#!/usr/bin/env bash
# Allow 443 only from Cloudflare, SSH from anywhere (tighten as you like). Needs ufw and curl; run as root.
# Re-run now and then: Cloudflare's ranges change rarely.
set -euo pipefail
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp
for range in $(curl -fsS https://www.cloudflare.com/ips-v4 https://www.cloudflare.com/ips-v6); do
  ufw allow from "$range" to any port 443 proto tcp
done
ufw --force enable
ufw status numbered
