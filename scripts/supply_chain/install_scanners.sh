#!/usr/bin/env bash
set -euo pipefail
# Checksums from the primary release assets. Linux x86-64 only (CI ubuntu-latest).
work=$(mktemp -d)
target="${1:?Usage: install_scanners.sh DIRECTORY}"
mkdir -p "$target"
curl --fail --location --silent --show-error https://github.com/gitleaks/gitleaks/releases/download/v8.30.1/gitleaks_8.30.1_linux_x64.tar.gz -o "$work/gitleaks.tar.gz"
printf '%s  %s\n' 551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb "$work/gitleaks.tar.gz" | sha256sum --check
tar -xzf "$work/gitleaks.tar.gz" -C "$target" gitleaks
curl --fail --location --silent --show-error https://github.com/anchore/grype/releases/download/v0.119.0/grype_0.119.0_linux_amd64.tar.gz -o "$work/grype.tar.gz"
printf '%s  %s\n' 3fa2dc4b924621ab65404cf08d0b8438d896d80ab949c9d5a4ca283c36004c9b "$work/grype.tar.gz" | sha256sum --check
tar -xzf "$work/grype.tar.gz" -C "$target" grype
"$target/gitleaks" version
"$target/grype" version
