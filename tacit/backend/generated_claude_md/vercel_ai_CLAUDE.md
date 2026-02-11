

I'll start by retrieving all knowledge rules for repo_id=3.
Now I have all the rules. Let me filter for confidence >= 0.6 and organize them into the CLAUDE.md structure.

# CLAUDE.md

## Quick Start

- Requires **Node.js v22** (v18/v20 also supported, v22 recommended) and **pnpm v10+**
- Install pnpm: `npm install -g pnpm@10`
- Install dependencies and set up Git hooks:
  ```
  pnpm install
  ```
- Build all packages from the workspace root:
  ```
  pnpm build
  ```

## Development Commands

- **Build a package:** `pnpm build` (run inside the package folder; updates `dist/`)
- **Build with watch:** `pnpm build:watch` (inside the package folder)
- **Test a package:** `pnpm test` (run inside the package folder; no rebuild needed — only dependencies must be built)
- **Type-check entire workspace:** `pnpm type-check:full` (run from workspace root after any code change)
- **Format code:** `pnpm prettier-fix` or `prettier --write .`
- **Update tsconfig references after adding deps:** `pnpm update-references`
- **Create a changeset:** `pnpm changeset`
- **Run examples (Core):** `cd examples/ai-functions && pnpm tsx src/stream-text/openai.ts` (requires API keys like `OPENAI_API_KEY`)
- **Run examples (Frameworks):** `cd examples/<name> && pnpm dev`

## Code Style

- Use **ES module imports** — never `require()`
- Use **single quotes**, **trailing commas**, **2-space indentation**, no tabs (Prettier config in root `package.json`)
- All files including `.mdx` must pass Prettier. Pay special attention to MDX files with embedded JSX components (`<Tab>`, `<Tabs>`) which Prettier reformats aggressively
- File naming: `kebab-case.ts` for source, `kebab-case.tsx` for React/UI components
- Import core functions (`generateText`, `streamText`, tools, schemas) from the `ai` package
- Import provider implementations from `@ai-sdk/<provider>` (e.g., `@ai-sdk/openai`)
- Import provider type interfaces (`LanguageModelV3`) from `@ai-sdk/provider`
- Error classes are re-exported from `ai`
- **Zod usage:** Import Zod 3 as `import * as z3 from 'zod/v3'` (compatibility only); import Zod 4 as `import * as z4 from 'zod/v4'` and use `z4.core.$ZodType` for type references
- Do not embed `.mp4` video files using markdown image syntax (`![](url.mp4)`) in MDX documentation — use a video component instead (discovered from PR review)

## Testing

- **Framework:** Vitest
- **Test file naming:** `kebab-case.test.ts` (colocated alongside source files)
- **Type test files:** `kebab-case.test-d.ts`
- **Fixtures:** `__fixtures__/` subfolders; **Snapshots:** `__snapshots__/` subfolders
- Run tests for a single package: `pnpm test` inside the package folder (no need to rebuild the package itself — only its dependencies)
- In provider snapshot tests, only include API response fields actually returned by the provider. Do not include fields with default/zero values if the provider doesn't return them in that context (discovered from PR review on Anthropic provider)
- Bug fixes must include regression tests that would fail without the fix
- New features must include comprehensive unit test coverage

## Architecture

- **Monorepo** using pnpm workspaces and Turborepo
- **Main packages:**
  - `packages/ai` — main SDK with high-level functions (`generateText`, `streamText`)
  - `packages/provider` — provider interfaces/specifications (`LanguageModelV3`)
  - `packages/provider-utils` — shared implementation utilities (`parseJSON`, `safeParseJSON`)
  - `packages/<provider>` — AI provider implementations (e.g., `@ai-sdk/openai`, `@ai-sdk/anthropic`)
  - `packages/<framework>` — UI framework integrations
- **Layered provider architecture:** Specifications → Utilities → Provider Implementations → Core
- **Provider options schemas** (user-facing): use `.optional()` unless `null` is meaningful; be as restrictive as possible
- **Provider response schemas** (API responses): use `.nullish()` instead of `.optional()`; keep minimal and allow flexibility for API changes
- Custom errors must extend `AISDKError` from `@ai-sdk/provider` and use the **marker pattern** — a private symbol property with a static `isInstance` method calling `AISDKError.hasMarker()`
- When adding new packages: create folder under `packages/<name>`, add to root `tsconfig.json` references, then run `pnpm update-references`

## Workflow

- **PR title format:** Conventional commits — `fix(package-name): description`, `feat(package-name): description`, `chore(package-name): description`
- **Every PR must include a changeset** via `pnpm changeset`. Use **only `patch`** for bug fixes and non-breaking changes. Do not select `examples/*` packages (they are not released). CI blocks merge if changeset is missing or miscategorized
- **Complete bug fixes require:** reproduction example in `examples/`, regression tests, fix implementation, manual verification, and a changeset
- **Complete features require:** implementation, usage examples in `examples/`, unit tests, documentation in `content/`, and a changeset
- If a change introduces a deprecation or breaking change, add a codemod when possible (see `contributing/codemods.md`)
- Pre-commit hooks auto-format staged files via `lint-staged`. Skip hooks for WIP commits: `ARTISANAL_MODE=1 git commit -m "message"`
- Documentation lives in `content/` directory. Small typo fixes can be done directly in GitHub (press `.` for GitHub.dev)
- Verify that documentation URLs embedded in error messages or code comments are live and accessible before merging (discovered from PR review)

## Do Not

- **NEVER** use `JSON.parse` directly in production code — use `parseJSON` or `safeParseJSON` from `@ai-sdk/provider-utils` to prevent security risks. (source: project security policy)
- **NEVER** use `require()` for imports — use ES module imports instead. (source: project style guide)
- **NEVER** change public APIs without updating documentation in the `content/` directory. (source: project policy)
- **NEVER** use `major` or `minor` changeset types unless explicitly requested by a maintainer — default to `patch` for all bug fixes and non-breaking changes. CI enforces this via `verify-changesets`. (discovered from CI failures on PRs)
- **NEVER** skip Prettier formatting — CI runs a dedicated `Prettier` check that blocks PRs. Run `pnpm prettier-fix` before pushing. (discovered from CI failures on PRs)
- **Do not** forget to run `pnpm update-references` after adding package dependencies — this updates `tsconfig.json` references and forgetting it will break cross-package type resolution.
- **Do not** skip `pnpm type-check:full` from the workspace root after making code changes — it catches type errors across the entire codebase including examples.
- **Do not** embed `.mp4` video files using markdown image syntax (`![](url.mp4)`) in MDX files — the site does not render them. Use a video component instead. (discovered from PR review)
- **Do not** include default/zero-value fields in provider snapshot tests if the provider doesn't return them in that context — only include fields actually present in the API response. (discovered from PR review)
- **Do not** select `examples/*` packages in changesets — they are not released.