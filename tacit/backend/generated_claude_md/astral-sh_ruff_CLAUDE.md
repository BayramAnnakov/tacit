

I'll start by retrieving all knowledge rules for repo_id=1.
Now I have all the knowledge rules. Let me organize them into a well-structured CLAUDE.md. All rules have confidence >= 0.6, so I'll include all of them.

# CLAUDE.md

## Quick Start

This is a **Rust-based Cargo workspace monorepo** — `Cargo.lock` and `Cargo.toml` are at the repository root, with all crates under the `crates/` directory.

**Prerequisites — install required tools:**

```bash
cargo install cargo-nextest --locked
cargo install cargo-insta
uv tool install prek
prek install
```

**Build with debug (not release) during development:**

```bash
cargo build
```

Use debug builds — release builds lack debug assertions and have slower compile times.

**Run Ruff locally:**

```bash
cargo run -p ruff -- check /path/to/file.py --no-cache
```

## Development Commands

**Run all tests (preferred runner):**
```bash
cargo nextest run
```

**Run tests with optimized profile:**
```bash
cargo nextest run --cargo-profile fast-test
```

**Run a specific crate's tests:**
```bash
cargo nextest run -p <crate_name>
```

**Run a single mdtest file:**
```bash
cargo nextest run -p ty_python_semantic --test mdtest -- mdtest::<path/to/mdtest_file.md>
```

**Isolate a specific mdtest within a file:**
```bash
MDTEST_TEST_FILTER="<filter>" cargo nextest run -p ty_python_semantic --test mdtest -- mdtest::<path/to/file.md>
```

**Test a specific lint rule (rules not enabled by default):**
```bash
cargo run -p ruff -- check crates/ruff_linter/resources/test/fixtures/pycodestyle/E402.py --no-cache --preview --select E402
```

**Review snapshot test updates:**
```bash
cargo insta review
```

**Accept all snapshot updates:**
```bash
cargo insta accept
```

**Lint (Clippy):**
```bash
cargo clippy --workspace --all-targets --all-features -- -D warnings
```

**Run all formatting, linting, and pre-commit checks:**
```bash
uvx prek run -a
```

**Regenerate documentation and generated code:**
```bash
cargo dev generate-all
```

**Update schema during testing:**
```bash
RUFF_UPDATE_SCHEMA=1 cargo test
```

**Inspect the AST:**
```bash
cargo dev print-ast /path/to/file.py
```
Or use the AST panel at https://play.ruff.rs/?secondary=AST

**Reproduce ty ecosystem changes:**
```bash
uv run scripts/setup_primer_project.py <project-name> <some-temp-dir>
```

## Code Style

**Rust conventions:**
- Use `snake_case` for Rust source files and modules (e.g., `add_noqa.rs`, `analyze_graph.rs`)
- Prefer let chains (`if let Some(x) = foo && let [first, .., last] = bar`) over nested `if let` statements to reduce indentation
- Prefer `#[expect()]` over `#[allow()]` when suppressing Clippy lints
- Prefer `.is_some()` over `let Some(_) = expr` when you don't need the inner binding
- Avoid unnecessary intermediate allocations — prefer iterator chains with `.join()` (from itertools) over collecting into `Vec<String>` then joining. Use `itertools::Itertools::exactly_one()` instead of collecting to a Vec and checking `.len() != 1`

**Comments:**
- Use comments purposefully to explain invariants and *why* something unusual was done — not to narrate code
- Avoid vague TODO comments (e.g., `// todo?`). Either remove the TODO or expand it with enough context to explain what needs to be done and why
- When a known limitation is out of scope for the current PR, add a `TODO` comment documenting the limitation and desired future behavior

**Lint rule naming:**
- Rule names should highlight the pattern being linted against, not the preferred alternative
- Rule names must make grammatical sense when read as "allow ${rule}" (like Clippy)
- Do not include instructions on how to fix in the rule name — put those in documentation and `fix_title()`

**Diagnostic messages:**
- `message()` should describe the problem concisely (e.g., "Mutable default value for class attribute")
- `fix_title()` should contain actionable fix suggestions — displayed even when the rule has no auto-fix. List multiple alternatives when valid
- When adding an autofix to a diagnostic, always include a `help:` subdiagnostic via `diagnostic.help(...)` explaining what the fix does

**Scripts:**
- Python scripts in `scripts/` intended to be run with `uv` should use the shebang `#!/usr/bin/env -S uv run python3` instead of the standard `#!/usr/bin/env python3`

**When adding new helpers**, search the codebase for existing code performing the same logic and refactor those locations to use the new helper, rather than leaving duplicate logic

## Testing

- **All changes must be tested** — if you're not testing your changes, you're not done
- **Get your tests to pass** — if you didn't run the tests, your code does not work
- Use **snapshot testing** for test assertions — snapshots are stored in `snapshots/` subdirectories with `.snap` extension. Prefer snapshot tests over manual assertions, especially for CLI behavior tests
- Test files are organized in separate `tests/` directories at the crate level, not co-located with source in `src/`
- Test fixtures are stored in `resources/test/fixtures/` within each crate. For lint rules, place one file per rule (e.g., `E402.py`) containing all examples of violations and non-violations in `crates/ruff_linter/resources/test/fixtures/[linter]`
- Use `TestSystem` methods (e.g., `TestSystem::set_env_var()`) instead of setting real environment variables. Tests that bypass `TestSystem` and access real env vars or filesystem paths risk non-deterministic failures
- When implementing autofixes, add tests for edge cases: (1) code with comments interspersed, (2) code with keyword arguments alongside positional args, (3) combinations of both. Verify no invalid syntax is introduced

## Architecture

- **Cargo workspace monorepo** — all crates under `crates/` with flat naming: `ruff_*` for Ruff-specific code, `ty_*` for ty-specific code
- Most code including **all lint rules** lives in `crates/ruff_linter` — this is the primary crate for contributors
- The `Checker` in `crates/ruff_linter/src/checkers/ast.rs` is a Python AST visitor that iterates over the AST, builds a semantic model, and calls lint rule analyzer functions
- **All filesystem access and environment variable reads** must go through the `System` abstraction (`ruff_db::system`), never directly through `std::fs` or `std::env`. This ensures test isolation
- When integrating third-party crates with their own system abstraction traits (e.g., `which::Sys`), implement a blanket impl wrapping `ruff_db::system::System` rather than letting the crate access the real filesystem directly
- When looking up Python executables on PATH, check both `python3` and `python` binary names for cross-platform compatibility (Windows defaults to `python`)
- Handle unsupported source types gracefully — log a warning and return a default/empty result (e.g., `Ok(None)`), following the same pattern used for syntax errors
- Avoid writing significant amounts of new code — this is often a sign that we're missing an existing method or mechanism. Look for existing utilities first
- In `ty_python_semantic`, prefer integrating validation checks inline at the point of type inference rather than adding separate post-hoc check methods that iterate over declarations again

## Workflow

**Commit messages:**
- Use the format `[scope] description` with square brackets around the scope (e.g., `[ty]`, `[ruff]`, `[airflow]`)

**PR titles:**
- For lint rules: `[category] Description (CODE)` — e.g., `[flake8-bugbear] Avoid false positive for usage after continue (B031)`
- For ty work: prefix with `[ty]` and tag with the `ty` GitHub label

**Pre-PR checklist:**
1. `cargo clippy --workspace --all-targets --all-features -- -D warnings`
2. `RUFF_UPDATE_SCHEMA=1 cargo test`
3. `uvx prek run -a`
4. `cargo dev generate-all` (if code changes affect generated code)

**Pre-commit hooks:**
```bash
uv tool install prek && prek install
```

**New lint rules:**
- New violation structs must include `#[violation_metadata(preview_since = "NEXT_RUFF_VERSION")]`
- When mdtest files contain Python code with comments that would be removed by the autoformatter, add `# fmt: off` to disable autoformatting

**Reviews:**
- For PRs touching specialized subsystems (LSP server, type checker, formatter), seek review from the domain expert — a general code review alone is not sufficient
- For PRs with visual/editor-facing features, include a screenshot or screen recording in the PR summary
- New diagnostics from ecosystem impact checks (mypy_primer) arising from edge cases in test suites or metaprogramming libraries are acceptable and do not block merging

**Contributing etiquette:**
- Check in before starting work on issues not labeled `good first issue`, `help wanted`, or `bug` — consensus on the solution is required first
- Custom cargo configuration is in `.cargo/config.toml`

## Do Not

- **NEVER** use `panic!`, `unreachable!`, or `.unwrap()` — encode constraints in the type system instead. (source: project CLAUDE.md)
- **NEVER** use comments to narrate code — comments explain invariants and *why* something unusual was done. (source: project CLAUDE.md)
- **NEVER** access `std::fs` or `std::env` directly — all filesystem and environment variable access must go through the `System` abstraction in `ruff_db::system`. Direct OS access breaks test isolation. (discovered from PR review on #22843)
- **NEVER** set real environment variables in tests — use `TestSystem::set_env_var()` instead. Tests that bypass `TestSystem` risk non-deterministic failures depending on the developer's local environment. (discovered from PR review on #22843)
- **NEVER** use `--release` builds during development — release builds lack debug assertions and have slower compile times. (source: project CLAUDE.md)
- **NEVER** write significant amounts of new code without first searching for existing utilities — large new code often signals a missed existing method or mechanism. (source: project CLAUDE.md)
- **NEVER** open PRs for new features without prior discussion — the team will often close these immediately as new features create long-term maintenance burden. (source: CONTRIBUTING.md)
- **Do not** open PRs for issues labeled `needs-decision` or `needs-design` — these are not good candidates for contribution. (source: CONTRIBUTING.md)
- **Do not** leave vague TODO comments like `// todo?` — either remove the TODO or expand it with full context explaining what needs to be done and why. (discovered from PR review on #23063)
- **Do not** use `#[allow()]` when `#[expect()]` is available for suppressing Clippy lints. (source: project CLAUDE.md)
- **Do not** put fix instructions in lint rule names — names highlight the pattern being linted against; fixes belong in `fix_title()` and documentation. (source: CONTRIBUTING.md)
- **Do not** collect into intermediate `Vec<String>` when you can use iterator chains with `.join()` — avoid unnecessary allocations. (discovered from PR review on #22998)