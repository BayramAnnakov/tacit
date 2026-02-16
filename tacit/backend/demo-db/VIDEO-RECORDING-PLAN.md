# Video Recording Plan (3 min demo)

## Before You Start

### Pre-flight Checklist
1. [ ] Terminal: `cd tacit/backend && source venv/bin/activate`
2. [ ] Verify `--summary` works: `python __main__.py openclaw/openclaw --skip-extract --summary 2>/dev/null | head -5`
3. [ ] Verify `--modular` works: `python __main__.py openclaw/openclaw --skip-extract --modular 2>/dev/null | head -5`
4. [ ] Browser Tab 1: https://github.com/openclaw/openclaw/pull/15715 (package-lock PR)
5. [ ] Browser Tab 2: https://github.com/openclaw/openclaw/pull/12669 (compute-and-discard PR)
6. [ ] Slides open (slide2-problem.html — Step 1 is now a cold open, no title slide)
7. [ ] Screen recording software ready (QuickTime Player > File > New Screen Recording, or OBS)
8. [ ] Mic check — record 5 seconds and play back

### Screen Layout
- **Start with**: Terminal fullscreen (font size 16+ for readability) — cold open is CLI
- **Then**: Slides fullscreen for problem/solution
- **Then**: Split — terminal left, browser right for demo + provenance

### Terminal Prep
- Increase font size: `Cmd +` several times until text is readable at 720p
- Clear terminal: `clear`
- Make sure prompt is clean and short

---

## Recording Steps

### STEP 1: COLD OPEN — Live CLI (0:00-0:15)

**Action:** Terminal visible, large font. Skip slides — open with the tool running LIVE.

Type and run:
```bash
python __main__.py openclaw/openclaw --skip-extract --summary
```

**Say while output appears:**
> "Watch this. One command, one repo — Tacit just extracted 120 rules that this team enforces but never documented."

**Why this works:** Judges see a working tool in the first 5 seconds, not slides. This is the "wow" opener.

**Transition:** Pause 2 seconds on the output, then cut to slide 2.

---

### STEP 2: Show Slide 2 — The Adoption Cliff (0:15-0:35)

**Action:** Fullscreen slide2-problem.html

**Say:**
> "Claude Code is incredible — if you've invested in your CLAUDE.md. But most teams run /init, get a basic file, and the results are just okay. They didn't document the unwritten rules — the gotchas from PR reviews."

> "But that knowledge IS expressed — every time a reviewer says 'no, don't do that,' that's a tacit rule spoken out loud."

**Transition:** Click to slide 3

---

### STEP 3: Show Slide 3 — How Tacit Works (0:35-0:50)

**Action:** Fullscreen slide3-solution.html

**Say:**
> "Tacit mines those signals. 16 Claude Agent SDK agents analyze PRs, CI failures, and rejected reviews in parallel. It outputs native .claude/rules/ files — zero manual effort."

> "Our own repo uses the same .claude/rules/ format that Tacit generates — we practice what we preach."

**Transition:** Switch to terminal (Cmd+Tab or click)

---

### STEP 4: Deeper CLI Demo — Modular Output (0:50-1:20)

**Action:** Terminal visible. Type and run:

```bash
python __main__.py openclaw/openclaw --skip-extract --modular
```

> Use `--modular` for the demo — it shows the .claude/rules/ structure which is more visual

**Say while output scrolls:**
> "Now the modular output — these are the actual .claude/rules/ files Claude Code loads. Look at this do-not file: 'NEVER compute a result without applying it back' — caught in PR 12669. Every rule links back to the exact PR."

**Action:** Scroll up to the `do-not.md` section. PAUSE on a rule with a provenance link for 3+ seconds — let judges READ it.

---

### STEP 5: Provenance Deep-Dive (1:20-1:50)

**Action:** Switch to browser. Open PR #15715 tab.

**Say:**
> "Let me show you where one rule came from. PR 15715: a contributor accidentally ran npm install in a pnpm repo, generating a 14,000-line package-lock.json."

**Action:** Scroll down to the review comments. **PAUSE for 3 full seconds** so judges can read the reviewer comment. This is the single most impressive moment — don't rush it.

**Say:**
> "Two reviewers flagged it. Tacit read that conversation and extracted 'never commit package-lock in a pnpm repo' — with the exact reason why. It preserves the story behind the rule."

**Transition:** Switch to slide 6

---

### STEP 6: Show Slide 6 — The Numbers (1:50-2:15)

**Action:** Fullscreen slide6-results.html

**Say:**
> "We tested against 8 major repos — Next.js, Deno, React, Claude Code. 783 rules total. 54% novel. 44 anti-patterns from rejected reviews. 98% with provenance."

**PAUSE. Then deliver the mic-drop line slowly:**
> "The ground truth test: Tacit independently rediscovered 87% of OpenClaw's documented guidelines — without ever reading the CLAUDE.md file."

**Transition:** Click to slide 7

---

### STEP 7: Show Slide 7 — Close (2:15-2:30)

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
