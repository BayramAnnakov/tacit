# CLAUDE.md Comparison Report

## anthropics/claude-code
**Has CLAUDE.md?** No (only `.claude/` directory with plugin config)
**Tacit result:** Generated 40+ rules from PR discussions — this is **net-new value** since the repo has no existing CLAUDE.md. Tacit discovered conventions that are only implied in PR reviews.

---

## anthropics/anthropic-cookbook
**Has CLAUDE.md?** Yes — well-structured with setup, commands, code style, git workflow, key rules, slash commands, and project structure.

### What the actual CLAUDE.md covers:
| Section | Content |
|---------|---------|
| Quick Start | `uv sync`, pre-commit hooks, .env setup |
| Dev Commands | `make format/lint/check/fix/test` |
| Code Style | 100-char lines, double quotes, Ruff formatter, relaxed notebook rules |
| Git Workflow | Branch naming `<username>/<feature>`, conventional commits |
| Key Rules | No .env commits, use `uv add`, current models, notebook outputs, quality checks |
| Slash Commands | `/notebook-review`, `/model-check`, `/link-review` |
| Project Structure | Directory layout guide |
| Adding Cookbooks | registry.yaml workflow |

### What Tacit extracted from cookbook PRs (14 rules, pre-tuning):
| Rule | Confidence | In actual CLAUDE.md? |
|------|-----------|---------------------|
| Use `os.environ.get("ANTHROPIC_API_KEY")` | 0.95 | YES — Key Rule #1 |
| Keep notebook outputs for demonstration | 0.90 | YES — Key Rule #4 |
| Use conventional commits | 0.90 | YES — Git Workflow |
| One concept per notebook | 0.90 | YES — Key Rule #4 |
| Run quality checks before committing | 0.85 | YES — Key Rule #5 |
| Use `uv add` for dependencies | 0.85 | YES — Key Rule #2 |
| Use current Claude model versions | 0.85 | YES — Key Rule #3 |
| Always test notebooks top-to-bottom | 0.80 | YES — Key Rule #4 |
| Sign commits with GPG | 0.90 | NO — not in CLAUDE.md |
| Use pedagogical structure in notebooks | 0.85 | NO — not in CLAUDE.md |
| Avoid supplementary .md files alongside notebooks | 0.80 | NO — not in CLAUDE.md |
| Place pip installs in first code cell | 0.75 | NO — not in CLAUDE.md |
| Use %%capture magic for install output | 0.70 | NO — not in CLAUDE.md |
| Escape HTML in notebook markdown | 0.65 | NO — not in CLAUDE.md |

### Gap Analysis

**Tacit found (8/14 overlap = 57% coverage):**
- Most core conventions were correctly extracted
- Source attribution was approximately correct for 70% of rules

**Tacit missed (rules in actual CLAUDE.md not found by Tacit):**
1. Line length 100 chars + double quotes
2. Ruff as formatter
3. Branch naming convention `<username>/<feature>`
4. Never edit pyproject.toml directly
5. Slash command definitions
6. Relaxed notebook linting rules (E402, F811, N803, N806)
7. Project directory structure

**Why Tacit missed these:** Most of these are in config files (.ruff.toml, Makefile) or documented in README, not discussed in PR comments. Tacit only looks at PR discussions — it would need a separate config file analyzer pass to catch these.

**Tacit found extras (not in CLAUDE.md):**
- GPG signing, pedagogical structure, %%capture magic — these ARE discussed in PRs but the maintainers chose not to include them in CLAUDE.md (possibly too low-level or not universal enough).

---

## Impact of Prompt Tuning (this session)

### Thread Analyzer changes:
- **Before:** Most rules defaulted to 0.90-0.95 confidence → overcalibrated
- **After:** Granular 5-tier calibration (0.50-0.59, 0.60-0.69, 0.70-0.79, 0.80-0.89, 0.90-0.95) with explicit criteria
- **Before:** Rules could be inferred from PR titles/code diffs alone
- **After:** Grounding requirement — rules must trace to actual reviewer comment text

### Synthesizer changes:
- **Before:** Used fragile "search for 'a', 'e', 'the'" hack to get all rules → missed some
- **After:** Uses `list_all_knowledge` tool for complete retrieval
- **Before:** No deletion capability — duplicates accumulated
- **After:** Has `delete_knowledge` tool to remove merged originals
- **Before:** Vague "identify duplicates" instruction
- **After:** Structured 5-step process with semantic similarity criteria and examples

### Expected improvements on re-run:
1. Confidence scores should average 0.75-0.80 instead of 0.85-0.90
2. Near-duplicate rules (same concept, different words) should be merged
3. Rules without grounding in actual PR comments should be excluded
4. Low-quality/vague rules should be filtered during synthesis
