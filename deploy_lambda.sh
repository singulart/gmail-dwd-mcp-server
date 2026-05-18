#!/usr/bin/env bash
# Package and upload the Gmail DWD MCP Lambda deployment artifact to S3.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUCKET="${LAMBDA_S3_BUCKET:-argorand-lambdas-repository}"
BUILD_DIR="${ROOT}/.lambda-build"
PYTHON="${PYTHON:-python3}"
LAMBDA_NAME="gmail-dwd-mcp"

usage() {
  cat <<EOF
Usage: $(basename "$0") [all|gmail-dwd-mcp]

Environment:
  LAMBDA_S3_BUCKET  S3 bucket (default: argorand-lambdas-repository)
  PYTHON            Python interpreter for pip fallback (default: python3)

Builds use Docker (public.ecr.aws/lambda/python:3.14-arm64 on AL2023) when available
so native deps match the Lambda runtime. The pip fallback targets manylinux_2_34 /
manylinux_2_28 aarch64 (not manylinux2014).

Upload key:
  s3://\$BUCKET/gmail-dwd-mcp/deployment.zip
EOF
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "Missing required command: $1" >&2
    exit 1
  }
}

verify_linux_arm64_binaries() {
  local pkg_dir="$1"
  local bad=""

  while IFS= read -r -d '' so; do
    if ! file "${so}" | grep -q 'ELF 64-bit.*ARM aarch64'; then
      bad="${bad}\n  ${so}: $(file -b "${so}")"
    fi
  done < <(find "${pkg_dir}" -name '*.so' -print0 2>/dev/null)

  if [[ -n "${bad}" ]]; then
    echo "ERROR: Found non-Linux-arm64 shared libraries in the Lambda package:${bad}" >&2
    echo "Rebuild with Docker (recommended) or fix pip --platform flags; do not use macOS-native wheels." >&2
    exit 1
  fi
}

install_deps_docker() {
  local req="$1"
  local pkg_dir="$2"
  local image="public.ecr.aws/lambda/python:3.14-arm64"

  docker run --rm --platform linux/arm64 \
    --entrypoint /bin/bash \
    -v "${req}:/tmp/requirements.txt:ro" \
    -v "${pkg_dir}:/out" \
    "${image}" \
    -lc "python -m pip install -r /tmp/requirements.txt -t /out --quiet && chmod -R a+rX /out"
}

install_deps_pip() {
  local req="$1"
  local pkg_dir="$2"

  # Lambda Python 3.14 runs on Amazon Linux 2023 (glibc 2.34). Prefer manylinux_2_34
  # wheels; manylinux_2_28 covers packages that have not published 2_34 builds yet.
  # Do not use manylinux2014 — it targets glibc 2.17 and is obsolete for AL2023.
  "${PYTHON}" -m pip install -r "${req}" -t "${pkg_dir}" --quiet \
    --platform manylinux_2_34_aarch64 \
    --platform manylinux_2_28_aarch64 \
    --implementation cp \
    --python-version 3.14 \
    --only-binary=:all: || {
    echo "pip cross-install failed; install Docker and re-run (recommended)." >&2
    exit 1
  }
}

build_gmail_dwd_mcp() {
  local src="${ROOT}/lambda/${LAMBDA_NAME}"
  local work="${BUILD_DIR}/${LAMBDA_NAME}"
  local pkg="${work}/package"
  local zip="${work}/deployment.zip"
  local req="${src}/requirements.txt"

  rm -rf "${work}"
  mkdir -p "${pkg}"

  if command -v docker >/dev/null 2>&1; then
    echo "Building ${LAMBDA_NAME} dependencies in Lambda Python 3.14 arm64 Docker image..."
    install_deps_docker "${req}" "${pkg}"
  else
    echo "Docker not found; using pip cross-install (manylinux_2_34 / manylinux_2_28 aarch64)..."
    install_deps_pip "${req}" "${pkg}"
  fi

  verify_linux_arm64_binaries "${pkg}"

  echo "Copying application source..."
  cp -R "${ROOT}/src/gmail_dwd_mcp" "${pkg}/"
  cp "${src}/handler.py" "${pkg}/"

  (cd "${pkg}" && zip -qr "${zip}" .)
  echo "Zip sanity check:"
  unzip -l "${zip}" | grep -E 'handler.py|gmail_dwd_mcp/|mcp/|google/' | head -20 || true

  aws s3 cp "${zip}" "s3://${BUCKET}/${LAMBDA_NAME}/deployment.zip" --checksum-algorithm SHA256
  echo "Uploaded s3://${BUCKET}/${LAMBDA_NAME}/deployment.zip"
}

main() {
  require_cmd aws
  require_cmd zip
  require_cmd "${PYTHON}"

  local target="${1:-all}"
  case "${target}" in
    all|gmail-dwd-mcp)
      build_gmail_dwd_mcp
      ;;
    -h|--help|help)
      usage
      ;;
    *)
      echo "Unknown target: ${target}" >&2
      usage
      exit 1
      ;;
  esac
}

main "$@"
