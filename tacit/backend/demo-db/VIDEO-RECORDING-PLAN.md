# Video Recording Plan (3 min demo)

## Before You Start

### Pre-flight Checklist
1. [ ] Terminal: `cd tacit/backend && source venv/bin/activate`
2. [ ] Verify CLI works: `python __main__.py openclaw/openclaw --skip-extract 2>/dev/null | head -5`
3. [ ] Browser Tab 1: https://github.com/openclaw/openclaw/pull/15715 (package-lock PR)
4. [ ] Browser Tab 2: https://github.com/openclaw/openclaw/pull/12669 (compute-and-discard PR)
5. [ ] Slides open (slide1-title.html in browser or presentation tool)
6. [ ] Screen recording software ready (QuickTime Player > File > New Screen Recording, or OBS)
7. [ ] Mic check — record 5 seconds and play back

### Screen Layout
- **Left half**: Terminal (font size 16+ for readability)
- **Right half**: Browser (for PR links)
- Slides: fullscreen when showing, then switch to split layout for demo

### Terminal Prep
- Increase font size: `Cmd +` several times until text is readable at 720p
- Clear terminal: `clear`
- Make sure prompt is clean and short

---

## Recording Steps

### STEP 1: Show Slide 1 — Title (0:00-0:05)

**Action:** Fullscreen slide1-title.html

**Say:**
> "I love Claude Code. It's incredible — if you've invested enough in your CLAUDE.md."

**Transition:** Click to slide 2

---

### STEP 2: Show Slide 2 — The Adoption Cliff (0:05-0:25)

**Action:** Fullscreen slide2-problem.html

**Say:**
> "But I've talked to teams who tried it — they ran /init, got a basic CLAUDE.md, and the results were just okay. They didn't invest the time to document their unwritten conventions — the gotchas, the 'never do this' rules."

> "They got frustrated, stopped using Claude Code. Some fired the developer, threw out the code, never tried again. A huge lost opportunity."

> "But that knowledge IS expressed — in PR reviews. Every time a reviewer says 'no, don't do that,' that's a tacit rule spoken out loud."

**Transition:** Click to slide 3

---

### STEP 3: Show Slide 3 — How Tacit Works (0:25-0:40)

**Action:** Fullscreen slide3-solution.html

**Say:**
> "That's why I built Tacit. Point it at any GitHub repo, and 16 agents mine PR reviews, CI failures, and CHANGES_REQUESTED discussions. It outputs native .claude/rules/ files. Zero manual effort."

**Transition:** Switch to terminal (Cmd+Tab or click)

---

### STEP 4: Live CLI Demo (0:40-1:20)

**Action:** Terminal visible. Type and run:

```bash
python __main__.py openclaw/openclaw --skip-extract --modular
```

> Use `--modular` for the demo — it shows the .claude/rules/ structure which is more visual

**Say while output scrolls:**
> "Here's Tacit running against OpenClaw — a real open-source project. It extracted 126 rules. 62% are novel discoveries not in any documentation."

**Action:** Scroll up to the `do-not.md` section. Point out a rule:

**Say:**
> "Look at this do-not file: 'NEVER introduce non-trivial logic without test coverage — caught in PRs 15094 and 12669.' And here — 'NEVER use relative paths for file I/O — caught in PR 15094 by two independent reviewers.' Every rule links back to the exact PR."

**Action:** Scroll to show a few more rules, pause on provenance links

---

### STEP 5: Provenance Deep-Dive (1:20-1:50)

**Action:** Switch to browser. Open PR #15715 tab.

**Say:**
> "Let me show you where one of these rules came from. PR 15715: a contributor accidentally ran npm install in a pnpm repo, generating a 14,000-line package-lock.json."

**Action:** Scroll down to the review comments section (look for "remove package-lock.json" comment)

**Say:**
> "Two reviewers flagged it independently. Tacit read that conversation and extracted 'never commit package-lock in a pnpm repo' — with the exact reason why. It preserves the story behind the rule."

**Transition:** Switch to slide 6 or stay in browser

---

### STEP 6: Show Slide 6 — The Numbers (1:50-2:10)

**Action:** Fullscreen slide6-results.html

**Say:**
> "We tested Tacit against 8 major repos — Next.js, Deno, React, Claude Code. 783 rules total. 54% novel. 44 anti-patterns from rejected reviews. 98% with provenance."

> "The ground truth test: for OpenClaw, Tacit independently rediscovered 87% of documented guidelines — without ever reading the CLAUDE.md file."

**Transition:** Click to slide 7

---

### STEP 7: Show Slide 7 — Close (2:10-2:30)

**Action:** Fullscreen slide7-closing.html

**Say:**
> "/init handles the inferrable. Tacit handles the tacit. The output is native .claude/rules/ — feeds right back into Claude Code. You shouldn't have to write it — your team already said it in their PR reviews."

**Pause 3 seconds. End recording.**

---

## After Recording

1. Trim any dead air at start/end
2. Export as MP4 (720p or 1080p)
3. Upload to YouTube/Loom/Google Drive and paste link in submission form
4. Watch the full recording once to verify audio is clear

---

## If Something Goes Wrong During Recording

**CLI fails:** Show the pre-generated output files in `demo-db/` directory instead. `cat demo-db/generated-rules-openclaw/.claude__rules__do-not.md`

**Browser tab lost:** Skip the provenance deep-dive, describe it verbally: "In the actual PR, you can see the reviewer comments that generated this rule."

**Audio issues:** Re-record just that section and splice in editing.

**Key tip:** Don't aim for perfection. A slightly imperfect authentic recording is better than an over-produced one. The judges want to see it works, not that you're a video editor.
