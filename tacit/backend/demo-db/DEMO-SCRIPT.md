# Tacit Demo Script (2 minutes)

## Setup Before Demo
- Terminal open in `tacit/backend/`, venv activated
- Browser tab with https://github.com/openclaw/openclaw/pull/15715 ready (minimized)
- Browser tab with https://github.com/openclaw/openclaw/pull/12846 ready (minimized)
- Slides on screen

---

## SLIDE 1: The Problem (15 sec)

**Say:**
> "Every engineering team has rules that exist only in people's heads. Don't commit package-lock in a pnpm repo. Don't use shallow spread for nested configs. These aren't in any docs — they live in PR reviews, CI failures, and code review comments. When someone new joins, they learn by making mistakes. Tacit fixes that."

---

## SLIDE 2: What Tacit Does (15 sec)

**Say:**
> "Tacit is a continuous knowledge extraction system. Point it at a GitHub repo, and it deploys 16 AI agents that mine PRs, CI failures, code configs, and review discussions. It outputs CLAUDE.md and .claude/rules/ files — the exact format Claude Code uses for project context."

---

## SLIDE 3: Live Demo — Run the CLI (30 sec)

**Switch to terminal. Run:**

```bash
python __main__.py openclaw/openclaw --skip-extract
```

**Say while it runs (instant):**
> "Here's Tacit running against OpenClaw — a real open-source project with 15,000+ PRs. It found 158 rules. 47 of them — 30% — were novel discoveries not in any existing documentation."

**Scroll to the "Do Not" section at the bottom. Point at a NEVER rule:**

> "Look at this: 'NEVER commit package-lock.json — this project uses pnpm.' Confidence 0.90. And see that provenance link? PR #15715. Let me show you where this came from."

---

## SLIDE 4: Provenance Deep-Dive (30 sec)

**Switch to browser. Open PR #15715.**

**Say:**
> "This is PR #15715. A contributor accidentally ran npm install instead of pnpm install, generating a 14,000-line package-lock.json. Two reviewers — both Greptile bot and a human — flagged it. Tacit read that discussion and extracted 'NEVER commit package-lock.json' with the exact reason why."

**Scroll to show the review comment. Then say:**

> "This is the key insight: Tacit doesn't just extract rules — it preserves WHY each rule exists, linking back to the exact conversation where the team learned it."

---

## SLIDE 5: Anti-Pattern Mining — The Crown Jewel (20 sec)

**Say:**
> "The most powerful feature is anti-pattern mining. Tacit specifically targets CHANGES_REQUESTED PR reviews — the moments where a reviewer says 'no, don't do that.' From OpenClaw, it found 10 anti-patterns across 5 different PRs. Things like: never use raw toLowerCase for session keys — use the canonical functions. Never allow register() to silently overwrite Map entries. These are battle-tested rules that came from real bugs."

---

## SLIDE 6: The Numbers (10 sec)

**Say:**
> "We tested Tacit against 7 repos including Claude Code and Langchain. 768 total rules extracted. The headline number: 30% of extracted rules are NOVEL — conventions teams enforce in PR reviews but never wrote down. And every single rule links back to the exact PR conversation where the team learned it. That's the real value — surfacing knowledge your team doesn't know it has."

---

## SLIDE 7: Architecture (10 sec — only if asked)

**Say:**
> "Under the hood: 16 Claude Agent SDK agents, 20 MCP tools, 4-phase async pipeline. Anti-pattern mining uses Opus to analyze CHANGES_REQUESTED reviews. Everything runs through Claude Agent SDK with in-process MCP servers. The eval suite has 8 evals including LLM-as-judge for content quality."

---

## KEY TALKING POINTS (if judges ask questions)

**Q: "How is this different from just reading the README?"**
> "30% of the rules Tacit finds aren't in any documentation. The anti-pattern rules — the 'NEVER do X' rules — come from PR reviews, not docs. No one writes 'never commit package-lock' in a README. They say it in a code review after someone does it wrong."

**Q: "Does this actually help developers?"**
> "The output is CLAUDE.md and .claude/rules/ — native Claude Code format. Any developer using Claude Code gets these rules automatically. It's zero-friction adoption."

**Q: "How long does extraction take?"**
> "Full extraction on a repo like OpenClaw takes about 20 minutes. But it's designed for continuous learning — a GitHub webhook triggers incremental extraction on each merged PR, taking about 30 seconds."

**Q: "What model does it use?"**
> "Opus for deep analysis — anti-pattern mining, thread analysis, synthesis. Sonnet for lighter tasks — structural analysis, PR scanning. All via Claude Agent SDK with MCP tools."

**Q: "What's the eval suite?"**
> "8 evals scoring 0-1: anti-pattern mining, provenance coverage, path scoping, modular rules generation, incremental extraction, outcome metrics, domain knowledge (5 sub-evals with LLM judge), and ground truth recall. Overall: 74%."

---

## EMERGENCY FALLBACK

If live demo fails, show the pre-generated files:
- `demo-db/generated-rules-openclaw/.claude__rules__do-not.md` (the 47-line hero file)
- `demo-db/generated-claude-md-openclaw.md` (the 255-line CLAUDE.md)
- `demo-db/comparison-openclaw.json` (before/after data)
