

I'll start by retrieving all knowledge rules for repo_id=3.
Now I have all the rules. Let me organize them into a well-structured CLAUDE.md. I'll filter for confidence >= 0.6 (all rules qualify) and organize them by section.

# CLAUDE.md

## Quick Start

**Prerequisites:**
- Node.js `^20.19 || ^22.12 || >=24.0` (use `nvm`, latest LTS recommended)
- pnpm `>=10.15 <11`
- Docker (required for database management in tests)
- ts-node (for running TypeScript scripts)
- On Windows, use WSL or VS Code Dev Containers — the repo assumes a Unix-like environment

**Setup:**
```
git clone https://github.com/prisma/prisma.git
cd prisma
pnpm i
pnpm -r run dev
```

Verify local setup is correct — `pnpm prisma -v` must return version `0.0.0`.

## Development Commands

- **Build all packages:** `pnpm build` (Turborepo manages cache and ordering)
- **Fast dev build (no tsc):** `pnpm -r run dev`
- **Continuous watch build:** `pnpm run watch`
- **Run command for a specific package:** `pnpm --filter @prisma/<pkg> <script>`
- **Run benchmarks:** `pnpm bench` or `pnpm bench <pattern>` (outputs to `output.txt`, tracked by CodSpeed on CI)
- **Lint check:** ensure `Lint` GitHub Actions workflow passes before merge
- **Debug reproduction scripts:** `pnpm debug` from the reproduction folder, then open `chrome://inspect` in a Chromium browser

When modifying monorepo dependencies like `@prisma/internals`, run `pnpm -r run dev` or `pnpm run watch` at root to make changes available to the bundled CLI.

## Code Style

- Use `@prisma/ts-builders` for generating TypeScript type declarations — it provides a fluent API for interfaces, types, and properties with doc comments
- Commit message format: `<type>(<package>): <subject>` with optional body — e.g., `feat(client): new awesome feature\n\nCloses #111`
- Commit types: `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `chore` — use these exact types
- Add new workspace dependencies using `"workspace:*"` version protocol
- When adding generator output in `schema.prisma` for local dev, manually add `output = "../node_modules/.prisma/client"` to the generator block

## Testing

**Unit/Integration tests per package:**
```
pnpm --filter @prisma/<pkg> test
```

**Client integration tests:**
```
cd packages/client && pnpm run test integration
```
These are folder-based mini projects in `src/__tests__/integration`. Copy the minimal test from `packages/client/src/__tests__/integration/happy/minimal` and adjust — use `getTestClient` for in-memory clients or `generateTestClient` for filesystem-generated clients.

**Client functional tests:**
```
pnpm --filter @prisma/client test:functional:code --adapter js_pg <pattern>
```
Supported adapters: `js_pg`, `js_neon`, `js_libsql`, `js_planetscale`, `js_d1`, `js_better_sqlite3`, `js_mssql`, `js_mariadb`, `js_pg_cockroachdb`.

Functional tests require three files: `_matrix.ts` (test configurations), `test.ts` or `tests.ts` (test code), and `prisma/_schema.ts` (schema template) — all three are mandatory.

**Client e2e tests:**
```
pnpm build            # MUST build first
pnpm --filter @prisma/client test:e2e --verbose --runInBand
```

**General integration tests:**
```
cd packages/integration-tests && pnpm run test
```

**Migrate development testing:** Test changes in `packages/migrate/fixtures/blog` using `../../src/bin.ts migrate dev`.

**Test utilities:**
- Use `idForProvider(provider)` from `_utils/idForProvider` for portable ID field definitions in functional tests
- Use `ctx.setConfigFile('<name>')` to override config for next CLI invocation in tests — resets automatically after each test
- For error assertions, use `result.name === 'PrismaClientKnownRequestError'` and `result.code` — do not use `instanceof` checks

**Test writing guidelines:**
- Focus on regression-prevention tests that verify correct behavior, not tests that demonstrate the old broken behavior (source: PR review feedback)
- When modifying database adapter packages, include functional/integration tests in `packages/client/tests/functional` that exercise the adapter end-to-end, not just unit tests in the adapter package
- After modifying DMMF types, regenerate snapshot tests — CI runs snapshot comparison and will fail on stale snapshots

## Architecture

- `client-generator-js` and `client-generator-ts` maintain parallel implementations — changes to one must be mirrored in the other (source: discovered from CI failure in PR #29100)
- When updating Prisma engine versions, any new fields added to DMMF schema types must be added to ALL test fixtures that construct mock DMMF objects
- When the MSSQL adapter's runtime behavior conflicts with its documentation, fix the docs to match the adapter — the adapter's current behavior is the source of truth
- `packages/cli/build/index.js` bundle size must stay below ~6MB (enforced by `bundle-size` GitHub Action)
- Published CLI unpacked size must stay below ~16MB on npm
- When creating new packages, add resolution paths to `tsconfig.build.bundle.json` under `compilerOptions.paths` for editor go-to-definition support
- When creating new packages with tests, register them in `.github/workflows/test-template.yml` in the appropriate job

## Workflow

- PR authors must sign the Prisma CLA at https://cla-assistant.io/prisma/prisma
- Before merge, ensure: PR description links tracking issue, tests cover changes, `Lint` & `CLI commands` & `All pkgs (win+mac)` CI workflows pass, and a documentation PR is open
- Add `/integration` in the PR description to get a version released to npm with the `integration` tag for pre-merge testing
- Benchmark CI failures can be ignored if PR changes are unrelated to performance
- Avoid unnecessary merge commits to open PRs — each push invalidates approved CI runs and forces maintainers to re-approve
- When updating GitHub Actions versions in `.github/workflows/`, also update the same actions in custom composite actions under `.github/actions/`
- When bumping GitHub Actions to new major versions, check changelogs for breaking changes and required new parameters

**Creating reproduction folders:** Copy templates from sandbox: `cp -r basic-sqlite my-repro`, then `pnpm install`, `pnpm dbpush`, `pnpm generate && pnpm start`.

## Do Not

- **NEVER** edit `CLAUDE.md` or `GEMINI.md` directly — these are symlinks to `AGENTS.md`. Always edit `AGENTS.md`. (source: AGENTS.md)
- **NEVER** use `instanceof` checks for Prisma error assertions in functional tests — use `result.name === 'PrismaClientKnownRequestError'` and `result.code` instead. (source: AGENTS.md)
- **NEVER** hardcode ID types in functional tests — use `idForProvider(provider)` from `_utils/idForProvider` for portable ID field definitions. (source: AGENTS.md)
- **NEVER** skip the `pnpm build` step before running client e2e tests — the suite requires a fresh build at repo root. (source: AGENTS.md)
- **NEVER** update only `client-generator-js` without mirroring changes to `client-generator-ts` (or vice versa) — CI will fail. These packages maintain parallel implementations. (discovered from CI failure in PR #29100)
- **NEVER** add engine DMMF type fields without updating ALL test fixtures that construct mock DMMF objects — CI snapshot comparison will fail. (discovered from CI fix in PR #29100)
- **NEVER** push unnecessary merge commits to open PRs awaiting review — each push invalidates CI approvals and delays merging. (discovered from PR review in #29089)
- **NEVER** add "+1", "same here", or "any update?" comments to issues — use GitHub reactions (👍) instead. Only comment with new, actionable information. (source: CONTRIBUTING.md)
- **Do not** block PRs on benchmark CI failures when changes are unrelated to performance. (discovered from PR #29089)
- **Do not** write tests that only demonstrate the old broken behavior — focus on regression-prevention tests that verify correct behavior. (discovered from PR review in #29119)