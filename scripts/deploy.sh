#!/usr/bin/env bash
set -Eeuo pipefail

readonly expected_commit="${1:?Expected commit SHA is required}"
readonly prod_path="${2:?Production path is required}"
readonly production_branch="master"

cd "$prod_path"

if [[ ! -d .git ]]; then
    echo "Production repository not found at: $prod_path" >&2
    exit 1
fi

if [[ ! -f .env ]]; then
    echo "Production .env is missing." >&2
    exit 1
fi

if [[ ! -f docker-compose.podman.yml ]]; then
    echo "docker-compose.podman.yml is missing." >&2
    exit 1
fi

# Block modifications to tracked files.
# Untracked local deployment files such as .env or docker-compose.podman.yml
# are intentionally allowed.
if ! git diff --quiet || ! git diff --cached --quiet; then
    echo "Tracked production files contain local changes; deployment stopped." >&2
    git status --short >&2
    exit 1
fi

echo "Fetching production branch..."
git fetch --prune origin "$production_branch"

echo "Checking out exact tested commit..."
git checkout "$production_branch"
git reset --hard "$expected_commit"

if [[ "$(git rev-parse HEAD)" != "$expected_commit" ]]; then
    echo "Deployment commit verification failed." >&2
    exit 1
fi

echo "Validating Podman Compose configuration..."
podman compose \
    -f docker-compose.yml \
    -f docker-compose.podman.yml \
    config --quiet

echo "Building application images..."
podman compose \
    -f docker-compose.yml \
    -f docker-compose.podman.yml \
    build app scheduler telegram_gateway

echo "Removing stale one-shot app container..."
podman rm -f crypto_app 2>/dev/null || true

echo "Rolling out application services..."
podman compose \
    -f docker-compose.yml \
    -f docker-compose.podman.yml \
    up -d \
    --force-recreate \
    --no-deps \
    scheduler telegram_gateway

echo "Current containers:"
podman compose \
    -f docker-compose.yml \
    -f docker-compose.podman.yml \
    ps

echo "Verifying production services..."

scheduler_state="$(podman inspect crypto_scheduler --format '{{.State.Status}}')"
gateway_state="$(podman inspect crypto_telegram_gateway --format '{{.State.Status}}')"
tailscale_health="$(podman inspect crypto_tailscale --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}')"
db_health="$(podman inspect crypto_timescaledb --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}')"

echo "scheduler:        $scheduler_state"
echo "telegram_gateway: $gateway_state"
echo "tailscale:        $tailscale_health"
echo "timescaledb:      $db_health"

[[ "$scheduler_state" == "running" ]]
[[ "$gateway_state" == "running" ]]
[[ "$tailscale_health" == "healthy" ]]
[[ "$db_health" == "healthy" ]]

echo "Deployment health verification passed."

echo "Deployment completed successfully."
