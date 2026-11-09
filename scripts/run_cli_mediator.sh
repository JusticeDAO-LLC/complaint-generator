#!/usr/bin/env bash
set -euo pipefail
umask 077

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_PYTHON="${ROOT_DIR}/.venv/bin/python"
TEMP_ROOT="${ROOT_DIR}/statefiles"

mkdir -p "${TEMP_ROOT}"

export PATH="${ROOT_DIR}/.venv/bin:${PATH}"
export TMPDIR="${TEMP_ROOT}"
export COMPLAINT_GENERATOR_TMPDIR="${TEMP_ROOT}"
export COMPLAINT_GENERATOR_APPLICATION_TYPE="cli"
if [[ -z "${COMPLAINT_GENERATOR_MEDIATOR_BACKENDS:-}" ]]; then
	export COMPLAINT_GENERATOR_MEDIATOR_BACKENDS="llm-router-grok-4.7"
fi
export COMPLAINT_GENERATOR_ROUTER_PROGRESS=1
export COMMON_CRAWL_AUTO_CLONE_SOURCE=0
export PYTHONDONTWRITEBYTECODE=1
export PYTHONWARNINGS="ignore::SyntaxWarning"

select_working_python() {
	local candidate
	local candidates=()
	if [[ -n "${COMPLAINT_GENERATOR_PYTHON:-}" ]]; then
		candidates+=("${COMPLAINT_GENERATOR_PYTHON}")
	fi
	if [[ -x "${VENV_PYTHON}" ]]; then
		candidates+=("${VENV_PYTHON}")
	fi
	if command -v python3.12 >/dev/null 2>&1; then
		candidates+=("$(command -v python3.12)")
	fi
	if command -v python3 >/dev/null 2>&1; then
		candidates+=("$(command -v python3)")
	fi
	for candidate in "${candidates[@]}"; do
		if [[ -n "${candidate}" ]] && "${candidate}" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' >/dev/null 2>&1; then
			PYTHON="${candidate}"
			return 0
		fi
	done
	echo "No working Python interpreter found." >&2
	exit 127
}

select_working_python

if [[ "${COMPLAINT_GENERATOR_LAUNCHER_DRY_RUN:-}" == "1" ]]; then
	printf '%s\n' "${PYTHON}"
	printf '%s\n' "${COMPLAINT_GENERATOR_MEDIATOR_BACKENDS}"
	exit 0
fi

cd "${ROOT_DIR}"
exec "${PYTHON}" -m applications.complaint_cli chat "$@"
