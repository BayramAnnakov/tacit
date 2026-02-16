# Hackathon Submission

## Team Name
Bayram

## Team Members
Bayram Annakov / @Bayka

## Project Name
Tacit

## Selected Hackathon Track
Agentic Coding (Claude Agent SDK + MCP)

## Project Description

Tacit is a continuous team knowledge extraction system that discovers the unwritten rules your engineering team enforces but never documented. Point it at any GitHub repo — it deploys 16 Claude Agent SDK agents that mine PR reviews, CI failures, code configs, and CHANGES_REQUESTED discussions to extract tacit conventions and output CLAUDE.md and .claude/rules/ files.

Key capabilities:
- **Anti-pattern mining**: Analyzes rejected PR reviews to extract "NEVER do X" rules with full provenance — the exact PR where the team learned the lesson
- **Multi-source extraction**: 4-phase async pipeline with 5 parallel analyzers (structural, docs, CI failures, code configs, anti-patterns) + deep PR thread analysis
- **Native Claude Code output**: Generates CLAUDE.md and path-scoped .claude/rules/ files with YAML frontmatter — zero-friction adoption for any Claude Code user
- **Continuous learning**: GitHub webhooks trigger incremental extraction on each merged PR

Tested against 8 major OSS repos (Next.js, Deno, React, Prisma, LangChain, Claude Code, Claude Agent SDK Python, OpenClaw). Results: 783 rules extracted, 54% novel (not in any existing docs), 44 anti-patterns mined, 98% with provenance links. 8-eval quality suite scores 83% overall. For OpenClaw, Tacit independently rediscovered 87% of documented guidelines just from PR reviews and CI data — without ever reading the CLAUDE.md file.

Built with: Claude Agent SDK (16 agents), MCP (20 tools via in-process servers), Claude Opus 4.6 + Sonnet, FastAPI backend, SwiftUI macOS frontend.

## Public GitHub Repository
https://github.com/BayramAnnakov/tacit

## Demo Video
(to be recorded)

## Thoughts and Feedback on Building with Opus 4.6

Opus 4.6 was the backbone of Tacit's most demanding agents — anti-pattern mining, thread analysis, synthesis, and the eval suite's LLM-as-judge. A few observations:

**What worked exceptionally well:**
- **Deep PR thread analysis**: Opus 4.6 excels at reading long, multi-turn PR discussions and extracting the implicit convention being enforced. It consistently identified the "why" behind reviewer feedback, not just the surface correction.
- **Anti-pattern extraction quality**: When analyzing CHANGES_REQUESTED reviews, Opus reliably distinguished between style nitpicks and genuine anti-patterns worth codifying. The 10 anti-patterns it extracted from OpenClaw were all specific, actionable, and traced to real bugs.
- **Synthesis across sources**: The synthesizer agent (Opus) successfully deduplicated rules found across 5+ different signal sources, boosted confidence when multiple sources agreed, and pruned generic platitudes — the hardest part of the pipeline.
- **LLM-as-judge reliability**: Using Opus as an eval judge (content quality, category accuracy, ground truth recall) gave consistent, well-calibrated scores. The 83% overall eval score held up across multiple runs.

**What I'd love to see improved:**
- **Cost at scale**: Running 16 agents across 8 repos with 50 PRs each gets expensive. Being able to mix Opus for deep analysis with a cheaper model for lighter agents (without losing the SDK's session management) would help.
- **Structured output consistency**: Occasionally the agents would deviate from the requested JSON schema, especially for complex nested outputs. A built-in structured output mode would eliminate the retry logic.

Overall, Opus 4.6 via Claude Agent SDK was the right choice for this project. The combination of deep reasoning (for anti-pattern mining), long context (for PR thread analysis), and instruction-following (for structured extraction) made it possible to build a system that genuinely discovers knowledge teams didn't know they had.
