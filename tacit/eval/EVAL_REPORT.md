# Tacit Extraction Evaluation Report

**Date**: 2026-02-10
**Method**: Side-by-side comparison of Tacit-extracted rules (from PR review comments) against ground-truth CLAUDE.md / AGENTS.md files for three open-source repositories.

---

## Repo 1: astral-sh/ruff

**Extracted**: 30 rules from 10 PRs
**Ground truth**: 16 distinct conventions in CLAUDE.md

### Coverage Score: ~25% (4/16 conventions matched)

Tacit found direct or near-direct matches for the following CLAUDE.md conventions:

| CLAUDE.md Convention | Tacit Rule | Confidence |
|---|---|---|
| Prefer let chains over nested if let | "Prefer let chains over nested if let" | 0.85 |
| mdtest files for type checker tests | "mdtest files include both success and failure cases" | 0.82 |
| Use existing helpers, avoid new code | "Use existing helper methods like Line::full_range()" | 0.75 |
| Use comments to explain invariants, not narrate code | (Partially captured via TODO comment quality rule) | 0.88 |

### Key Hits

1. **Let chains preference** (0.85) -- This is a near-verbatim match of the CLAUDE.md rule. Strong signal extraction from PR feedback.
2. **mdtest testing patterns** (0.82) -- Correctly identified that mdtest files should include both success and failure cases, which aligns with the CLAUDE.md emphasis on testing completeness.
3. **Use existing utilities** (0.75) -- The "Use existing helper methods" rule captures the spirit of the CLAUDE.md's "Avoid writing significant amounts of new code. Look for existing utilities first."
4. **Type system encoding** (0.85) -- "Don't reuse existing type variant for new semantics" partially captures the CLAUDE.md's "encode constraints in the type system" philosophy.

### Key Misses

1. **Testing infrastructure** -- No rules about `cargo nextest`, `fast-test` profile, `-p` flag for per-crate testing, `cargo insta accept` for snapshots, or `MDTEST_TEST_FILTER`. These are the most actionable parts of the CLAUDE.md.
2. **Clippy configuration** -- `cargo clippy --workspace --all-targets --all-features -- -D warnings` is entirely absent.
3. **Debug builds** -- The requirement to use debug builds (not `--release`) during development was not captured.
4. **`uvx prek run -a`** -- The critical end-of-task command was not found.
5. **PR conventions** -- The `[ty]` prefix rule and ty GitHub label requirement are missing.
6. **ALL changes must be tested** -- The emphatic "If you're not testing your changes, you're not done" was not captured as a rule.
7. **Avoid panic!/unreachable!/.unwrap()** -- Not extracted, despite being a core Rust safety convention.
8. **`#[expect()]` over `#[allow()]`** -- Missing, though this is a highly specific and important Clippy convention.
9. **Crate naming convention** -- `ruff_*` for Ruff, `ty_*` for ty was not captured.

### Precision Assessment: ~60% genuinely useful

Of the 30 extracted rules:
- **~8 rules** are genuinely useful team conventions that would help any contributor (let chains, TODO quality, helper reuse, TextSize::ZERO, mdtest patterns, .expect() preference, consistent branch styling, large refactors in intermediate PRs).
- **~10 rules** are moderately useful but overly specific to individual PRs (Airflow linter patterns, CodSpeed regressions, specific LSP server behaviors).
- **~12 rules** are noise -- they describe PR-specific implementation details rather than reusable team conventions (TypeVar constraint checking, class inheritance with intermediate_bases, Peekable iterator patterns).

### Novel Discoveries: 4 potentially useful

1. **"Large refactors broken into transitory/intermediate PRs"** (0.72) -- Good workflow practice not in CLAUDE.md.
2. **"UI/editor changes need screenshots/before-after evidence"** (0.73) -- Reasonable PR convention not explicitly stated.
3. **"Use named constants for literal numeric offsets"** (0.80) -- Solid code style rule.
4. **"TextSize::ZERO instead of TextSize::new(0)"** (0.75) -- Idiomatic Rust convention worth codifying.

### Confidence Calibration

The calibration is **inverted for this repo**. The most valuable matches (let chains at 0.85, mdtest at 0.82) have appropriate confidence. But the highest-confidence rule (0.92, "extract shared helper from duplicate logic") is a generic software engineering principle, not a ruff-specific convention. Meanwhile, genuinely ruff-specific rules like TextSize::ZERO (0.75) and existing helpers (0.75) are scored lower. The confidence scores correlate more with "how universally true is this advice" than with "how important is this to the ruff project specifically."

---

## Repo 2: modelcontextprotocol/python-sdk

**Extracted**: 29 rules from 10 PRs
**Ground truth**: 21 distinct conventions in CLAUDE.md

### Coverage Score: ~24% (5/21 conventions matched)

| CLAUDE.md Convention | Tacit Rule | Confidence |
|---|---|---|
| Do not use Test-prefixed classes, use functions | "No Test-prefixed classes, use standalone async functions" | 0.92 |
| Don't silently swallow exceptions | "Don't silently swallow exceptions" | 0.80 |
| snake_case for Python attributes | "snake_case for Python attributes" | 0.75 |
| Don't expose internal features publicly | "Don't document/expose internal features publicly" | 0.80 |
| Breaking changes documented in migration.md | "No migration entries for internal APIs" (partial) | 0.78 |

### Key Hits

1. **Test-prefixed classes prohibition** (0.92) -- Excellent match. This is one of the more unusual and project-specific conventions, and Tacit nailed it with high confidence.
2. **Exception handling** (0.80) -- "Don't silently swallow exceptions" aligns with the CLAUDE.md's strong stance against `except Exception:` and requirement for `logger.exception()`.
3. **Internal module privacy** (0.90) -- "Underscore-prefixed modules are internal/private" correctly identifies a key architectural pattern, though the CLAUDE.md doesn't state this explicitly (it's more about the test file that doesn't use Test-prefixed classes).
4. **snake_case convention** (0.75) -- Direct match with Python community standards enforced by this project.

### Key Misses

1. **uv-only package management** -- The CLAUDE.md's most emphatic rule ("ONLY use uv, NEVER pip", "FORBIDDEN: uv pip install, @latest syntax") was completely missed. This is the single most distinctive convention in the file.
2. **Type hints required for all code** -- Not extracted.
3. **Line length: 120 chars** (or 88 chars for Ruff) -- Not captured.
4. **FORBIDDEN: imports inside functions** -- A strongly worded convention that was missed.
5. **Async testing: use anyio, not asyncio** -- Not extracted, despite being project-specific and important.
6. **tests/client/test_client.py as reference file** -- Missing.
7. **E2E tests with mcp.client.Client** -- Not captured.
8. **Git commit trailer conventions** -- The `--trailer "Reported-by:<name>"` and `"Github-Issue:#<number>"` patterns are entirely absent.
9. **NEVER mention co-authored-by or tool used** -- Highly distinctive rule, not found.
10. **Ruff format + Pyright type checking** -- Toolchain configuration not extracted.
11. **logger.exception() not logger.error()** -- Specific and actionable, but missed.
12. **Catch specific exceptions, FORBIDDEN: except Exception** -- Partially covered by the "don't silently swallow exceptions" rule, but the specificity is lost.

### Precision Assessment: ~55% genuinely useful

Of the 29 extracted rules:
- **~7 rules** are genuinely useful team conventions (no Test-prefixed classes, don't swallow exceptions, snake_case, don't expose internals, self-contained docstring examples, http_client naming, @dataclass preference).
- **~10 rules** are moderately useful but somewhat generic (respect user-configured objects, batch deprecation changes, correct articles before acronyms, no get_ prefix).
- **~12 rules** are PR-specific implementation details or generic advice (sync function wrapping, callbacks not breaking contracts, functools.partial with anyio, TODO blocks as comments).

### Novel Discoveries: 5 potentially useful

1. **"Sync functions as handlers must be wrapped in async automatically"** (0.95) -- A genuine architectural pattern for the MCP SDK framework, not in CLAUDE.md.
2. **"Use snapshot testing for assertions"** (0.78) -- Useful testing convention.
3. **"Pin external tool dependencies in CI"** (0.80) -- Good DevOps practice.
4. **"Name HTTP client param http_client not httpx_client"** (0.80) -- Specific API design convention.
5. **"@dataclass over manual __init__ for many params"** (0.75) -- Solid Python style convention.

### Confidence Calibration

Calibration is **moderately well-aligned** for this repo. The highest-confidence hit (Test-prefixed classes at 0.92) is indeed one of the most distinctive rules. However, the highest overall score (0.95 for sync-to-async wrapping) goes to a rule that, while architecturally true, is not in the CLAUDE.md -- suggesting the model conflates "clearly true from the codebase" with "explicitly stated convention." The 0.72-0.75 range contains a mix of genuine conventions and noise, making it hard to use confidence as a reliable filter.

---

## Repo 3: vercel/ai

**Extracted**: 14 rules from 10 PRs (note: only 7 PRs yielded rules)
**Ground truth**: 20 distinct conventions in CLAUDE.md (AGENTS.md)

### Coverage Score: ~10% (2/20 conventions matched)

| CLAUDE.md Convention | Tacit Rule | Confidence |
|---|---|---|
| Every PR needs a changeset (patch default) | "Initial release changeset uses major version" + "Isolated changes don't need cross-package changesets" (partial) | 0.95, 0.88 |
| New providers extend openai-compatible base | "New providers extend openai-compatible base" | 0.72 |

### Key Hits

1. **Changeset workflow** (0.95, 0.88) -- Tacit captured nuances about changesets (initial release = major, isolated = no cross-package), though it missed the core rule (every PR needs a changeset, use patch by default, don't select example packages).
2. **Provider extension pattern** (0.72) -- "New providers extend @ai-sdk/openai-compatible base" partially aligns with the documented provider architecture.

### Key Misses

1. **Monorepo tooling** -- pnpm + Turborepo, `pnpm install`, `pnpm build`, `pnpm test`, `pnpm lint` -- none of the core development commands were captured.
2. **Prettier configuration** -- Single quotes, trailing commas, 2-space indent, no tabs -- entirely missing.
3. **Vitest for testing** -- Not extracted.
4. **Zod 3 and 4 support** -- The dual-Zod import pattern is a highly specific convention that was not found.
5. **Never use JSON.parse directly** -- Use parseJSON/safeParseJSON from provider-utils. Not captured.
6. **File naming: kebab-case.ts** -- Missing.
7. **AISDKError marker pattern** -- The error extension pattern is central to the architecture and was missed.
8. **Provider pattern: Specs -> Utilities -> Providers -> Core** -- Not extracted as a rule.
9. **Provider options .optional() vs .nullish()** -- Nuanced API design convention, not captured.
10. **pnpm update-references after adding deps** -- Missing.
11. **Do not add minor/major changesets** -- Actually contradicted by the extracted "initial release uses major" rule.
12. **Don't use require() for imports** -- Not found.
13. **Don't change public APIs without updating docs** -- Not captured.

### Precision Assessment: ~50% genuinely useful

Of the 14 extracted rules:
- **~4 rules** are genuinely useful (changeset workflow rules, provider extension pattern, handle fire-and-forget promises).
- **~5 rules** are moderately useful but generic (proper telemetry typing, example file naming, specific TS types over unknown, new exports scoping, preserve old examples).
- **~5 rules** are PR-specific or overly narrow (gateway provider method mirroring, no index signatures on interfaces, v6 gateway compat evaluation, OpenTelemetry in separate package).

### Novel Discoveries: 3 potentially useful

1. **"Handle fire-and-forget promise errors"** (0.72) -- Good async JavaScript practice, not in CLAUDE.md.
2. **"Telemetry prefers JSON-serializable over OTEL attributes"** (0.78) -- Useful if building telemetry features.
3. **"Preserve old examples when migrating to new patterns"** (0.75) -- Reasonable migration practice.

### Confidence Calibration

Calibration is **poorly aligned** for this repo. The highest confidence score (0.95 for "initial release uses major changeset") directly contradicts the CLAUDE.md's "Do not add minor/major changesets" rule -- the extracted rule is about a narrow edge case (brand-new packages), while the CLAUDE.md states the general policy. The lowest confidence rules (0.72) include the provider extension pattern, which is actually one of the more genuinely useful conventions. The small extraction count (14 rules from 10 PRs, with 3 PRs yielding nothing) suggests the tool struggled to find signal in this repository's PR discussions.

---

## Overall Summary

### Aggregate Metrics

| Metric | ruff | python-sdk | vercel/ai | Average |
|---|---|---|---|---|
| **Rules extracted** | 30 | 29 | 14 | 24.3 |
| **Ground truth conventions** | 16 | 21 | 20 | 19.0 |
| **Coverage (% of ground truth found)** | 25% | 24% | 10% | **~20%** |
| **Precision (% genuinely useful)** | 60% | 55% | 50% | **~55%** |
| **Novel useful discoveries** | 4 | 5 | 3 | 4.0 |
| **PRs analyzed** | 10 | 10 | 10 | 10 |

### What Tacit Does Well

1. **Style conventions from code review** -- Tacit excels at extracting code style preferences that reviewers enforce in PRs (let chains, naming conventions, Test-prefixed class prohibition). These are the kinds of rules that are hard to discover without reading PR comments.

2. **Novel rule discovery** -- Across all three repos, Tacit found ~12 useful conventions that are NOT in the CLAUDE.md files. This is arguably the tool's most compelling value proposition: surfacing implicit team knowledge that hasn't been codified yet.

3. **Architectural patterns** -- Rules about internal/private module conventions, provider extension patterns, and handler wrapping show that Tacit can pick up structural design decisions from review feedback.

### What Tacit Misses Systematically

1. **Toolchain and build commands** -- Tacit missed 100% of commands like `cargo nextest`, `uv run --frozen pytest`, `pnpm build`, `cargo clippy`, etc. These are arguably the most immediately useful parts of a CLAUDE.md. **Root cause**: These conventions are rarely debated in PR reviews -- they're established infrastructure that reviewers assume contributors know.

2. **FORBIDDEN/NEVER rules** -- Strong prohibitions ("NEVER pip", "FORBIDDEN: imports inside functions", "NEVER mention co-authored-by") were systematically missed. These rules tend to be stated upfront in contributor docs rather than discovered through PR feedback.

3. **Testing framework configuration** -- Which test runner, which async framework, which reference test file -- none of this was captured in any repo.

4. **PR/commit conventions** -- Title formats, commit trailers, changeset defaults -- these meta-workflow rules were largely absent.

5. **Formatting/linting configuration** -- Line lengths, quote styles, indentation -- basic formatting standards that appear in every CLAUDE.md were not extracted.

### Confidence Score Calibration Assessment

**Overall calibration: Weak.** The confidence scores are not well-calibrated for the purpose of filtering signal from noise.

Key issues:
- **High confidence does not predict CLAUDE.md alignment.** The highest-confidence rules across all repos (0.92-0.95) are a mix of genuine conventions and generic software engineering advice. One (vercel/ai at 0.95) actually contradicts the CLAUDE.md's general policy.
- **Confidence correlates with universality, not project-specificity.** Generic advice like "extract shared helpers from duplicate logic" (0.92) scores higher than project-specific conventions like "TextSize::ZERO instead of TextSize::new(0)" (0.75).
- **The 0.70-0.80 range is a mix of signal and noise.** There is no clear confidence threshold where "above = useful, below = noise."

**Recommendation**: Confidence scores should be reweighted to penalize generic software engineering advice and boost project-specific conventions that would not apply to other codebases.

### Recommendations

1. **Supplement with non-PR sources**: The biggest coverage gap is toolchain/build/test commands. These could be extracted from CI configuration files (`.github/workflows/`), `Makefile`/`justfile`, `package.json` scripts, and existing `CONTRIBUTING.md` files rather than PR comments.

2. **Detect FORBIDDEN/NEVER patterns**: Add explicit scanning for strong negative conventions. These are sometimes stated in PR comments as "we never do X" or "please don't use Y" but may need additional signal sources (issue discussions, contributor docs).

3. **Improve specificity scoring**: Introduce a "project-specificity" dimension alongside confidence. A rule like "use let chains" is ruff-specific; "extract shared helpers" is universal. The scoring should distinguish these.

4. **Increase PR sample size for smaller repos**: vercel/ai only extracted 14 rules from 10 PRs (with 3 yielding nothing). Increasing to 20-30 PRs or filtering for PRs with substantive review feedback might improve coverage.

5. **Cross-reference with CI/config files**: After extracting PR-based rules, cross-reference them against CI configs and package.json scripts to auto-generate the "toolchain commands" section that Tacit currently misses entirely.

6. **Add contradiction detection**: The vercel/ai case showed an extracted rule contradicting the CLAUDE.md. A post-processing step could flag rules that conflict with each other or with known conventions.

### Bottom Line

Tacit captures approximately **20% of what a well-written CLAUDE.md contains**, with roughly **55% precision** on extracted rules. Its primary strength is discovering **implicit team conventions** that are not yet documented -- averaging 4 novel useful discoveries per repo. However, it systematically misses the most practically useful information: build commands, toolchain setup, testing infrastructure, and strong prohibitions. To be a complete CLAUDE.md generator, Tacit needs to augment PR-based extraction with static analysis of CI configurations, build scripts, and existing contributor documentation.
