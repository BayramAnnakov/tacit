---
description: Testing conventions, eval process, and verification
---

## Quick Verification

- Syntax check: `python -c "import ast; ast.parse(open('file.py').read())"`
- Import check: `python -c "from module import *"`
- Use mock gateways in integration tests to prevent real HTTP calls
- Test webhook handling with sample payloads from `tacit/backend/samples/`
- Database tests should use a temporary DB path, not the production `tacit.db`

## Eval Suite v1 (Extraction Quality)

Compares generated CLAUDE.md output against ground truth files for 6 OSS repos.

```bash
cd tacit/backend && source venv/bin/activate
python eval_extract.py
```

- Ground truth files in `generated_claude_md/`
- Measures: coverage (% of expected rules found), precision (% of generated rules that match), novel discoveries
- Repos: langchain, deno, prisma, next.js, react, claude-code

## Eval Suite v2 (New V2 Capabilities)

Tests 8 capabilities added in v2. Each eval scores 0.0–1.0, averaged for overall score.

```bash
cd tacit/backend && source venv/bin/activate
python eval_v2.py                    # Full eval (extraction + all 8 evals)
python eval_v2.py --skip-extraction  # Reuse existing DB, run evals only
```

Results saved to `eval_v2_results.json` with per-repo breakdown.

### Eval 1: Anti-Pattern Mining
Tests `github_fetch_rejected_patterns` tool logic against 6 repos. Checks that CHANGES_REQUESTED PRs are found and structured correctly (pr_number, rejection_comments, inline_review_comments).
- Score = repos_with_patterns / total_repos

### Eval 2: Provenance Coverage
After extraction, checks what % of rules have `provenance_url` and `provenance_summary` populated. Validates URLs match `https://github.com/` pattern.
- Score = average of url_coverage and summary_coverage percentages

### Eval 3: Path Scoping Coverage
Checks what % of extracted rules have `applicable_paths` populated with valid glob patterns (e.g., `src/api/**/*.ts`).
- Score = rules_with_paths / total_rules

### Eval 4: Modular Rules Generation
Runs `generate_modular_rules()` per repo and validates output: files start with `.claude/`, path-scoped files have YAML frontmatter, a `do-not` rules file exists.
- Score = 0.7 * file_validity + 0.3 * donot_coverage

### Eval 5: Incremental Extraction
Simulates single-PR extraction via `incremental_extract()`. Finds a PR number from existing provenance URLs, extracts just that PR, validates auto-approve threshold (>= 0.85 confidence).
- Score = successful_extractions / total_attempts

### Eval 6: Outcome Metrics Collection
Runs `collect_outcome_metrics()` per repo. Validates 4 fields (total_prs, avg_review_rounds, ci_failure_rate, avg_time_to_merge_hours) are present and within reasonable bounds.
- Score = repos_with_valid_metrics / total_repos

### Eval 7: Domain Knowledge Extraction
5 weighted sub-evals: content quality (LLM judge, 0.30), domain coverage (LLM holistic, 0.25), confidence calibration (0.15), category accuracy (LLM judge, 0.15), DB schema self-test (0.15).
- Score = weighted composite of 5 sub-evals

### Eval 8: Ground Truth Recall
For repos with existing CLAUDE.md/AGENTS.md: filters out rules whose provenance_url mentions these files ("contaminated" rules), then uses LLM judge to measure what % of the ground truth guidelines were independently discovered from PRs, CI, configs, and code.
- Score = avg recall across repos with ground truth files
- This is the most honest measure of Tacit's discovery capability

### Passing Threshold
Overall score >= 50% to pass (exit code 0). Below 50% exits with code 1.
