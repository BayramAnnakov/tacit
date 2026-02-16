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

Tacit discovers the unwritten rules your engineering team enforces but never documented. Point it at any GitHub repo — 16 Claude Agent SDK agents mine PR reviews, CI failures, and CHANGES_REQUESTED discussions to extract tacit conventions, then output CLAUDE.md and path-scoped `.claude/rules/` files that Claude Code loads automatically.

What makes it different: anti-pattern mining from rejected PR reviews extracts "NEVER do X" rules with full provenance — linking each rule to the exact PR comment where the team learned the lesson. A 4-phase async pipeline runs 6 parallel analyzers (Sonnet for scanning, Opus for deep analysis), synthesizes across sources with confidence boosting, and filters generic platitudes through 3 layers. This repo itself uses the `.claude/rules/` format Tacit generates — same convention, applied to our own development.

Tested against 8 major OSS repos. Results: 783 rules extracted, 54% novel, 98% with provenance links. Eval suite scores 83%. Tacit independently rediscovered 87% of OpenClaw's documented guidelines from PR data alone — without reading the CLAUDE.md.

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
