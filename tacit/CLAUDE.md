# Project Guidelines

## Architecture

### API Providers
- Only use Anthropic's own API providers (direct Anthropic API, AWS Bedrock, Google Vertex). Third-party proxies (OpenRouter, LiteLLM) are unsupported — Claude Code requires Anthropic-formatted API responses and OpenAI-formatted responses will not work even through a proxy. *(confidence: 0.95)*
- Configure API providers via environment variables: `ANTHROPIC_BASE_URL`, `ANTHROPIC_API_KEY`, `ANTHROPIC_BEDROCK_BASE_URL`, `ANTHROPIC_VERTEX_BASE_URL`, `ANTHROPIC_VERTEX_PROJECT_ID`, `CLAUDE_CODE_USE_BEDROCK`, `CLAUDE_CODE_USE_VERTEX`, `ANTHROPIC_MODEL`, `AWS_REGION`, `CLOUD_ML_REGION`, `DISABLE_PROMPT_CACHING`, and `API_TIMEOUT_MS`. *(confidence: 0.85)*
- Expect Anthropic-formatted API responses only. Response format parsing is tightly coupled to the Anthropic API schema. *(confidence: 0.80)*

### Shell Compatibility
- Test subprocess interactions against non-POSIX shells (fish, nushell, zsh) in addition to bash. Non-POSIX shells can cause Claude Code to hang indefinitely. Use `SHELL=/bin/bash claude` as a workaround when running from non-bash shells. *(confidence: 0.95)*
- When building CLI tools that spawn subprocesses, always test against non-POSIX shells — shell-specific syntax differences can cause commands to hang or fail silently. *(confidence: 0.85)*

### Refactoring
- Extract distinct responsibilities from large service classes into separate utility classes. Target reducing monolithic services to pure orchestration logic, keeping each extracted component independently testable. *(confidence: 0.85)*
- Replace complex conditional logic (long if/else chains) with rule-based decision maps using clear priority ordering and centralized configuration. *(confidence: 0.85)*
- Maintain backward compatibility when refactoring — the public interface must remain unchanged for consuming services, and all existing tests must pass. *(confidence: 0.80)*

### Terminal UI
- Do not require elevated (sudo/root) permissions for terminal UI features to render correctly. If a display issue is resolved by running with sudo, treat it as a file permission or terminal capability bug that needs a proper fix. *(confidence: 0.75)*

## Code Style
- Replace complex conditional logic (long if/else chains) with rule-based decision maps that have clear priority ordering. Centralize pattern weights and configurations rather than scattering them through service methods. *(confidence: 0.70)*

## Testing
- Use mock gateways (e.g., `MockKernelGateway`) in integration tests to prevent real HTTP calls. Never allow integration tests to make actual network requests to external services. *(confidence: 0.75)*
- Test CLI terminal rendering across multiple shells (zsh, fish, bash), multiple terminal emulators (Terminal.app, Ghostty, Kitty, iTerm2), and multiple Node.js versions (v18 LTS through current) to catch cross-environment compatibility issues. *(confidence: 0.70)*

## Workflow

### Issue Management
- Auto-lock closed issues after 7 days of inactivity. Direct users experiencing similar issues to file a new issue and reference the closed one. *(confidence: 0.95)*
- When triaging CLI rendering or display bugs, collect the user's Node.js version, shell (e.g., zsh, fish, bash), terminal emulator (e.g., Terminal.app, Ghostty, Kitty, iTerm2), and OS version before investigating. *(confidence: 0.90)*
- When evaluating community feature requests, gather user context and use cases before making a decision. When declining a request, provide a clear and concise response rather than leaving the discussion open-ended. *(confidence: 0.85)*
- When closing a bug that affected multiple users, ask reporters to confirm the fix in the specific version that addresses it rather than silently closing the issue. *(confidence: 0.65)*

### Shell Environment
- Ensure the `SHELL` environment variable is set to a POSIX-compatible shell (e.g., bash) when running Claude Code. Use `SHELL=/bin/bash claude` as a workaround from non-bash shells. *(confidence: 0.90)*

### Commits & Code Review
- Use conventional commit format for commit messages (e.g., `refactor(scope):`, `build(deps):`, `test(scope):`). Include the component scope in parentheses and a concise description of the change. *(confidence: 0.70)*

### Observability
- Provide a verbose or debug mode in CLI tools that surfaces model interactions, console output, and internal state. Users need observability into what's happening when a tool hangs or fails silently. *(confidence: 0.70)*

## Security
- Document security vulnerability reporting in a `SECURITY.md` file at the repository root, directing reporters to the organization's official bug bounty program (e.g., HackerOne). *(confidence: 0.85)*

## Performance
- When Claude Code operations hang or never complete (especially on large repositories), check the user's shell environment first. Shell incompatibility (particularly with fish shell) is a known root cause of indefinite hangs. *(confidence: 0.85)*
