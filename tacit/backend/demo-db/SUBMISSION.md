# Hackathon Submission

## Team Name
Bayram

## Team Members
Bayram Annakov / @Bayka

## Project Name
Tacit

## Selected Hackathon Track
Build a Tool That Should Exist

## Project Description

Tacit extracts unwritten rules your team enforces but never documented. Point it at a GitHub repo — 16 Agent SDK agents mine PR reviews, CI failures, and CHANGES_REQUESTED discussions, then output CLAUDE.md and `.claude/rules/` files Claude Code loads automatically.

The key: anti-pattern mining from rejected PRs extracts "NEVER do X" rules linking each to the exact PR comment where the team learned the lesson. 57 agent runs, 20 MCP tools, ~$13/extraction. 4-phase pipeline with Opus for deep analysis, Sonnet for scanning.

Results: 343 rules from 50 PRs, 100% with provenance. Eval suite: 83%. Rediscovered 87% of documented guidelines from PR data alone — without reading the existing CLAUDE.md.

## Public GitHub Repository
https://github.com/BayramAnnakov/tacit

## Demo Video
(to be recorded)

## Thoughts and Feedback on Building with Opus 4.6

Opus excels at reading PR discussions and extracting the transferable lesson — a reviewer writes "this silently drops messages" and Opus generalizes to "NEVER silently drop user data." The in-process MCP server pattern (20 tools via FastMCP passed to ClaudeSDKClient, no IPC) made agent development fast. Multi-model orchestration (Opus $9.15 + Sonnet $3.95 per run) just works via ClaudeAgentOptions.

Feedback: (1) CLAUDECODE env var blocks nested SDK calls — had to pop it manually. (2) 98% prompt cache hit rate slashed costs but is invisible to developers. (3) A structured output mode at the SDK level would eliminate JSON schema retry logic.
