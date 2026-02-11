

I'll start by retrieving all knowledge rules for repo_id=1.
Now I have all the rules. Let me organize them into a well-structured CLAUDE.md. All rules have confidence >= 0.6, so all qualify. Let me compose the document:

# CLAUDE.md

## Quick Start

This is a Python monorepo managed with `uv` (fast Python package installer/resolver that replaces pip/poetry).

**Prerequisites:** Install [uv](https://docs.astral.sh/uv/)

**Install all dependencies:**
```bash
uv sync --all-groups
```

**Install a specific dependency group only:**
```bash
uv sync --group test
uv sync --group lint
```

Key config files: `pyproject.toml` (main workspace config with dependency groups), `uv.lock` (locked dependencies), `Makefile` (development tasks).

Documentation sources are at https://github.com/langchain-ai/docs or `../docs/`. Prefer the local install and use file search tools. If needed, use the docs MCP server as defined in `.mcp.json`.

## Development Commands

| Task | Command |
|------|---------|
| Install all deps | `uv sync --all-groups` |
| Run unit tests | `make test` |
| Run specific test | `uv run --group test pytest tests/unit_tests/test_specific.py` |
| Lint | `make lint` |
| Format | `make format` |
| Type check | `uv run --group lint mypy .` |

## Code Style

- All Python code MUST include type hints and return types
- Use Google-style docstrings with `Args` section for all public functions. Types go in function signatures, NOT in docstrings. Focus on "why" rather than "what"
- Do not repeat default parameter values in docstrings unless there is post-processing or the value is set conditionally
- Use single backticks (`` `code` ``) for inline code references — do NOT use Sphinx-style double backticks (` ``code`` `)
- Ensure American English spelling in documentation (e.g., "behavior", not "behaviour")
- Break up complex functions (>20 lines) into smaller, focused functions where it makes sense
- No bare `except:` clauses — always use `except Exception:` or more specific types. Use a `msg` variable for error messages in exception handlers
- Use `or` for default values instead of ternary `if`: write `**(kwargs or {})` not `**(kwargs if kwargs else {})` (Ruff rule FURB110)
- Use `maxsplit` parameter with `str.split()` / `str.rsplit()` when you only need the first or last segment: write `text.split(delimiter, maxsplit=1)[0]` not `text.split(delimiter)[0]` (Ruff rule FURB184, enforced by CI across 10+ files)
- Do not use unnecessary lambda wrappers: write `key=str` not `key=lambda x: str(x)` (Ruff rule PLW0108)
- Prefer code readability over performance optimizations. Do not sacrifice readability for performance unless the improvement is proven meaningful with benchmark data

## Testing

- **Framework:** pytest — when in doubt, check existing tests for examples
- **Test file structure mirrors source code structure:**
  - Unit tests: `tests/unit_tests/` — no network calls allowed
  - Integration tests: `tests/integration_tests/` — network calls permitted
- Every new feature or bugfix MUST be covered by unit tests
- Tests must be deterministic (no flaky tests). Use fixtures/mocks for external dependencies
- Cover happy path, edge cases, and error conditions

## Architecture

**Monorepo structure:**
- `libs/core/` — langchain-core primitives (base abstractions, interfaces, protocols; users should not need to know about this layer directly)
- `libs/langchain/` — langchain-classic (legacy, no new features)
- `libs/langchain_v1/` — actively maintained langchain package
- `libs/partners/` — third-party integrations
- `libs/text-splitters/` — document chunking utilities
- `libs/standard-tests/` — shared test suite for integrations

Each package in `libs/` has its own `pyproject.toml` and `uv.lock`. Local development uses editable installs via `[tool.uv.sources]`.

Some integrations are maintained in separate repos (e.g., `langchain-ai/langchain-google`, `langchain-ai/langchain-aws`). These repos are usually cloned at the same level as the main monorepo — reference via `../langchain-google/` if needed.

**Public API discipline:**
- Before making ANY changes to public APIs: check if the function/class is exported in `__init__.py`, look for existing usage patterns in tests and examples
- Use keyword-only arguments for new parameters: `(*, new_param: str = "default")`
- Mark experimental features with docstring warnings using MkDocs Material admonitions (`!!! warning`)
- Do not add generic type parameters to classes that don't actually use them — unnecessary generics degrade developer UX (discovered from PR review)

**Third-party integrations** must be maintained as separate packages. Do not submit integration middleware directly into the main langchain library — contact a maintainer to discuss external package structure.

## Workflow

**PR title format:** Conventional Commits with mandatory scope, lowercase:
```
feat(langchain): add new chat completion feature
fix(core): resolve type hinting issue
```
Allowed types and scopes defined in `.github/workflows/pr_lint`. All titles lowercase except proper nouns.

**PR descriptions:**
- Describe the "why" of changes and why the proposed solution is the right one
- Limit prose — highlight areas requiring careful review
- Always add a disclaimer mentioning how AI agents are involved with the contribution

**PR scope:** Keep PRs tightly scoped to the issue being fixed. Do not include unrelated changes — PRs that bundle unrelated modifications will be rejected (discovered from PR reviews).

**Dependency version markers:** Add `python_version` markers in `pyproject.toml` for dependencies incompatible with newer Python versions:
```toml
"cassio>=0.1.0,<1.0.0; python_version < '3.14'"
```
Do not simply exclude incompatible dependencies — constrain them so they remain available for compatible versions.

**Function signature changes:** Warn for ANY function signature changes, regardless of whether they look breaking. When a change could be technically breaking, flag it and CC a core maintainer (CODEOWNERS member) for an explicit decision before merging.

## Do Not

- **NEVER** introduce breaking changes to public API function signatures, argument positions, or names — breaking changes are a reason for immediate PR rejection. (source: CLAUDE.md, confirmed in multiple PR reviews)
- **NEVER** use bare `except:` clauses — always use `except Exception:` or more specific types. **NEVER** use `except BaseException:` as it swallows `SystemExit` and `KeyboardInterrupt`.
- **NEVER** use `eval()`, `exec()`, or `pickle` on user-controlled input.
- **NEVER** use unnecessary lambda wrappers — write `key=str` not `key=lambda x: str(x)`. CI will reject this (Ruff PLW0108).
- **NEVER** use ternary `if` for default values — write `**(kwargs or {})` not `**(kwargs if kwargs else {})`. CI will reject this (Ruff FURB110).
- **NEVER** omit `maxsplit` when splitting to get only the first/last segment — write `text.split(d, maxsplit=1)[0]` not `text.split(d)[0]`. CI will reject this (Ruff FURB184, discovered across 10+ files in a single CI fix).
- **NEVER** use Sphinx-style double backticks (` ``code`` `) — use single backticks (`` `code` ``).
- **NEVER** repeat default parameter values in docstrings unless post-processing or conditional assignment is involved.
- **Do not** submit LLM-generated PRs that haven't been carefully reviewed — low-quality AI-generated contributions increase maintenance burden and will be rejected. (discovered from PR reviews)
- **Do not** submit third-party integration middleware directly into the main langchain library — it must be a separate package. (discovered from PR review of #35092)
- **Do not** include unrelated changes in PRs — keep scope tight to the issue being fixed. (discovered from PR review of #35102)
- **Do not** add generic type parameters to classes that don't use them — use `Any` instead. Unnecessary generics degrade developer UX. (discovered from PR review of #34629)
- **Do not** submit performance optimization PRs without benchmark data proving the improvement is meaningful.