#!/usr/bin/env bash
set -euo pipefail

# This smoke is deliberately a no-op unless the caller supplies a credential reference.
# It never prints credential values or claims a hosted request passed.
refs=(AZURE_OPENAI_CREDENTIAL_REF BEDROCK_CREDENTIAL_REF ANTHROPIC_CREDENTIAL_REF GEMINI_CREDENTIAL_REF GROQ_CREDENTIAL_REF OPENAI_COMPATIBLE_CREDENTIAL_REF)
for ref in "${refs[@]}"; do
  if [[ -n "${!ref:-}" ]]; then
    printf 'SKIP: credential reference %s is configured, but hosted smoke requires an explicitly approved live target.\n' "$ref"
    exit 0
  fi
done
printf 'SKIP: no hosted credential references are configured.\n'
