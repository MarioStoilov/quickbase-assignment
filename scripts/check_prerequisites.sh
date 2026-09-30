#!/usr/bin/env bash
# Check that the tools the project needs are installed, before anything is set up.
#
#   scripts/check_prerequisites.sh      run every check, exit 1 when any fails
#
# Run by `make check-prerequisites` and first in `make install`. Each check prints one
# PASS or FAIL line; a FAIL line names what is missing or too old and where to get it.
# The script changes nothing and never asks for root.
set -u

# ------------------------------------------------------------------------------------
# Constants
# ------------------------------------------------------------------------------------

# Oldest Python version the backend supports, as declared in pyproject.toml.
MINIMUM_PYTHON_VERSION="3.12"

# Oldest Node.js major version the frontend's toolchain supports.
MINIMUM_NODE_MAJOR_VERSION=20

# Where to get uv, printed when it is missing.
UV_INSTALL_URL="https://docs.astral.sh/uv/"

# Where to get Node.js, printed when it or npm is missing.
NODE_INSTALL_URL="https://nodejs.org/"

# ------------------------------------------------------------------------------------
# Run-wide state (set by the checks, read by main)
# ------------------------------------------------------------------------------------

# How many checks failed; the exit code is 1 when this is not zero.
failed_check_count=0

# ------------------------------------------------------------------------------------
# Reporting helpers
# ------------------------------------------------------------------------------------

# Print a PASS line.
#   $1  what was found, for example "python 3.12.1"
report_pass() {
  local finding="$1"

  echo "PASS  ${finding}"
}

# Print a FAIL line and count the failure.
#   $1  what is wrong and what to do about it
report_fail() {
  local problem="$1"

  echo "FAIL  ${problem}"
  failed_check_count=$((failed_check_count + 1))
}

# ------------------------------------------------------------------------------------
# Probing helpers
# ------------------------------------------------------------------------------------

# Succeed when a command is on the PATH.
#   $1  the command name
command_exists() {
  local command_name="$1"

  command -v "${command_name}" >/dev/null 2>&1
}

# Succeed when a dotted version is at least a required dotted version.
#   $1  the version found, for example "3.12.1"
#   $2  the version required, for example "3.12"
version_at_least() {
  local found_version="$1"
  local required_version="$2"
  local lowest_version

  lowest_version="$(printf '%s\n%s\n' "${required_version}" "${found_version}" | sort -V | head -n 1)"

  [ "${lowest_version}" = "${required_version}" ]
}

# ------------------------------------------------------------------------------------
# Checks, one per tool
# ------------------------------------------------------------------------------------

# Python 3 must be installed and at least MINIMUM_PYTHON_VERSION.
check_python() {
  local python_version

  if ! command_exists python3; then
    report_fail "python3 is not installed; ${MINIMUM_PYTHON_VERSION} or newer is required"
    return
  fi

  python_version="$(python3 --version 2>&1 | cut -d' ' -f2)"

  if version_at_least "${python_version}" "${MINIMUM_PYTHON_VERSION}"; then
    report_pass "python ${python_version}"
  else
    report_fail "python3 is ${python_version}; ${MINIMUM_PYTHON_VERSION} or newer is required"
  fi
}

# uv must be installed; it provisions the virtual environment and runs every backend target.
check_uv() {
  local uv_version

  if ! command_exists uv; then
    report_fail "uv is not installed; see ${UV_INSTALL_URL}"
    return
  fi

  uv_version="$(uv --version 2>&1 | cut -d' ' -f2)"
  report_pass "uv ${uv_version}"
}

# Node.js must be installed and at least MINIMUM_NODE_MAJOR_VERSION.
check_node() {
  local node_version
  local node_major_version

  if ! command_exists node; then
    report_fail "node is not installed; Node.js ${MINIMUM_NODE_MAJOR_VERSION} or newer is required, see ${NODE_INSTALL_URL}"
    return
  fi

  node_version="$(node --version 2>&1)"
  node_major_version="$(echo "${node_version}" | sed 's/^v//' | cut -d'.' -f1)"

  if [ "${node_major_version}" -ge "${MINIMUM_NODE_MAJOR_VERSION}" ]; then
    report_pass "node ${node_version}"
  else
    report_fail "node is ${node_version}; Node.js ${MINIMUM_NODE_MAJOR_VERSION} or newer is required"
  fi
}

# npm must be installed; it installs and runs the frontend.
check_npm() {
  local npm_version

  if ! command_exists npm; then
    report_fail "npm is not installed; it ships with Node.js, see ${NODE_INSTALL_URL}"
    return
  fi

  npm_version="$(npm --version 2>&1)"
  report_pass "npm ${npm_version}"
}

# ------------------------------------------------------------------------------------
# Main
# ------------------------------------------------------------------------------------

main() {
  check_python
  check_uv
  check_node
  check_npm

  if [ "${failed_check_count}" -ne 0 ]; then
    echo "${failed_check_count} prerequisite check(s) failed"
    exit 1
  fi

  echo "all prerequisites found"
}

main "$@"
