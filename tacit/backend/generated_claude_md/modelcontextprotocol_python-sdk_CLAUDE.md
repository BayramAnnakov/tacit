

I'll start by loading the `list_all_knowledge` tool and retrieving all rules for repo_id=2.
Now I have all 58 rules. Let me filter for confidence >= 0.6 (all of them qualify) and organize them into the CLAUDE.md structure.

# CLAUDE.md

## Quick Start

- Python 3.10+ is required
- Install [uv](https://docs.astral.sh/uv/getting-started/installation/) — this is the only supported package manager
- Clone the repo, then install dependencies:
  ```
  uv sync --frozen --all-extras --dev
  ```
- Install pre-commit hooks:
  ```
  uv tool install pre-commit --with pre-commit-uv --force-reinstall
  ```
- Add MCP to a uv-managed project:
  ```
  uv add "mcp[cli]"
  ```
- Test and debug your MCP server with the Inspector:
  ```
  uv run mcp dev server.py
  ```

## Development Commands

- **Format:**
  ```
  uv run --frozen ruff format .
  ```
- **Lint:**
  ```
  uv run --frozen ruff check .
  ```
- **Lint (autofix):**
  ```
  uv run --frozen ruff check . --fix
  ```
- **Type-check:**
  ```
  uv run --frozen pyright
  ```
- **Test:**
  ```
  uv run --frozen pytest
  ```
- **Update README snippets** (after modifying example code):
  ```
  uv run scripts/update_readme_snippets.py
  ```
- **Fix CI errors in this order:** 1) Formatting → 2) Type errors → 3) Linting — this is the most efficient approach

## Code Style

- Type hints are required for all code — no exceptions
- Maximum line length is 120 characters (not the default 88)
- Public APIs must have docstrings
- Follow existing code patterns exactly — functions must be focused and small
- Include `py.typed` marker file in packages to indicate type hint support
- Always use `logger.exception()` instead of `logger.error()` when catching exceptions — don't include the exception in the message (use `logger.exception("Failed")` not `logger.exception(f"Failed: {e}")`)
- Catch specific exceptions where possible: file ops use `except (OSError, PermissionError):`, JSON use `except json.JSONDecodeError:`, network use `except (ConnectionError, TimeoutError):`
- Place `# pragma: no cover` on the **branch statement** (e.g., `except Exception:`) rather than on individual lines within the block — misplaced annotations will cause CI coverage checks to fail (discovered from CI fix in PR #2005)
- Code examples in documentation must be formatted with ruff and include full type annotations
- Prefer `TypedDict` over plain `dict` for typed dictionaries when the type does not use generics (discovered from PR #1985)

## Testing

- **Framework:** pytest with anyio for async tests (not asyncio)
- **Test file organization:** mirrors the source tree — `src/mcp/X/Y.py` → `tests/X/test_Y.py`
- Test files must be named with `test_` prefix (e.g., `test_client.py`, `test_auth.py`)
- Use standalone test functions — do not use `Test` prefixed classes
- Use `conftest.py` for shared test fixtures (present in `tests/` root and subdirectories)
- Store issue-specific regression tests in `tests/issues/` with `test_ISSUE_NUMBER_description.py` naming
- Follow test patterns in `tests/client/test_client.py` — it is the reference for well-designed tests
- Be minimal and focus on E2E tests using `mcp.client.Client` whenever possible
- New features require tests and bug fixes require regression tests — no exceptions
- Use `inline_snapshot` for test assertions instead of manual assert comparisons (discovered from PR #2010)

## Architecture

- **Package layout:** src-layout with main package code under `src/mcp/`
- **Module boundaries:** `client/`, `server/`, `shared/`, `types/` under `src/mcp/`
- Each example project has its own `pyproject.toml` for dependency isolation (monorepo pattern under `examples/`)
- Place automation scripts in the `scripts/` directory at repo root
- Use `__main__.py` for executable modules/packages
- In server-side code, use `ServerRequestContext` (from `mcp.server`) instead of the shared `RequestContext` from `mcp.shared.context` — the server-specific context type provides correct type information for server handlers (discovered from PR #1985)
- Documentation uses MkDocs (`mkdocs.yml` with `docs/` directory)

## Workflow

### Commits
- Use conventional commit format: `feat`, `fix`, `chore`, `refactor`, `ci`, `docs`
- Include PR number at end of first line using `(#NNNN)` format
- Use `chore(deps):` prefix for dependency update commits
- For issue-related commits: `git commit --trailer "Github-Issue:#<number>"`
- For user-reported bugs/features: `git commit --trailer "Reported-by:<name>"`

### Pull Requests
- All PRs require a corresponding issue — unless trivial (typo, docs tweak). PRs without a linked issue will be closed
- Create an issue first for: new public APIs/decorators, architectural changes, multi-module changes, or features requiring spec changes
- Before starting work, comment on the issue so maintainers can assign it to you
- Wait for maintainer feedback or a `ready for work` label before starting
- Write PR descriptions focused on high-level problem and solution — don't go into code specifics unless it adds clarity
- Keep PRs small (a few dozen lines when possible) — large PRs sit in the review queue
- Ensure CI passes before requesting review — PRs with failing CI will not be reviewed
- All PRs are squash-merged
- Target `main` for new features and breaking changes (v2 development); target `v1.x` for security/bug fixes on v1
- Submit your PR to the same branch you branched from

### Breaking Changes
- Document breaking changes in `docs/migration.md` in the same PR — include what changed, why, how to migrate, and before/after code examples

### Issues
- Do NOT work on issues labeled `needs confirmation` or `needs maintainer action` — wait for maintainer input first

## Do Not

- **NEVER** use `pip install` or `uv pip install` or `@latest` syntax — use `uv add <package>` for installation and `uv run <tool>` for running tools. The repo uses `uv.lock` exclusively for dependency management.
- **NEVER** use `except Exception:` except in top-level handlers — catch specific exceptions instead. CI enforces this.
- **NEVER** put imports inside functions — imports must be at the top of the file.
- **NEVER** use `Test` prefixed classes for test organization — use standalone test functions only. (source: CLAUDE.md and PR #2010)
- **NEVER** mention co-authored-by or the tool used to create commits/PRs in commit messages or PR descriptions.
- **NEVER** place `# pragma: no cover` on individual lines inside an except block — place it on the branch statement itself (`except Exception:  # pragma: no cover`). Misplaced annotations cause CI coverage checks to fail. (discovered from CI fix in PR #2005)
- **Do not** submit PRs without a linked issue (except trivial fixes) — they will be closed.
- **Do not** start work on issues labeled `needs confirmation` or `needs maintainer action`.
- **Do not** submit PRs with failing CI — they will not be reviewed.
- **Do not** use `asyncio` for async testing — use `anyio`.
- **Do not** use `logger.error()` when catching exceptions — use `logger.exception()` and don't include the exception object in the message string.