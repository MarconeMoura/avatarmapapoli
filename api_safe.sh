#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="$ROOT_DIR/.api.pid"
LOG_FILE="$ROOT_DIR/.api.log"
BACKUP_ROOT="$ROOT_DIR/.backups"
PYTHON_BIN="$ROOT_DIR/.venv/bin/python"
PORT="9000"
UVICORN_MATCH="uvicorn .*avatar:app.*--port ${PORT}"

is_pid_running() {
  local pid="$1"
  [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null
}

resolve_running_pid() {
  if [[ -f "$PID_FILE" ]]; then
    local pid
    pid="$(tr -d '[:space:]' < "$PID_FILE")"
    if is_pid_running "$pid"; then
      echo "$pid"
      return 0
    fi
  fi

  local pid
  pid="$(lsof -ti tcp:"$PORT" -sTCP:LISTEN 2>/dev/null | head -n 1 || true)"
  if [[ -n "$pid" ]]; then
    echo "$pid"
    return 0
  fi

  pid="$(pgrep -f "$UVICORN_MATCH" | head -n 1 || true)"
  if [[ -n "$pid" ]]; then
    echo "$pid"
    return 0
  fi

  return 1
}

create_backup() {
  local ts dest
  ts="$(date +"%Y%m%d-%H%M%S")"
  dest="$BACKUP_ROOT/$ts"
  mkdir -p "$dest"

  local files=(
    "avatar.py"
    "main.py"
    "avatar"
    "Static/index"
    ".vscode/launch.json"
    ".vscode/tasks.json"
    ".env"
  )

  local copied=0
  for rel in "${files[@]}"; do
    if [[ -f "$ROOT_DIR/$rel" ]]; then
      cp "$ROOT_DIR/$rel" "$dest/${rel//\//__}"
      copied=1
    fi
  done

  if [[ "$copied" -eq 1 ]]; then
    echo "Backup criado em: $dest"
  else
    echo "Nenhum arquivo encontrado para backup."
  fi
}

start_api() {
  if resolve_running_pid >/dev/null 2>&1; then
    local pid
    pid="$(resolve_running_pid)"
    echo "API ja esta rodando na porta $PORT (PID $pid)."
    return 0
  fi

  if [[ ! -x "$PYTHON_BIN" ]]; then
    echo "Erro: Python do venv nao encontrado em $PYTHON_BIN"
    exit 1
  fi

  create_backup
  nohup "$PYTHON_BIN" -m uvicorn avatar:app --reload --host 127.0.0.1 --port "$PORT" > "$LOG_FILE" 2>&1 &
  local pid=$!
  echo "$pid" > "$PID_FILE"
  sleep 1

  if is_pid_running "$pid"; then
    echo "API iniciada com sucesso (PID $pid)."
    echo "Log: $LOG_FILE"
  else
    echo "Falha ao iniciar API. Verifique o log: $LOG_FILE"
    exit 1
  fi
}

stop_api() {
  if ! resolve_running_pid >/dev/null 2>&1; then
    rm -f "$PID_FILE"
    echo "API ja estava parada na porta $PORT."
    return 0
  fi

  local pid
  pid="$(resolve_running_pid)"
  kill "$pid" 2>/dev/null || true

  for _ in {1..20}; do
    if ! is_pid_running "$pid"; then
      break
    fi
    sleep 0.2
  done

  if is_pid_running "$pid"; then
    kill -9 "$pid" 2>/dev/null || true
  fi

  rm -f "$PID_FILE"
  echo "API parada (PID $pid)."
}

status_api() {
  if resolve_running_pid >/dev/null 2>&1; then
    local pid
    pid="$(resolve_running_pid)"
    echo "API rodando (PID $pid)."
  else
    echo "API parada."
  fi
}

toggle_api() {
  if resolve_running_pid >/dev/null 2>&1; then
    stop_api
  else
    start_api
  fi
}

case "${1:-}" in
  start)
    start_api
    ;;
  stop)
    stop_api
    ;;
  toggle)
    toggle_api
    ;;
  status)
    status_api
    ;;
  backup)
    create_backup
    ;;
  *)
    echo "Uso: $0 {start|stop|toggle|status|backup}"
    exit 1
    ;;
esac
