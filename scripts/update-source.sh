#!/usr/bin/env bash
set -euo pipefail

REPO_URL="${1:-}"
BRANCH="${2:-main}"
ROOT="${GROSTER_ROOT:-/opt/groster}"
SRC="${ROOT}/source"

if [[ -z "${REPO_URL}" ]]; then
  echo "Usage: $0 <git-repo-url> [branch]" >&2
  exit 2
fi

sudo mkdir -p "${ROOT}"
if [[ -d "${SRC}/.git" ]]; then
  sudo git -C "${SRC}" fetch origin "${BRANCH}"
  sudo git -C "${SRC}" checkout "${BRANCH}"
  sudo git -C "${SRC}" pull --ff-only origin "${BRANCH}"
else
  sudo rm -rf "${SRC}"
  sudo git clone --branch "${BRANCH}" "${REPO_URL}" "${SRC}"
fi

echo "Source is now in ${SRC}"
