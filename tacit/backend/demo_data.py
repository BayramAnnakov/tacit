"""Rich demo dataset for --demo mode.

Realistic OpenClaw-like rules with real PR links, anti-patterns, CI fixes.
No API keys needed — seeds directly into the local SQLite database.
"""

import asyncio

import database as db

# Real OpenClaw PR numbers for provenance links
_BASE = "https://github.com/openclaw/openclaw/pull"


DEMO_RULES: list[dict] = [
    # ── Anti-patterns (from CHANGES_REQUESTED reviews) ──────────────────
    {
        "rule_text": "NEVER commit package-lock.json — this project uses pnpm with pnpm-lock.yaml. An npm lockfile creates conflicting dependency sources and CI drift.",
        "category": "workflow",
        "confidence": 0.97,
        "source_type": "anti_pattern",
        "provenance_url": f"{_BASE}/15715",
        "provenance_summary": "Contributor ran npm install in a pnpm repo, generating a 14,000-line package-lock.json. Two reviewers flagged it independently.",
        "applicable_paths": "package.json,pnpm-lock.yaml",
    },
    {
        "rule_text": "NEVER compute a result without applying it back — computing a value and then discarding it is a logic bug that silently drops user-visible state.",
        "category": "architecture",
        "confidence": 0.95,
        "source_type": "anti_pattern",
        "provenance_url": f"{_BASE}/12669",
        "provenance_summary": "PR computed token counts but never stored them, causing the UI to show stale values. Reviewer caught the compute-and-discard pattern.",
        "applicable_paths": "src/**/*.ts",
    },
    {
        "rule_text": "NEVER use raw .toLowerCase() to canonicalize session keys or identifiers — use dedicated canonicalization functions. Raw lowercasing bypasses sentinel handling, prefix logic, and alias mapping.",
        "category": "architecture",
        "confidence": 0.95,
        "source_type": "anti_pattern",
        "provenance_url": f"{_BASE}/12846",
        "provenance_summary": "Ghost sessions appeared because toLowerCase() collapsed distinct keys. Multiple review rounds established the canonicalization pattern.",
        "applicable_paths": "src/sessions/**/*.ts",
    },
    {
        "rule_text": "NEVER reuse the context window token constant for output token limits — they serve different purposes and conflating them causes silent truncation.",
        "category": "architecture",
        "confidence": 0.93,
        "source_type": "anti_pattern",
        "provenance_url": f"{_BASE}/12667",
        "provenance_summary": "Output was being truncated because the context_tokens constant was reused for max_output_tokens. Reviewer identified the semantic mismatch.",
        "applicable_paths": "src/**/*.ts",
    },
    {
        "rule_text": "NEVER include API-specific payload fields unconditionally — gate optional fields on the relevant type/mode. Discord's url field is only valid for type 1 (Streaming).",
        "category": "architecture",
        "confidence": 0.92,
        "source_type": "anti_pattern",
        "provenance_url": f"{_BASE}/10855",
        "provenance_summary": "Discord API rejected requests because 'url' field was sent for non-streaming activity types. Reviewer required type-gating.",
        "applicable_paths": "src/discord/**/*.ts",
    },
    {
        "rule_text": "NEVER delete only the first legacy key match during session store migration — delete ALL case-variant legacy keys in a single pass to prevent ghost duplicates.",
        "category": "architecture",
        "confidence": 0.91,
        "source_type": "anti_pattern",
        "provenance_url": f"{_BASE}/12846#discussion_r1",
        "provenance_summary": "Phantom session entries appeared because only one legacy key variant was deleted. Fix required findStoreKeysIgnoreCase() to delete all variants.",
        "applicable_paths": "src/sessions/**/*.ts",
    },
    {
        "rule_text": "NEVER return timeout/null decisions as successful responses — callers cannot distinguish 'timed out' from 'explicitly allowed'. Return an explicit error or distinct status field.",
        "category": "architecture",
        "confidence": 0.90,
        "source_type": "anti_pattern",
        "provenance_url": f"{_BASE}/3357",
        "provenance_summary": "Exec approval timeout was returned as a null decision, which callers interpreted as 'allowed'. Multiple review rounds established the explicit status pattern.",
        "applicable_paths": "src/**/*.ts",
    },
    {
        "rule_text": "NEVER allow register() or Map-based pending-entry methods to silently overwrite existing entries — this strands the original request's promise/timer.",
        "category": "architecture",
        "confidence": 0.89,
        "source_type": "anti_pattern",
        "provenance_url": f"{_BASE}/3357#discussion_r2",
        "provenance_summary": "Duplicate registration silently overwrote a pending promise, causing the original request to hang indefinitely.",
        "applicable_paths": "src/**/*.ts",
    },
    {
        "rule_text": "NEVER normalize identifiers without deduplicating the result — keys like Assistant and assistant that normalize to the same value cause Map collisions and credential overwrites.",
        "category": "security",
        "confidence": 0.91,
        "source_type": "anti_pattern",
        "provenance_url": f"{_BASE}/7286",
        "provenance_summary": "Matrix account IDs normalized to the same value, causing credential overwrites and cross-account data leaks. Fix required dedup via Set.",
        "applicable_paths": "src/**/*.ts,extensions/**/*.ts",
    },
    {
        "rule_text": "NEVER use shallow object spread ({ ...base, ...override }) to merge config objects with nested fields — overrides silently replace entire nested objects. Use deep merge.",
        "category": "architecture",
        "confidence": 0.88,
        "source_type": "anti_pattern",
        "provenance_url": f"{_BASE}/7286#discussion_r3",
        "provenance_summary": "Matrix multi-account config lost nested settings because shallow spread replaced the entire nested object instead of merging keys.",
        "applicable_paths": "src/**/*.ts",
    },
    # ── PR-derived rules ────────────────────────────────────────────────
    {
        "rule_text": "Use Array.prototype.toSorted() instead of [...arr].sort() — the linter enforces toSorted() for immutable array sorting (Node 22+).",
        "category": "style",
        "confidence": 0.90,
        "source_type": "pr",
        "provenance_url": f"{_BASE}/14892",
        "provenance_summary": "Reviewer requested toSorted() to match the project's immutable-by-default pattern. Linter rule was added to enforce this.",
        "applicable_paths": "src/**/*.ts",
    },
    {
        "rule_text": "Keep files under ~700 LOC — split/refactor when it improves clarity or testability. Extract helpers instead of creating V2 copies.",
        "category": "style",
        "confidence": 0.88,
        "source_type": "pr",
        "provenance_url": f"{_BASE}/15094",
        "provenance_summary": "PR that grew a service file to 900+ lines was asked to extract helpers. Established the 700 LOC soft limit.",
        "applicable_paths": "src/**/*.ts",
    },
    {
        "rule_text": "Use shared CLI palette in src/terminal/palette.ts — no hardcoded ANSI colors. Status output must use tables + ANSI-safe wrapping via src/terminal/table.ts.",
        "category": "style",
        "confidence": 0.87,
        "source_type": "pr",
        "provenance_url": f"{_BASE}/14205",
        "provenance_summary": "PR with hardcoded color codes was rejected until they used the shared palette.",
        "applicable_paths": "src/cli/**/*.ts,src/terminal/**/*.ts",
    },
    {
        "rule_text": "Do not leave unused variables anywhere, including test files — CI enforces no-unused-variables and will fail the build.",
        "category": "style",
        "confidence": 0.92,
        "source_type": "pr",
        "provenance_url": f"{_BASE}/15652",
        "provenance_summary": "CI failed on a PR with unused test variables. Reviewer confirmed: no exceptions, even in test files.",
        "applicable_paths": "src/**/*.ts,extensions/**/*.ts",
    },
    {
        "rule_text": "When using vi.mock() at top level, use vi.clearAllMocks() or vi.resetAllMocks() in afterEach — NOT vi.restoreAllMocks(), which breaks module-level mock exports.",
        "category": "testing",
        "confidence": 0.91,
        "source_type": "pr",
        "provenance_url": f"{_BASE}/15154",
        "provenance_summary": "Tests were intermittently failing because restoreAllMocks() broke module-level mock exports. Multiple rounds established the clear/reset pattern.",
        "applicable_paths": "src/**/*.test.ts",
    },
    {
        "rule_text": "Plugin-only dependencies must live in the extension package.json, not root. Plugin runtime dependencies go in dependencies (npm install runs with --omit=dev).",
        "category": "architecture",
        "confidence": 0.88,
        "source_type": "pr",
        "provenance_url": f"{_BASE}/15715#discussion_r4",
        "provenance_summary": "Reviewer caught a plugin dependency in root package.json. Established the extension-scoped dependency rule.",
        "applicable_paths": "extensions/**/*",
    },
    {
        "rule_text": "NEVER use workspace:* in plugin dependencies — npm install breaks. Put openclaw in devDependencies or peerDependencies instead.",
        "category": "architecture",
        "confidence": 0.90,
        "source_type": "pr",
        "provenance_url": f"{_BASE}/14567",
        "provenance_summary": "Plugin using workspace:* caused npm install failures for users. Reviewer required peerDependencies.",
        "applicable_paths": "extensions/**/package.json",
    },
    {
        "rule_text": "Extract distinct responsibilities from large service classes into separate utility classes. Target reducing monolithic services to pure orchestration logic.",
        "category": "architecture",
        "confidence": 0.85,
        "source_type": "pr",
        "provenance_url": f"{_BASE}/13201",
        "provenance_summary": "Large PR refactored a 1200-line service into orchestration + utilities. Reviewer praised the pattern and recommended it as standard.",
        "applicable_paths": "src/**/*.ts",
    },
    {
        "rule_text": "Protocol versioning: clients send minProtocol + maxProtocol in connect; PROTOCOL_VERSION lives in src/gateway/protocol/schema.ts. Always bump when changing wire format.",
        "category": "architecture",
        "confidence": 0.87,
        "source_type": "pr",
        "provenance_url": f"{_BASE}/11904",
        "provenance_summary": "Breaking wire format change without version bump caused client crashes. Established the version-bump-on-schema-change rule.",
        "applicable_paths": "src/gateway/**/*.ts",
    },
    {
        "rule_text": "Methods with side effects (send, agent, poll, chat.send) require an idempotencyKey in params to prevent duplicate execution.",
        "category": "architecture",
        "confidence": 0.89,
        "source_type": "pr",
        "provenance_url": f"{_BASE}/10234",
        "provenance_summary": "Duplicate message sends were caused by retries without idempotency keys. WebSocket protocol was updated to require them.",
        "applicable_paths": "src/gateway/**/*.ts",
    },
    {
        "rule_text": "Follow the WhatsApp channel pattern for multi-account: read account configs from channels.<channel>.accounts, use Map-based client storage keyed by accountId.",
        "category": "architecture",
        "confidence": 0.86,
        "source_type": "pr",
        "provenance_url": f"{_BASE}/7286#discussion_r5",
        "provenance_summary": "Matrix multi-account PR was asked to follow the established WhatsApp pattern. Became the reference implementation for all channels.",
        "applicable_paths": "src/telegram/**/*.ts,src/discord/**/*.ts,extensions/**/*.ts",
    },
    {
        "rule_text": "In SwiftUI, prefer Observation framework (@Observable, @Bindable) — do NOT introduce new ObservableObject usage; migrate existing usages when touching related code.",
        "category": "style",
        "confidence": 0.88,
        "source_type": "pr",
        "provenance_url": f"{_BASE}/14011",
        "provenance_summary": "PR using ObservableObject was rejected until migrated to @Observable. Reviewer established the migration-on-touch rule.",
        "applicable_paths": "apps/macos/**/*.swift",
    },
    # ── CI-fix rules ────────────────────────────────────────────────────
    {
        "rule_text": "Test subprocess interactions against non-POSIX shells (fish, nushell, zsh) in addition to bash. Non-POSIX shells can cause Claude Code to hang indefinitely.",
        "category": "testing",
        "confidence": 0.95,
        "source_type": "ci_fix",
        "provenance_url": f"{_BASE}/9812",
        "provenance_summary": "CI passed on bash but users reported hangs on fish shell. Fix added cross-shell test matrix.",
        "applicable_paths": "src/**/*.test.ts",
    },
    {
        "rule_text": "Do not set test workers above 16 — causes resource exhaustion and flaky failures on CI runners.",
        "category": "testing",
        "confidence": 0.90,
        "source_type": "ci_fix",
        "provenance_url": f"{_BASE}/13567",
        "provenance_summary": "CI started failing intermittently after worker count was raised to 20. Rolled back to 16 and documented the limit.",
        "applicable_paths": "vitest.*.config.ts",
    },
    {
        "rule_text": "Coverage thresholds: 70% lines, 70% functions, 55% branches, 70% statements. PRs that drop below these thresholds fail CI.",
        "category": "testing",
        "confidence": 0.92,
        "source_type": "ci_fix",
        "provenance_url": f"{_BASE}/12456",
        "provenance_summary": "Coverage was added to CI after a PR introduced uncovered critical paths. Thresholds were calibrated over several PRs.",
        "applicable_paths": "vitest.*.config.ts",
    },
    {
        "rule_text": "Run pnpm build && pnpm check && pnpm test locally before submission. CI requires format check + type checking (tsgo) + linting.",
        "category": "workflow",
        "confidence": 0.93,
        "source_type": "ci_fix",
        "provenance_url": f"{_BASE}/14001",
        "provenance_summary": "Multiple PRs were failing CI for formatting/type issues. Pre-submit checklist was added to CONTRIBUTING.md.",
        "applicable_paths": "",
    },
    {
        "rule_text": "Use oxfmt for formatting (not prettier). Run oxfmt --write to auto-fix, oxfmt --check to verify.",
        "category": "style",
        "confidence": 0.90,
        "source_type": "ci_fix",
        "provenance_url": f"{_BASE}/14320",
        "provenance_summary": "PR formatted with prettier was rejected by CI. Reviewer confirmed oxfmt is the project standard.",
        "applicable_paths": "src/**/*.ts",
    },
    {
        "rule_text": "Keep pnpm-lock.yaml and Bun patching in sync when touching deps/patches. CI runs tests on both Node.js and Bun.",
        "category": "workflow",
        "confidence": 0.88,
        "source_type": "ci_fix",
        "provenance_url": f"{_BASE}/14678",
        "provenance_summary": "Bun tests broke after a dependency patch was applied only to pnpm. Established the dual-sync requirement.",
        "applicable_paths": "pnpm-lock.yaml,package.json",
    },
    # ── Docs/config rules ───────────────────────────────────────────────
    {
        "rule_text": "Use 'OpenClaw' for product/app/docs headings; use 'openclaw' for CLI command, package/binary, paths, and config keys.",
        "category": "style",
        "confidence": 0.85,
        "source_type": "docs",
        "provenance_url": "",
        "provenance_summary": "",
        "applicable_paths": "docs/**/*",
    },
    {
        "rule_text": "Internal doc links (Mintlify): root-relative without .md/.mdx extension. Avoid em dashes and apostrophes in headings — they break Mintlify anchor links.",
        "category": "style",
        "confidence": 0.83,
        "source_type": "docs",
        "provenance_url": "",
        "provenance_summary": "",
        "applicable_paths": "docs/**/*.md,docs/**/*.mdx",
    },
    {
        "rule_text": "README (GitHub) must use absolute docs URLs (https://docs.openclaw.ai/...). Docs content must be generic — no personal device names/hostnames/paths.",
        "category": "style",
        "confidence": 0.82,
        "source_type": "docs",
        "provenance_url": "",
        "provenance_summary": "",
        "applicable_paths": "README.md,docs/**/*",
    },
    {
        "rule_text": "Changelog: user-facing changes only — no internal/meta notes.",
        "category": "workflow",
        "confidence": 0.80,
        "source_type": "docs",
        "provenance_url": "",
        "provenance_summary": "",
        "applicable_paths": "CHANGELOG.md",
    },
    {
        "rule_text": "Document security vulnerability reporting in a SECURITY.md file at the repository root, directing reporters to the organization's official bug bounty program.",
        "category": "security",
        "confidence": 0.85,
        "source_type": "docs",
        "provenance_url": "",
        "provenance_summary": "",
        "applicable_paths": "SECURITY.md",
    },
    # ── Structure/config rules ──────────────────────────────────────────
    {
        "rule_text": "Use TypeBox schemas as the single source of truth — runtime validation (AJV), JSON Schema export, and Swift codegen all derive from the same definition.",
        "category": "architecture",
        "confidence": 0.90,
        "source_type": "structure",
        "provenance_url": "",
        "provenance_summary": "",
        "applicable_paths": "src/gateway/protocol/**/*.ts",
    },
    {
        "rule_text": "Avoid Type.Union in tool input schemas (no anyOf/oneOf/allOf). Use stringEnum/optionalStringEnum for string lists. Use Type.Optional() instead of | null.",
        "category": "architecture",
        "confidence": 0.88,
        "source_type": "config",
        "provenance_url": "",
        "provenance_summary": "",
        "applicable_paths": "src/**/*.ts",
    },
    {
        "rule_text": "Config validation is strict — unknown keys, malformed types, or invalid values cause Gateway to refuse to start. Only openclaw doctor works when validation fails.",
        "category": "architecture",
        "confidence": 0.87,
        "source_type": "config",
        "provenance_url": "",
        "provenance_summary": "",
        "applicable_paths": "src/**/*.ts",
    },
    {
        "rule_text": "Hot reload modes: hybrid (default, auto-restarts for critical changes), hot, restart, off. Most fields hot-apply; gateway.* and infrastructure fields require restart.",
        "category": "architecture",
        "confidence": 0.85,
        "source_type": "config",
        "provenance_url": "",
        "provenance_summary": "",
        "applicable_paths": "src/**/*.ts",
    },
    {
        "rule_text": "Model refs use provider/model format (e.g. anthropic/claude-opus-4-6). Only use Anthropic's own API providers — third-party proxies are unsupported.",
        "category": "architecture",
        "confidence": 0.90,
        "source_type": "config",
        "provenance_url": "",
        "provenance_summary": "",
        "applicable_paths": "src/**/*.ts",
    },
    {
        "rule_text": "DM security defaults to pairing mode — unknown senders get a pairing code. Public DMs require explicit opt-in (dmPolicy: open, allowFrom: [*]).",
        "category": "security",
        "confidence": 0.92,
        "source_type": "config",
        "provenance_url": "",
        "provenance_summary": "",
        "applicable_paths": "src/**/*.ts",
    },
    {
        "rule_text": "Gateway binds to 127.0.0.1 (loopback) by default. Use --bind lan with OPENCLAW_GATEWAY_TOKEN for external access. Tailscale Funnel refuses to start unless auth.mode: password.",
        "category": "security",
        "confidence": 0.88,
        "source_type": "config",
        "provenance_url": "",
        "provenance_summary": "",
        "applicable_paths": "src/gateway/**/*.ts",
    },
]


# Simulated extraction timeline — each step has (delay_seconds, message, detail)
EXTRACTION_TIMELINE: list[tuple[float, str, str]] = [
    # Phase 1: Parallel analyzers
    (0.0, "phase", "\033[1;36m  Phase 1: Starting 6 parallel analyzers...\033[0m"),
    (0.8, "agent", "\033[32m    ✓\033[0m structural-analyzer: 14 conventions from repo structure"),
    (0.3, "agent", "\033[32m    ✓\033[0m docs-analyzer: 8 rules from CONTRIBUTING.md, README"),
    (0.5, "agent", "\033[32m    ✓\033[0m code-analyzer: 12 rules from linter/test configs"),
    (0.7, "agent", "\033[32m    ✓\033[0m domain-analyzer: 5 domain conventions from architecture docs"),
    (1.0, "agent", "\033[32m    ✓\033[0m ci-failure-miner: 6 implicit rules from CI fix patterns"),
    (1.2, "agent", "\033[32m    ✓\033[0m anti-pattern-miner: 10 \033[31m\"Do Not\"\033[0m rules from CHANGES_REQUESTED reviews"),
    # Phase 2: PR thread analysis
    (0.4, "phase", "\033[1;36m  Phase 2: Deep PR thread analysis...\033[0m"),
    (0.6, "agent", "\033[90m    → Scanning 50 PRs for knowledge-rich discussions...\033[0m"),
    (0.8, "agent", "\033[32m    ✓\033[0m pr-scanner: 23 PRs selected (first-timers, rejections, long threads)"),
    (0.5, "agent", "\033[90m    → Analyzing PR #15715: \"Remove package-lock.json\"...\033[0m"),
    (0.7, "agent", "\033[32m    ✓\033[0m thread-analyzer: 3 rules extracted \033[90m(provenance: PR #15715)\033[0m"),
    (0.4, "agent", "\033[90m    → Analyzing PR #12669: \"Fix compute-and-discard pattern\"...\033[0m"),
    (0.6, "agent", "\033[32m    ✓\033[0m thread-analyzer: 2 rules extracted \033[90m(provenance: PR #12669)\033[0m"),
    (0.4, "agent", "\033[90m    → Analyzing PR #12846: \"Session store canonicalization\"...\033[0m"),
    (0.7, "agent", "\033[32m    ✓\033[0m thread-analyzer: 4 rules extracted \033[90m(provenance: PR #12846)\033[0m"),
    (0.3, "agent", "\033[90m    → Analyzing PR #7286: \"Matrix multi-account support\"...\033[0m"),
    (0.6, "agent", "\033[32m    ✓\033[0m thread-analyzer: 3 rules extracted \033[90m(provenance: PR #7286)\033[0m"),
    (0.2, "agent", "\033[90m    → ... analyzing 19 more PRs ...\033[0m"),
    (1.5, "agent", "\033[32m    ✓\033[0m 23 PR threads analyzed, 42 rules extracted"),
    # Phase 3: Await
    (0.3, "phase", "\033[1;36m  Phase 3: Awaiting parallel tasks...\033[0m"),
    (0.5, "agent", "\033[32m    ✓\033[0m All 6 analyzers complete"),
    # Phase 4: Synthesis
    (0.3, "phase", "\033[1;36m  Phase 4: Cross-source synthesis...\033[0m"),
    (1.0, "agent", "\033[32m    ✓\033[0m synthesizer: Merged 97 → 72 rules (dedup, confidence boosting)"),
    (0.5, "agent", "\033[32m    ✓\033[0m Generic filter: Removed 5 platitudes \033[90m(3-layer filtering)\033[0m"),
    (0.3, "done", "\033[1;32m  ✓ Extraction complete: {total} rules found\033[0m"),
]


# Real cost data from 50-PR openclaw extraction (Feb 2026)
DEMO_COST_DATA: dict = {
    "total_cost_usd": 13.10,
    "total_input_tokens": 163_970,
    "total_output_tokens": 0,  # included in input total
    "total_cache_read_tokens": 10_845_589,
    "total_cache_creation_tokens": 0,
    "elapsed_seconds": 1243.0,  # 20m43s
    "num_agents_run": 57,
    "by_model": {"opus": 9.15, "sonnet": 3.95},
    "by_agent": {
        "domain-analyzer": 1.41,
        "docs-analyzer": 1.09,
        "synthesizer": 0.76,
        "code-analyzer": 0.67,
        "structural-analyzer": 0.52,
        "pr-scanner": 0.27,
        "anti-pattern-miner": 0.19,
        "ci-failure-miner": 0.12,
        "thread-analyzer": 8.07,
    },
}


async def seed_demo_rules(repo_id: int) -> int:
    """Insert demo rules into the database. Returns count of rules inserted."""
    count = 0
    for rule in DEMO_RULES:
        await db.insert_rule(
            rule_text=rule["rule_text"],
            category=rule["category"],
            confidence=rule["confidence"],
            source_type=rule["source_type"],
            source_ref=f"demo:{rule['source_type']}",
            repo_id=repo_id,
            provenance_url=rule.get("provenance_url", ""),
            provenance_summary=rule.get("provenance_summary", ""),
            applicable_paths=rule.get("applicable_paths", ""),
        )
        count += 1
    return count


async def run_simulated_extraction(total_rules: int) -> None:
    """Print simulated extraction progress to stderr with realistic timing."""
    import sys
    for delay, _msg_type, text in EXTRACTION_TIMELINE:
        await asyncio.sleep(delay)
        if "{total}" in text:
            text = text.replace("{total}", str(total_rules))
        print(text, file=sys.stderr)
