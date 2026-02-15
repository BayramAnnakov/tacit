# CLAUDE.md

## Quick Start

Prerequisites: Node.js >= 22.12.0, pnpm 10.23.0 (specified via `packageManager` field).

```bash
git clone <repo-url>
pnpm install
pnpm ui:build          # auto-installs UI deps on first run
pnpm build
pnpm openclaw onboard --install-daemon
```

Install pre-commit hooks (runs same checks as CI):
```bash
prek install
```

Prefer pnpm for builds from source. Bun is optional for running TypeScript directly (`bun <file.ts>` / `bunx <tool>`).

Key paths:
- Source: `src/` (CLI in `src/cli`, commands in `src/commands`, web provider in `src/provider-web.ts`, infra in `src/infra`, media in `src/media`)
- Tests: colocated as `*.test.ts`
- Docs: `docs/`
- Extensions/plugins: `extensions/`
- Sessions: `~/.openclaw/agents/<agentId>/sessions/`
- Credentials: `~/.openclaw/credentials/`

## Development Commands

```bash
pnpm build             # Canvas bundling, tsdown, plugin SDK types, build metadata
pnpm check             # Format check + type checking (tsgo) + linting — run before every commit
pnpm test              # Parallel test runner via scripts/test-parallel.mjs (orchestrates vitest)
pnpm check:docs        # Validate docs formatting, linting, and links
pnpm protocol:check    # Verify JSON schema and Swift bindings are in sync
```

Formatting:
```bash
oxfmt --check          # Verify formatting
oxfmt --write          # Auto-fix formatting
```

Linting:
```bash
oxlint --type-aware    # Configured via .oxlintrc.json
```

Type checking uses `tsgo` with TypeScript strict mode enabled.

Run tests on both runtimes (CI requirement):
```bash
pnpm canvas:a2ui:bundle && pnpm test                                              # Node
pnpm canvas:a2ui:bundle && bunx vitest run --config vitest.unit.config.ts          # Bun
```

Secret scanning:
```bash
detect-secrets scan --baseline .secrets.baseline
```

Committing (preferred — keeps staging scoped):
```bash
scripts/committer "<msg>" <file...>
```

## Code Style

- Use TypeScript strict mode — avoid `any` type, prefer strict typing
- Use ES2023 target and NodeNext module resolution with `.js` extensions in imports
- Use `Array.prototype.toSorted()` instead of `[...arr].sort()` — the linter enforces `toSorted()` for immutable array sorting (Node 22+)
- Use "OpenClaw" for product/app/docs headings; use "openclaw" for CLI command, package/binary, paths, and config keys
- Keep files under ~700 LOC — split/refactor when it improves clarity or testability
- Keep files concise — extract helpers instead of creating V2 copies
- Add brief code comments for tricky or non-obvious logic
- Do not leave unused variables anywhere, including test files — CI will fail (discovered from CI fix on PR #15652)
- Use shared CLI palette in `src/terminal/palette.ts` — no hardcoded colors
- Use `src/cli/progress.ts` (osc-progress + @clack/prompts spinner) for CLI progress — don't hand-roll spinners/bars
- Status output must use tables + ANSI-safe wrapping via `src/terminal/table.ts`
- Use existing patterns for CLI options and dependency injection via `createDefaultDeps`
- Control UI uses Lit with legacy decorators — use `@state() foo = "bar"` and `@property({ type: Number }) count = 0` style
- In SwiftUI, prefer Observation framework (`@Observable`, `@Bindable`) — do NOT introduce new `ObservableObject` usage; migrate existing usages when touching related code
- Docs content must be generic — no personal device names/hostnames/paths; use placeholders like `user@gateway-host`
- README (GitHub) must use absolute docs URLs (`https://docs.openclaw.ai/...`)
- Internal doc links (Mintlify): root-relative without `.md`/`.mdx` extension (e.g., `[Config](/configuration)`). Avoid em dashes and apostrophes in headings — they break Mintlify anchor links
- Changelog: user-facing changes only — no internal/meta notes

### Tool Schema Conventions

- Avoid `Type.Union` in tool input schemas (no `anyOf`/`oneOf`/`allOf`)
- Use `stringEnum`/`optionalStringEnum` (`Type.Unsafe` enum) for string lists
- Use `Type.Optional(...)` instead of `| null`
- Keep top-level tool schema as `type: "object"` with properties
- Avoid raw `format` property names — some validators treat it as reserved

## Testing

- **Framework**: Vitest with custom parallel runner (`scripts/test-parallel.mjs`)
- **Test file pattern**: `src/**/*.test.ts` or `extensions/**/*.test.ts` — always use `.test.ts` extension
- **Setup file**: `test/setup.ts` (loaded via vitest `setupFiles` config)
- **Coverage thresholds**: 70% lines, 70% functions, 55% branches, 70% statements
- **Timeout**: 120s default, 180s hook timeout on Windows
- **Max workers**: Do NOT set above 16 (already tried — causes issues)
- **Windows CI**: Tests run on Windows 2025 with `OPENCLAW_TEST_WORKERS=2` due to resource constraints
- Live integration tests (`*.live.test.ts`) and e2e tests (`*.e2e.test.ts`) are excluded from standard suite — run separately in CI
- When using `vi.mock()` at top level, use `vi.clearAllMocks()` or `vi.resetAllMocks()` in `afterEach` — NOT `vi.restoreAllMocks()`, which breaks module-level mock exports (discovered from PR #15154)
- Before using a simulator, check for connected real devices (iOS + Android) and prefer them
- Pure test additions/fixes generally do not need a changelog entry unless they alter user-facing behavior

Pre-PR checklist:
```bash
pnpm build && pnpm check && pnpm test
```

## Architecture

### Gateway & Protocol

- The Gateway is the single control plane for all messaging surfaces (WhatsApp, Telegram, Slack, Discord, Signal, iMessage, WebChat)
- Exposes a WebSocket API on port 18789 (default). Exactly one Gateway controls a single Baileys session per host
- TypeBox schemas are the single source of truth — runtime validation (AJV), JSON Schema export (`dist/protocol.schema.json`), and Swift codegen (`apps/macos/Sources/OpenClawProtocol/GatewayModels.swift`)
- WebSocket protocol has three frame types: Request (`type: "req"`), Response (`type: "res"`), Event (`type: "event"`). First frame MUST be a connect request
- Protocol versioning: clients send `minProtocol` + `maxProtocol` in connect; `PROTOCOL_VERSION` lives in `src/gateway/protocol/schema.ts`
- Bridge protocol (TCP JSONL, port 18790) is **LEGACY/DEPRECATED** — use WebSocket API
- Methods with side effects (`send`, `agent`, `poll`, `chat.send`) require an `idempotencyKey` in params

### Channels & Extensions

- Core channels: `src/telegram`, `src/discord`, `src/slack`, `src/signal`, `src/imessage`, `src/web`, `src/channels`, `src/routing`
- Extension channels: `extensions/*` (msteams, matrix, zalo, voice-call, etc.)
- When refactoring shared logic, always consider all built-in + extension channels (routing, allowlists, pairing, command gating, onboarding, docs)
- When adding a new connection provider, update every UI surface and docs (macOS app, web UI, mobile, onboarding)

### Multi-Account Pattern

- Follow the WhatsApp channel pattern: read account configs from `channels.<channel>.accounts`, use Map-based client storage keyed by accountId
- Always thread `accountId` through every resolution path — config, client lookup, auth, credentials, shared client creation, outbound sending
- Normalize account IDs early using a shared `normalizeAccountId()` function; deduplicate via `Set`
- Use case-insensitive fallback for config key lookups (direct first, then iterate with normalization)

### Agents & Sessions

- An Agent is a fully scoped brain with its own workspace, `agentDir` for auth profiles, and session store under `~/.openclaw/agents/<agentId>/sessions/`
- Session transcripts stored as JSONL. Telegram forum topics use `<SessionId>-topic-<threadId>.jsonl`
- Sessions follow `dmScope` rules: `"main"` (default, all DMs share one session), `"per-peer"`, `"per-channel-peer"` (recommended for multi-user), `"per-account-channel-peer"`
- Bindings route inbound messages via deterministic most-specific-wins matching: peer → guildId → teamId → accountId → channel-level → default agent
- Workspace bootstrap files injected on first session turn: `AGENTS.md`, `SOUL.md`, `TOOLS.md`, `BOOTSTRAP.md`, `IDENTITY.md`, `USER.md`

### Config System

- Config validation is strict — unknown keys, malformed types, or invalid values cause Gateway to refuse to start. Only diagnostic commands work when validation fails (`openclaw doctor`)
- Hot reload modes: `"hybrid"` (default, auto-restarts for critical changes), `"hot"`, `"restart"`, `"off"`. Most fields hot-apply; `gateway.*` and infrastructure fields require restart
- `$include` for config organization: single file replaces containing object; array deep-merges in order (later wins). Nested includes supported up to 10 levels
- Model refs use `"provider/model"` format (e.g., `"anthropic/claude-opus-4-6"`)

### Deployment

- macOS: menubar app only, no separate LaunchAgent — restart via OpenClaw Mac app or `scripts/restart-mac.sh`
- Remote: Gateway on Linux instance; clients connect over Tailscale Serve/Funnel or SSH tunnels
- Docker: containers run as non-root user (`node`) for security hardening
- Gateway binds to 127.0.0.1 (loopback) by default — use `--bind lan` with `OPENCLAW_GATEWAY_TOKEN` or `OPENCLAW_GATEWAY_PASSWORD` for external access
- Tailscale Funnel refuses to start unless `gateway.auth.mode: "password"` is set

### Dependencies & Plugins

- Plugin-only dependencies must live in the extension `package.json`, not root
- Plugin runtime dependencies go in `dependencies` (npm install runs with `--omit=dev`)
- Extract shared logic into helper functions (e.g., dedicated `paths.ts` utility) — don't duplicate across modules
- When using module-level mutex/lock, always release in `try/finally` to prevent deadlocks

## Product Context

OpenClaw is a personal, single-user AI assistant optimized for feeling "local, fast, and always-on." The Gateway is the control plane; the product is the assistant itself. It prioritizes developer experience over raw performance.

- **Recommended model**: Anthropic Pro/Max (100/200) + Opus 4.6 for long-context strength and prompt-injection resistance
- **Skills platform**: Skills load from bundled, managed/local (`~/.openclaw/skills`), and workspace (`<workspace>/skills`). Workspace wins on name conflict. ClawHub is the community hub
- **Agent-to-agent coordination**: `sessions_list`, `sessions_history`, `sessions_send` tools — off by default, must be explicitly enabled
- **Canvas**: Canvas host (default port 18793) serves agent-editable HTML. A2UI enables agent-driven visual workspace
- **Chat commands**: `/status`, `/new` or `/reset`, `/compact`, `/think <level>`, `/verbose on|off`, `/usage off|tokens|full`
- **DM security**: Defaults to `"pairing"` mode — unknown senders get pairing code. Public DMs require explicit opt-in (`dmPolicy: "open"`, `allowFrom: ["*"]`)
- **Session context leakage warning**: Default `dmScope: "main"` shares context across ALL senders. Use `"per-channel-peer"` for multi-user setups
- **Sandbox modes**: Default tools run on host; set `agents.defaults.sandbox.mode: "non-main"` for Docker isolation of non-main sessions
- **Release channels**: `stable` (tagged `vYYYY.M.D`, npm `latest`), `beta` (prerelease `vYYYY.M.D-beta.N`), `dev` (moving head on `main`)

## Workflow

### Commit Conventions

- Use concise, action-oriented messages (e.g., `CLI: add verbose flag to send`)
- Group related changes — avoid bundling unrelated refactors
- Use `scripts/committer "<msg>" <file...>` instead of manual `git add`/`git commit`

### PR Process

- Read `docs/help/submitting-a-pr.md` before submitting
- Run `pnpm build && pnpm check && pnpm test` locally before submission
- Use rebase-based workflow — rebase onto `upstream/main`, ensure CI is green
- For bugs/small fixes: open a PR directly. For new features/architecture: start a GitHub Discussion or Discord thread first
- AI-assisted PRs are welcome — mark as AI-assisted in title/description, note degree of testing, include prompts/session logs if possible
- Print the full URL at the end when working on a GitHub Issue or PR

### Release & Versioning

- "Bump version everywhere" means: `package.json`, Android `build.gradle.kts`, iOS/macOS `Info.plist` files, docs — **except** `appcast.xml` (only for macOS Sparkle releases)
- Read `docs/reference/RELEASING.md` and `docs/platforms/mac/release.md` before any release work
- Dependency patching: patched dependencies must use exact versions (no `^`/`~`). Patching requires explicit approval

### CI Behavior

- CI optimizes on changed files — docs-only PRs skip heavy jobs; lint and format always run
- CI requires: `pnpm check` pass, tests on Node.js and Bun, protocol schema up-to-date, Windows tests pass, secret scanning pass
- Keep `pnpm-lock.yaml` and Bun patching in sync when touching deps/patches

### Multi-Agent Git Safety

- When user says "push": may `git pull --rebase` (never discard other agents' work)
- When user says "commit": scope to your changes only
- When user says "commit all": commit everything in grouped chunks
- When "sync" given: if dirty, commit with sensible Conventional Commit message → `git pull --rebase` → push; if conflicts can't resolve, stop

### Labels & Docs Maintenance

- When adding channels/extensions/apps/docs, update `.github/labeler.yml` and create matching GitHub labels
- When adding a new `AGENTS.md`, also add a `CLAUDE.md` symlink (`ln -s AGENTS.md CLAUDE.md`)

## Do Not

- **NEVER** commit `package-lock.json` — this project uses pnpm with `pnpm-lock.yaml`. An npm lockfile creates conflicting dependency sources and CI drift. If it appears, it was generated accidentally by `npm install` (caught in PR #15715)
- **NEVER** commit local config files (`.tmp/**`, `openclaw.json` snapshots) containing live `gateway.auth.token` values or machine-specific paths — these leak secrets into repository history. Rotate any leaked tokens immediately (caught in PR #15715, flagged by multiple reviewers)
- **NEVER** commit or publish real phone numbers, videos, or live configuration values — use obviously fake placeholders in docs, tests, and examples
- **NEVER** update the Carbon dependency — it is pinned intentionally
- **NEVER** edit `node_modules` (global/Homebrew/npm/git installs too) — updates will overwrite changes
- **NEVER** edit `docs/zh-CN/**` unless explicitly asked — it is generated content
- **NEVER** switch branches or check out a different branch unless explicitly requested
- **NEVER** create/remove/modify git worktree checkouts (or edit `.worktrees/*`) unless explicitly requested
- **NEVER** create/apply/drop git stash entries unless explicitly requested (includes `git pull --rebase --autostash`) — assume other agents may be working
- **NEVER** embed `\n` in GitHub issues/comments/PR comments — use literal multiline strings or `-F - <<'EOF'` for real newlines
- **NEVER** use `workspace:*` in plugin dependencies — `npm install` breaks. Put openclaw in `devDependencies` or `peerDependencies` instead
- **NEVER** use raw `.toLowerCase()` to canonicalize session keys or identifiers — use dedicated canonicalization functions (`canonicalizeSpawnedByForAgent()`, `resolveSessionStoreKey()`, etc.). Raw lowercasing bypasses sentinel handling, prefix logic, and alias mapping, causing ghost sessions (caught in PR #12846, multiple comments across files)
- **NEVER** delete only the first legacy key match during session store migration — delete ALL case-variant legacy keys in a single pass using `findStoreKeysIgnoreCase()`. Deleting only one leaves ghost duplicates causing phantom session entries (caught in PR #12846, repeated across sessions-resolve.ts, agent.ts, server-node-events.ts)
- **NEVER** return timeout/null decisions as successful responses — callers cannot distinguish "timed out" from "explicitly allowed/denied." Return an explicit error or distinct status field like `{ status: "timeout", decision: null }` (caught in PR #3357, exec approval timeout handling)
- **NEVER** allow `register()` or Map-based pending-entry methods to silently overwrite existing entries with the same ID — this strands the original request's promise/timer. Guard with existence check or throw explicit error. Wrap in try/catch for structured error responses (caught in PR #3357, multiple review rounds)
- **NEVER** normalize identifiers without deduplicating the result — keys like `Assistant` and `assistant` that normalize to the same value cause Map collisions, credential overwrites, and runtime crashes. Always pass through a `Set` (caught in PR #7286, Matrix account IDs)
- **NEVER** use shallow object spread (`{ ...base, ...override }`) to merge config objects with nested fields — overrides will silently replace entire nested objects. Use deep merge utility or explicitly merge each nested key (caught in PR #7286, Matrix multi-account config)
- **NEVER** sanitize identifiers into filenames using simple character replacement (e.g., replacing non-alphanumeric with `_`) — distinct identifiers can collapse to the same filename, causing credential overwrites and cross-account data leaks. Use base64url or append a short hash suffix (caught in PR #7286, Matrix credentials)
- **NEVER** include API-specific payload fields unconditionally — gate optional fields on the relevant type/mode. Example: Discord's `url` field is only valid for `type: 1` (Streaming); including it for other types causes rejection (caught in PR #10855)
- **NEVER** introduce new `ObservableObject` usage in SwiftUI — prefer Observation framework (`@Observable`, `@Bindable`) and migrate existing usages when touching related code
- **Do not** use `any` type in TypeScript — prefer strict typing; strict mode is enforced project-wide
- **Do not** leave unused variables in code, including test files — CI enforces no-unused-variables and will fail the build (discovered from CI fix on PR #15652)
- **Do not** set test workers above 16 — already tried, causes resource issues
- **Do not** use `vi.restoreAllMocks()` in tests with top-level `vi.mock()` — use `vi.clearAllMocks()` or `vi.resetAllMocks()` instead; restoreAllMocks breaks module-level mock exports (discovered from PR #15154)
- **Do not** ignore unexpected changes to `src/canvas-host/a2ui/.bundle.hash` — it is auto-generated; only regenerate via `pnpm canvas:a2ui:bundle` and commit hash as a separate commit
- **Do not** add plugin-only dependencies to root `package.json` — they must live in the extension `package.json` unless core uses them
