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

echo "Deploying..."
podman compose \
    -f docker-compose.yml \
    -f docker-compose.podman.yml \
    up -d --build --remove-orphans

echo "Current containers:"
podman compose \
    -f docker-compose.yml \
    -f docker-compose.podman.yml \
    ps

echo "Deployment completed successfully."
