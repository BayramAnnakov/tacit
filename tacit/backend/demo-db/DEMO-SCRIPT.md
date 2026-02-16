# Tacit Demo Script (3 minutes)

## Setup Before Demo
- Terminal open in `tacit/backend/`, venv activated
- Slides on screen
- No browser tabs needed — all PR links are clickable in iTerm2

---

## SLIDE 1: Title (5 sec)

**Say:**
> "I love Claude Code. It's incredible — if you've invested enough in your CLAUDE.md."

---

## SLIDE 2: The Adoption Cliff (25 sec)

**Say:**
> "But I've talked to teams who tried it — they ran /init, got a basic CLAUDE.md, and the results were just okay. The /init handles what's inferrable from code — build systems, frameworks, configs. But the tacit stuff — the gotchas, the 'never do this' rules — nobody wrote those down. And can you blame them? Most teams can't even articulate their own rules until someone breaks one in a PR."

> "They got frustrated, stopped using Claude Code. That's a huge lost opportunity."

> "But here's the thing — that knowledge IS expressed. Every time a reviewer says 'no, don't do that' in a pull request, that's a tacit rule spoken out loud."

---

## SLIDE 3: How Tacit Works (15 sec)

**Say:**
> "That's why I built Tacit. Point it at any GitHub repo and 16 AI agents mine PR reviews, CI failures, code configs, and CHANGES_REQUESTED discussions."

> "The output respects Claude Code's own memory hierarchy. Anti-patterns and code style go to .claude/rules/ — modular, path-scoped, focused files. Architecture and workflow commands go to CLAUDE.md. And every rule links back to the PR where it was learned."

---

## SLIDE 4: Live Demo — Summary View (30 sec)

**Switch to terminal. Run:**

```bash
python __main__.py openclaw/openclaw --skip-extract --summary
```

**Say while it runs (instant):**
> "Here's Tacit running against OpenClaw — a real open-source project. 120 rules extracted, 60% are novel — conventions the team enforces in reviews but never documented. 55 discovered from PRs and CI, 65 from docs and config."

**Point at the anti-pattern rules:**
> "Look at these anti-patterns. 'NEVER compute a result without applying it back' — that's a real compute-and-discard bug found in a PR. And each one has a clickable link to the exact reviewer comment. Let me show you."

---

## SLIDE 5: Provenance Deep-Dive (25 sec)

### Which rules to click (pick 2 from this list):

**Best for demo — most dramatic reviewer comments:**

1. **PR #12669** — "compute and discard" bug
   - Click the `PR #12669` link → jumps to exact inline review comment
   - Comment says: "Repair result unused — `repairToolUseResultPairing()` returns repaired messages but they're never applied back"
   - Search on page: `Repair result unused`

2. **PR #12667** — reuse context window constant for output tokens
   - Click `PR #12667` → jumps to inline review
   - Comment says: "Wrong maxTokens fallback — `DEFAULT_CONTEXT_TOKENS` (200k) is a context window size, not a max output limit"
   - Search on page: `Wrong maxTokens fallback`

3. **PR #16565** — A2A policy only checks one side
   - Click `PR #16565` → jumps to review comment
   - Comment says: "Enforce requester allowlist — only verifies targetAgentId, creates authorization bypass"
   - Search on page: `Enforce requester allowlist`

4. **PR #16369** — Discord rawMember vs member (CI-fix)
   - Click `PR #16369` → jumps to PR body
   - Root cause: `member.roles` returns Carbon `Role[]` objects that stringify to `<@&123456>` mentions
   - Search on page: `Carbon Role` or `rawMember`

**Say after clicking:**
> "See? A reviewer caught this exact bug — and Tacit extracted the rule with the precise reason why. These aren't generic best practices. These are YOUR team's specific rules, with full provenance — linked to the exact comment."

---

## SLIDE 6: The Numbers (15 sec)

**Say:**
> "We tested across 8 OSS repos — Next.js, Deno, React, Claude Code's own repo, Prisma, LangChain — plus private repos from the teams I mentioned. 783 rules from OSS alone. 54% are novel — not in any documentation. 98% link back to the exact PR comment."

> "The ground truth test: for OpenClaw, Tacit independently rediscovered 87% of their guidelines — without ever reading their CLAUDE.md. Just from PRs and CI."

---

## SLIDE 7: Close (10 sec)

**Say:**
> "Claude Code's docs say: only include what Claude can't infer from code. /init handles the inferrable — build systems, frameworks. Tacit handles the tacit — the rules your team enforces in PR reviews but never wrote down. The output is native Claude Code format, right where it belongs. You shouldn't have to write it manually — your team already said it."

---

## KEY TALKING POINTS (if judges ask questions)

**Q: "Why both .claude/rules/ AND CLAUDE.md?"**
> "Different rules belong in different places. The Claude Code docs say CLAUDE.md is for things like build commands and architecture — stuff every session needs. But for topic-specific rules like 'never do X' or code style, the docs recommend .claude/rules/ — modular files that stay focused and can be path-scoped to specific directories. Tacit sorts rules into the right place automatically."

**Q: "How is this different from just reading the README?"**
> "54% of the rules Tacit finds aren't in any documentation. No one writes 'never reuse context window constants for output tokens' in a README. A reviewer catches it in code review after someone does it wrong."

**Q: "Does this actually help developers?"**
> "The output is native Claude Code format — CLAUDE.md and .claude/rules/. Any developer using Claude Code gets these rules automatically. Zero-friction adoption. And path-scoped rules in .claude/rules/ only activate when Claude works on relevant files, so they don't bloat context."

**Q: "How long does extraction take?"**
> "Full extraction on OpenClaw takes about 10-15 minutes analyzing 50 PRs. But it supports continuous learning — a GitHub webhook triggers incremental extraction on each merged PR, about 30 seconds."

**Q: "What model does it use?"**
> "Opus 4.6 for deep analysis — anti-pattern mining, thread analysis, synthesis. Sonnet for lighter tasks — structural analysis, PR scanning. All via Claude Agent SDK."

**Q: "What's the eval suite?"**
> "8 evals: anti-pattern mining, provenance coverage, path scoping, modular rules generation, incremental extraction, outcome metrics, domain knowledge with LLM-as-judge, and ground truth recall. Overall: 83%."

**Q: "Could this become a hook instead of just rules?"**
> "Great question. For the most critical 'NEVER' rules, hooks would enforce them deterministically — like literally blocking a commit. That's on the roadmap. Right now Tacit outputs advisory rules, but the provenance data is structured enough to generate hooks too."

**Q: "How do you filter out generic rules?"**
> "Three layers: (1) agent prompts explicitly say 'skip rules that pass the any-project test' — if you could paste it into any random project's CLAUDE.md, it's too generic. (2) The synthesizer aggressively removes generic patterns during dedup. (3) A post-synthesis programmatic safety net catches anything the LLM missed — known patterns like 'always write tests' or 'remove dead code' are auto-removed."

---

## EMERGENCY FALLBACK

If live demo fails, show the pre-generated files:
- `demo-db/generated-rules-openclaw/.claude__rules__do-not.md`
- `demo-db/generated-claude-md-openclaw.md`

Or run with `--summary` which only reads from the local DB (no API calls needed).
