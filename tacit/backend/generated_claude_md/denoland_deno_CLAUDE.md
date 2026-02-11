

I'll start by loading the `list_all_knowledge` tool and retrieving all rules for repo_id=2.
Now I have all the rules. Let me filter for confidence >= 0.6 and organize them into the CLAUDE.md structure.

# CLAUDE.md

## Quick Start

### Prerequisites

- Rust toolchain: version specified in `rust-toolchain.toml` (other versions and Nightly are not supported)
- Protocol Buffers compiler (protoc) version 3+
- Python 3 (for Web Platform Tests — ensure `python` in PATH points to Python 3)
- Clone with submodules: `git clone --recurse-submodules https://github.com/denoland/deno.git`

**macOS:**
```
xcode-select --install
brew install cmake
```

**macOS Apple Silicon (M1/M2):**
```
brew install llvm lld
# Add /opt/homebrew/opt/llvm/bin/ to $PATH
```

**Linux/WSL:**
```
wget https://apt.llvm.org/llvm.sh && chmod +x llvm.sh && ./llvm.sh 17
apt install --install-recommends -y cmake libglib2.0-dev protobuf-compiler
```
For WSL, allocate at least 16GB memory in `.wslconfig` — insufficient memory causes build failures.

**Windows:**
- Enable "Developer Mode" before cloning (symlinks require it)
- Set `git config --global core.symlinks true` before cloning (requires git 2.19.2+)
- Install VS Community 2019 with "Desktop development with C++" toolkit
- Enable "Debugging Tools for Windows" via Windows SDK settings

### Build & Verify

```bash
cargo build
./target/debug/deno run tests/testdata/run/002_hello.ts
```

## Development Commands

| Task | Command |
|------|---------|
| **Build (standard)** | `cargo build` |
| **Build (fast, binary only)** | `cargo build --bin deno` |
| **Build (release)** | `cargo build --release` |
| **Build (HMR for JS/TS iteration)** | `cargo build --features hmr` |
| **Check (no binary, fastest)** | `cargo check` |
| **Check (single crate)** | `cargo check -p deno_runtime` |
| **Format + Lint** | `./tools/format.js && ./tools/lint.js` |
| **Run all tests** | `cargo test` |
| **Run spec tests** | `cargo test specs` |
| **Run single spec test** | `cargo test spec::test_name` |
| **Run CLI integration tests** | `cargo test --bin deno` |
| **Filter tests by name** | `cargo test <nameOfTest>` |
| **Tests in specific crate** | `cargo test -p deno_core` |
| **Run dev binary** | `./target/debug/deno run script.ts` |
| **Verbose logging** | `DENO_LOG=debug ./target/debug/deno run script.ts` |
| **Module-specific logging** | `DENO_LOG=deno_core=debug ./target/debug/deno run script.ts` |
| **Debug with backtrace** | `RUST_BACKTRACE=1 ./target/debug/deno run script.ts` |
| **Debug JS with V8 inspector** | `./target/debug/deno run --inspect-brk script.ts` |
| **Debug Rust with LLDB** | `lldb ./target/debug/deno` then `run eval 'console.log("test")'` |
| **Diagnose build errors** | `cargo clean && cargo build -vv` |

Use `cargo build --features hmr` when iterating on JS/TS modules (especially `ext/node/polyfills/`). This reads JS/TS sources at runtime instead of embedding them in the binary, so you don't need to rebuild when they change. Works with all cargo commands (`cargo run --features hmr`, `cargo test --features hmr`).

Use `cargo check` instead of `cargo build` for faster feedback — it checks compilation errors without producing a binary.

## Code Style

### Copyright Headers

Every source file (`.rs`, `.ts`, `.js`, `Cargo.toml`) must include a copyright/license header as the first line. CI enforces this.

```
// Copyright 2018-2026 the Deno authors. MIT license.
```

For TOML files:
```
# Copyright 2018-2026 the Deno authors. MIT license.
```

Keep the year range current. (Discovered from CI failure in PR #32085.)

### Rust Conventions

- Use `AnyError` as the error type alias (`use deno_core::error::AnyError;`) — do not use raw `anyhow::Error` directly
- All `unsafe` blocks must include a `// SAFETY:` comment immediately above explaining why the operation is safe. Enforced by `clippy::undocumented_unsafe_blocks`. (Discovered from PR #32031.)
- Large async futures must be wrapped in `Box::pin()` to avoid excessive stack usage. CI runs Clippy with `clippy::large_futures`. (Discovered from PR #32046.)
- Direct `println!()` and `eprintln!()` are denied by Clippy (`clippy::print_stdout`, `clippy::print_stderr`). Wrap in `#[allow(clippy::print_stdout)]` if genuinely needed. (Discovered from PR #32085.)
- Batch multiple `write!` calls to stdout/stderr into a single call to reduce I/O syscalls
- Place console-related utility functions (ANSI escape filtering, terminal detection, etc.) in the `util::console` module

### JavaScript Conventions

- In Node.js polyfill code (`ext/node/polyfills/`), always use **primordials** instead of native JavaScript built-in methods. Use `FunctionPrototypeBind(fn, thisArg)` instead of `fn.bind(thisArg)`. This prevents user-land monkey-patching from breaking Deno internals. CI lint enforces this. (Discovered from PR #32092.)
- When working with TypedArray data in Node.js polyfills, always normalize non-Uint8Array TypedArrays to Uint8Array (using buffer/byteOffset/byteLength) before byte-offset arithmetic

### Formatting

- Rust formatting uses `rustfmt` (project-specific configuration) — run via `./tools/format.js`
- JavaScript/TypeScript linting uses `dlint` — run via `./tools/lint.js`

## Testing

### Test Organization

- **Spec tests** (`tests/specs/`): Main integration tests. Each has a `__test__.jsonc` defining CLI commands and expected output. Schema at `tests/specs/schema.json`
- **Unit tests**: Inline with source code in Rust files
- **CLI integration tests**: `cli/tests/`
- **TypeScript unit tests**: `tests/unit/` — run with `target/debug/deno test -A --unstable --lock=tools/deno.lock.json --config tests/config/deno.json tests/unit`
- **Web Platform Tests** (`tests/wpt/`): Standards compliance tests (requires Python 3)

### Creating Spec Tests

1. Create a directory in `tests/specs/` with a descriptive name
2. Add a `__test__.jsonc` file describing test steps
3. Add input files needed by the test
4. Add `.out` files for expected output

### Spec Test Output Matching

| Pattern | Meaning |
|---------|---------|
| `[WILDCARD]` | Matches 0+ any characters (like `.*`) |
| `[WILDLINE]` | Matches to end of line |
| `[WILDCHAR]` | Matches one character |
| `[WILDCHARS(n)]` | Matches next n characters |
| `[UNORDERED_START]`/`[UNORDERED_END]` | Order-independent line matching |
| `[# comment]` | Line comment in output files |

For flaky spec tests, use `[UNORDERED_START]`/`[UNORDERED_END]` for order-independent output and check for race conditions.

## Architecture

### Codebase Structure

| Directory | Purpose |
|-----------|---------|
| `cli/` | User-facing CLI implementation and subcommands |
| `runtime/` | Assembles the JavaScript runtime |
| `ext/` | Extensions providing native functionality to JS (fs, net, etc.) |
| `tests/specs/` | Integration tests |
| `tests/unit/` | Unit tests |

### Key Files

- `cli/main.rs` — Entry point
- `cli/args/flags.rs` — CLI flags and argument parsing
- `runtime/worker.rs` — Worker/runtime initialization
- `runtime/permissions.rs` — Permission system
- `cli/module_loader.rs` — Module loading and resolution

### Core Concepts

- **Ops**: Rust functions exposed to JavaScript (find examples in `ext/` directories, e.g., `ext/fs/lib.rs`)
- **Extensions**: Collections of ops and JS code
- **Workers**: JavaScript execution contexts (main worker, web workers)
- **Resources**: Managed objects passed between Rust and JS (files, sockets, etc.)

### Reference Patterns

- Simple CLI command: `cli/tools/fmt.rs`
- Complex CLI command: `cli/tools/test/` directory structure

## Workflow

### Adding a New CLI Subcommand

1. Define command structure in `cli/args/flags.rs`
2. Add handler in `cli/tools/<command_name>.rs` or `cli/tools/<command_name>/mod.rs`
3. Wire it up in `cli/main.rs`
4. Add spec tests in `tests/specs/<command_name>/`

### Adding/Modifying an Extension

1. Navigate to `ext/<extension_name>/`
2. Rust code provides ops exposed to JavaScript
3. JavaScript code provides higher-level APIs
4. Update `runtime/worker.rs` to register if new extension
5. Add tests in the extension's directory

### Before Submitting a PR

1. Run `./tools/format.js && ./tools/lint.js`
2. Run `cargo test`
3. Address GitHub Copilot automated code review comments — maintainers expect these to be resolved before approval

### Cross-Crate Development

Check out Deno crates next to each other (`denoland/deno/`, `denoland/deno_core/`, `denoland/deno_ast/`) and use Cargo's patch feature:
```
cargo build --config 'patch.crates-io.deno_ast.path="../deno_ast"'
```
Remove patch overrides before committing.

### VSCode Configuration

For HMR development, add to workspace settings:
```json
{
  "rust-analyzer.cargo.features": ["hmr"],
  "deno.importMap": "tools/core_import_map.json"
}
```

To use development LSP, set `"deno.path": "/path/to/your/deno/target/debug/deno"` in `.vscode/settings.json`.

## Do Not

- **NEVER** clone without `--recurse-submodules` — Deno requires submodules and the build will fail without them
- **NEVER** use a Rust version other than what's specified in `rust-toolchain.toml` — building on other versions or Nightly is not supported
- **NEVER** use `println!()` or `eprintln!()` directly — Clippy denies `print_stdout` and `print_stderr`. Wrap in `#[allow(clippy::print_stdout)]` if genuinely needed. CI enforces this. (Discovered from CI failure in PR #32085)
- **NEVER** omit `// SAFETY:` comments on `unsafe` blocks — Clippy's `clippy::undocumented_unsafe_blocks` lint will fail the build. Each unsafe operation needs its own safety comment. (Discovered from CI failure in PR #32031)
- **NEVER** use native JS built-in methods (`.bind()`, `.call()`, etc.) in Node.js polyfill code (`ext/node/polyfills/`) — use primordials instead (e.g., `FunctionPrototypeBind`). CI lint enforces this to prevent prototype pollution. (Discovered from CI failure in PR #32092)
- **NEVER** omit the copyright/license header from source files — every `.rs`, `.ts`, `.js`, and `Cargo.toml` file must start with the copyright line. CI lint rejects files missing it. (Discovered from CI failure in PR #32085)
- **NEVER** skip running `./tools/format.js && ./tools/lint.js` before committing — CI enforces `rustfmt` formatting and `dlint` checks. Code not matching the project's `rustfmt` configuration will be rejected. (Confirmed by CI failures in PRs #32082, #32088)
- **NEVER** leave large async futures unboxed — wrap in `Box::pin()` to avoid `clippy::large_futures` lint failures in CI. (Discovered from CI failure in PR #32046)
- **NEVER** skip running `cargo test` before submitting a PR — this is the full test suite including unit, integration, and Web Platform Tests
- **Do not** use raw `anyhow::Error` — use `AnyError` from `deno_core::error::AnyError` for clarity and consistency (discovered from PR #31599)
- **Do not** use `cargo build` when you only need to check for errors — use `cargo check` for faster feedback
- **Do not** mix byte-offset arithmetic with `.subarray()` on non-Uint8Array TypedArrays in Node.js polyfills — normalize to Uint8Array first (discovered from PR #32077)