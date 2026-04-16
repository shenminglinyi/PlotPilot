#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "[1/4] root: ${ROOT_DIR}"

if [[ ! -d "${ROOT_DIR}/.venv" ]]; then
  echo "Missing Python virtualenv at ${ROOT_DIR}/.venv"
  echo "Create it with:"
  echo "  python3 -m venv .venv"
  echo "  source .venv/bin/activate"
  echo "  pip install -r requirements.txt"
  exit 1
fi

if [[ ! -d "${ROOT_DIR}/frontend/node_modules" ]]; then
  echo "Missing frontend dependencies at ${ROOT_DIR}/frontend/node_modules"
  echo "Install them with:"
  echo "  cd frontend && npm install"
  exit 1
fi

echo "[2/4] starting backend on http://127.0.0.1:8005"
(
  cd "${ROOT_DIR}"
  source ".venv/bin/activate"
  python -m uvicorn interfaces.main:app --host 127.0.0.1 --port 8005 --reload
) &
BACKEND_PID=$!

echo "[3/4] starting frontend on http://127.0.0.1:3000"
(
  cd "${ROOT_DIR}/frontend"
  npm run dev -- --host 127.0.0.1 --port 3000
) &
FRONTEND_PID=$!

cleanup() {
  kill "${BACKEND_PID}" "${FRONTEND_PID}" 2>/dev/null || true
}

trap cleanup EXIT INT TERM

echo "[4/4] backend pid=${BACKEND_PID}, frontend pid=${FRONTEND_PID}"
wait "${BACKEND_PID}" "${FRONTEND_PID}"
