#!/usr/bin/env bash
# Tacit Claude Code Hook — captures session transcripts on Stop events.
# Reads JSON from stdin (Claude Code hook protocol), sends transcript_path
# and cwd to the Tacit backend for AI-powered knowledge extraction.
#
# Install: copy this file and make executable, then add to Claude Code hooks config.

set -euo pipefail

TACIT_URL="${TACIT_URL:-http://localhost:8000}"

# Read hook event JSON from stdin
INPUT=$(cat)

# Extract fields
EVENT=$(echo "$INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('hook_event_name',''))" 2>/dev/null || echo "")

if [ "$EVENT" != "Stop" ]; then
  exit 0
fi

TRANSCRIPT=$(echo "$INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('transcript_path',''))" 2>/dev/null || echo "")
CWD=$(echo "$INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('cwd',''))" 2>/dev/null || echo "")
SESSION_ID=$(echo "$INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('session_id',''))" 2>/dev/null || echo "")

if [ -z "$TRANSCRIPT" ]; then
  exit 0
fi

# POST to Tacit backend (fire-and-forget, don't block Claude Code)
curl -s -X POST "${TACIT_URL}/api/hooks/capture" \
  -H "Content-Type: application/json" \
  -d "{\"transcript_path\": \"${TRANSCRIPT}\", \"cwd\": \"${CWD}\", \"session_id\": \"${SESSION_ID}\"}" \
  --max-time 5 \
  >/dev/null 2>&1 || true
