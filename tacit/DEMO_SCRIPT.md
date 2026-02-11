# Tacit Demo Script (3 minutes)

## Setup Before Recording
1. `rm -f tacit/backend/tacit.db` (fresh DB with seeded data)
2. Start backend: `cd tacit/backend && source venv/bin/activate && python main.py`
3. Launch SwiftUI app: `cd tacit/TacitApp && swift run TacitApp`
4. Set screen to 1440x900, clean desktop, dark mode

---

## Scene 1: The Problem (0:00 - 0:20)
**Narration**: "Every engineering team builds up tacit knowledge — conventions that live in PR comments and code reviews but never make it into documentation. When new engineers join, or when AI assistants help write code, this knowledge is invisible."

**On screen**: Show the app's welcome screen, then navigate to Team Knowledge showing the pre-seeded rules.

---

## Scene 2: Connect a Repository (0:20 - 0:40)
**Narration**: "Tacit connects to your GitHub repos and extracts this hidden knowledge using AI agents."

**Actions**:
1. Click "+" in sidebar
2. Type `anthropics/claude-code`
3. Paste GitHub token
4. Click Connect

---

## Scene 3: Live Extraction (0:40 - 1:30)
**Narration**: "Watch as four AI agents analyze your PR discussions in real-time. The scanner finds knowledge-rich PRs, the analyzer extracts specific rules, and the synthesizer merges duplicates."

**Actions**:
1. Click "Extraction" in sidebar
2. Select the repo from picker
3. Click "Extract"
4. Watch pipeline bar progress through stages
5. Show event cards appearing with rule discoveries
6. Point out the stats counters rolling up

**Key moment**: When rule discovery cards appear with the blue glow

---

## Scene 4: Browse Knowledge (1:30 - 1:50)
**Narration**: "Every extracted rule has a confidence score and a decision trail showing how it was discovered and evolved."

**Actions**:
1. Click "Team Knowledge" in sidebar
2. Click a rule to show detail view
3. Scroll to decision trail timeline
4. Click category filter pills
5. Type in search box

---

## Scene 5: Local Discovery & Proposals (1:50 - 2:20)
**Narration**: "Team members can also discover patterns from their own Claude Code conversations and propose them to the team."

**Actions**:
1. Click "My Discoveries"
2. (Show pre-existing proposals instead if local scan not ready)
3. Click "Proposals" in sidebar
4. Show pending proposal from Alex
5. Type feedback, click "Approve"
6. Show the rule now appears in Team Knowledge

---

## Scene 6: Generate CLAUDE.md (2:20 - 2:50)
**Narration**: "Finally, generate a CLAUDE.md file — your team's tacit knowledge, made explicit. The AI organizes rules by category, includes confidence scores, and produces a file ready to drop into any project."

**Actions**:
1. Click "CLAUDE.md" in sidebar
2. Select repo, click "Generate"
3. Show the split preview/editor view
4. Click "Export" to save

---

## Scene 7: Close (2:50 - 3:00)
**Narration**: "Tacit: turn your team's invisible knowledge into explicit guidelines. Built with Claude Code during the Anthropic Hackathon."

**On screen**: Show the full app with populated sidebar counts
