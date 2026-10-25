# Tag Out: build brief (Track 2, Agent-to-Agent Coordination)

DevHacks S3 x Cubbie, ASU Tempe. Submissions due **Sun Oct 25, 12:00 PM Arizona** (UTC-7, no DST).
Submit on the Cubbie site with the kit CLI: `--track agents` (Track 1 "Callback" by team "Aju" is already in, which
unlocks Track 2). Judged privately by Cubbie's engineers, "mainly technical and use-case".

This is the single source of truth for the build. Research and earlier versions are in `research/`.

---

## 1. The product in one paragraph

Every student worker gets a **mascot agent** that privately knows their whole life calendar (classes, exams and due
dates from Canvas, doctor appointments, interviews, vacations, ASU holidays and breaks), their shifts at every campus
job, and the work rules that apply to them. **Every Sunday** it checks next week and texts only when a shift collides
with something. Then the mascots **negotiate with coworkers' mascots** to trade shifts in a ring ("Ben takes your
Tuesday, you take Dev's Friday, Dev takes Ben's Thursday") so everyone's week works, nobody loses scheduled pay, and
nobody breaks a rule their employers can't see. Every student and the manager confirm with one tap. Nobody ever learns
why anyone said no.

## 2. Pitch (30 s, open with the stat)

> "About 10,000 ASU students work on campus, half with high financial need, most 11 to 20 hours a week. When school
> and a shift collide, ASU's advice is 'be proactive about finding shift coverage'. So students drop the shift and lose
> the pay, or skip the studying. Tag Out gives every student worker a mascot that reads their calendar and their
> shifts. Every Sunday it warns you about next week's collisions, then negotiates with your coworkers' mascots to trade
> shifts so everyone's week works and nobody loses pay. It knows your private limits (a 25-hour average for everyone,
> 20 hours a week across all jobs if you're on an F-1) and never tells anyone why you said no. In our simulation of a
> 40-person roster, plain covers fixed X% of conflicts; trades fixed Y% more."

X/Y come from the simulator (section 7). Never use the spring-2025 "1,200 students lost status" figure: those were
record-check terminations, not work-hour cases.

## 3. Facts with sources (put the exact quotes in `docs/RULES.md`)

**Rules the Rulebook enforces**

| Rule | Who | How counted | Engine behaviour | Source |
|---|---|---|---|---|
| 25 h average across all ASU jobs + stipends (FWS hours count) | every ASU student worker (F-1 too) | measurement period: first 12 months of employment, then Oct-Sep (SSM says Oct-Oct; note the discrepancy), checked biweekly; one week can go up to 40 | projected average after the trade; **"unverified" when history is missing, never "safe"**. Exceeding means termination from all ASU jobs and no student rehire for 26 weeks | https://public.powerdms.com/ASU/documents/1560576 ; https://cfo.asu.edu/aca-faqs-undergraduate-graduate-student-workers |
| 20 h/week in session | F-1, J-1 | Mon-Sun, each week alone, no averaging, summed across ALL on-campus employers (ASU, Aramark, Follett, stipends) | hard block. ASU: going over means "loss of your F-1/J-1 immigration status" | https://studentemployment.asu.edu/students/international-students/hourly-limits-and-work-rules ; 8 CFR 214.2(f)(9)(i) |
| 40 h/week in ASU-listed break weeks | F-1, J-1 | per ASU's dated chart (winter break Dec 14 2026 - Jan 10 2027); 20 in a first or final summer | raises the limit only in listed weeks | same page; https://issc.asu.edu/news/work-hour-limits-f-1-students-during-semester-break |
| FWS earnings <= award | Federal Work-Study students (international students are not eligible) | cumulative dollars | block when a trade would exceed the remaining award | https://studentemployment.asu.edu/students/preparing-student-employment/federal-work-study |
| 40 h/week | everyone | workweek | overtime warning | SSM 305-05 |
| No work during your own class time | everyone | per shift | block | SSM 305-05 |

Footer on every screen and in the README: "Not legal or immigration advice. Your DSO and ASU Student Employment decide.
Rules are cited; limits are configurable."

**Stats**
- About 10,000 students work at ASU each year (other ASU pages say 8,000 or 12,000+); 7 in 10 undergrads work at ASU at some point; most work 11-20 h/week; nearly a quarter also hold an off-campus job; 50% have high financial need. https://workplus.asu.edu/impact
- 14,600 international students at ASU in fall 2025. https://news.asu.edu/20250813-sun-devil-community-asu-welcomes-14600-international-students-fall
- ASU tells students to "be proactive about finding shift coverage". https://studentemployment.asu.edu/students/starting-your-role/developing-schedule
- Sun Devil Fitness: 200+ student staff, 40-50 roles, many working for several managers; a schedule took about 6 hours to build (vendor case study). https://www.subitup.com/case-studies/arizona-state-university/
- Why now (international students): the July 2026 DHS rule ending duration of status (blocked nationwide Sep 14 2026, appealed Sep 30) and the August 2026 narrowing of CPT make on-campus hours more important and more scrutinised. Sources in `research/rules-and-why-now.md`.
- Survey (to be filled): answers from ASU student workers collected tonight; see `survey.md`.

## 4. The agent cast

| Agent | Holds (private) | Does |
|---|---|---|
| **Mascot agent** x6 (one per demo student; separate FastAPI process, own SQLite file) | the student's life calendar, shifts at every job, which rules apply, pay goal, soft preferences (wants more hours, never Fridays, protects exam eves) | runs the Sunday check; answers trade rounds with only a pick (the shift it would take) or a pass; asks its student when unsure and makes one counter-offer; never sends a reason, hours or rule names |
| **Steward** (manager agent, one per employer; Library in the MVP) | roster, role certifications, approval policy | posts open shifts; one-tap Approve card for the real manager; weekly **crunch forecast** (counts only, k >= 3) |
| **Rulebook** (library called privately by each mascot) | policy text + that one student's numbers | returns eligible / blocked / unverified with the exact quoted rule line; code checks the quote exists in `docs/RULES.md` |
| **Broker** | only picks and shift IDs | runs Top Trading Cycles rounds over the mascots' private picks, validates any ring with OR-Tools CP-SAT against every mascot's eligibility answers, runs the two-phase commit |

Say it honestly in the README: TTC is a central matching step that only ever sees each mascot's pick. The agency is in
the mascots: private preferences, private rule checks, asking their student, counter-offers.

## 5. How it works

1. **Ingest (private, per mascot):** Canvas ICS feed, any personal ICS feed (Google Calendar secret address), job
   shift ICS exports, ASU's public academic-calendar ICS, and texts like "dentist Thu 3pm" or "I got the Amazon
   interview Thu 2pm". Claude (`claude-haiku-5-5`, strict JSON schema, regex fallback, cached) turns texts into events
   and preferences. Every event becomes a private "busy" block with a private label; only "busy" can ever leave.
2. **Sunday check (proactive, weekly):** each mascot compares next week's shifts with busy blocks and texts only on a
   collision: "Your Tue 6-10 Library shift hits CSE 310 exam prep. Find a trade that keeps your hours?" [Yes] [Not now].
3. **Trade rounds:** the Broker opens a round for the conflicted shift(s). Every mascot computes privately which open
   shift it would take (its pick) or passes, using Rulebook + preferences. **All replies are released together at the
   round deadline** (no timing tell). TTC closes cycles; a 1-hop cover is just a cycle of length 2.
4. **Ask the student:** if a mascot is unsure (soft preference, e.g. "Fri 10-2 is your gym slot"), it asks its student
   and may make one counter-offer, then a second round runs. This is shown on screen once.
5. **Validate:** CP-SAT checks the proposed ring against every member's eligibility (each mascot re-runs its Rulebook
   on the exact final ring), minimising changed shifts. "No safe trade" is an honest outcome.
6. **Two-phase commit:** PREPARE (fresh schedule versions, holds) -> every member taps Confirm on Telegram -> the
   Steward card is approved -> COMMIT. Any decline, timeout or stale version -> ABORT, release holds, original shifts
   intact, try the next ring.
7. **Guest path (cold start):** a coworker without a mascot gets a one-tap trade link; their rules show as
   "unverified", so their limits stay their own responsibility.
8. **Winter Break Handoff:** in ASU-listed break weeks, domestic students who go home want shifts gone while F-1
   students who stay may work up to 40 h and often want hours. Mascots match them privately. Report: "N shifts handed
   off, $X kept on campus, 0 rule breaks."
9. **Manager crunch forecast:** the Steward warns a week ahead ("Wed career fair: 5 of 14 staff can't work 10-2"),
   counts only, only when >= 3 people are affected.

## 6. Privacy design (and its honest limits)

- Closed message schemas (Pydantic `extra="forbid", frozen=True`): a pick or a pass is all that can cross the wire.
  A test proves a message carrying `hours` or `reason` is rejected.
- Mascots have a **private diary** (owner-only view: energy bar for room left before the limit that binds first,
  which limit, the quoted rule) and a **public face** identical for everyone: idle, thinking, shrug, covering,
  relieved. Glow comes from trades made, never from hours left.
- Badges only for public positive acts (Clutch, Chain Link, Streak). Never anything about hours, limits, visa or FWS.
  One code path for every student; the F-1 limit is just a private number.

### Mascots come from Codex Pets (user's requirement: use these exactly)

- Every mascot is a pet from **https://codex-pets.net** (open-source gallery, site code MIT:
  https://github.com/portons/codex-pet-share). **Each student chooses their own pet; no two students on a roster
  share one.** The choice is cosmetic and never derived from status.
- The curated, original-art set (no fan art of copyrighted characters) is in **`pets.json`** next to this brief: 18
  pets with id, name, creator, sprite version, atlas size, `spritesheetUrl`, `posterUrl` and `downloadUrl` (all
  verified downloadable tonight). More can be found with `GET https://codex-pets.net/api/pets?page=1&pageSize=10&q=<words>`.
- **Format:** `spritesheet.webp`, 8 columns, cell **192x208**. v1 atlas 1536x1872 (9 rows); v2 atlas 1536x2288
  (11 rows: rows 9-10 are 16 look directions). The download zip holds `pet.json` + `spritesheet.webp`.
- **Animation rows** (row: frames @ fps): 0 idle 6@6, 1 running-right 8@12, 2 running-left 8@12, 3 waving 4@5,
  4 jumping 5@14, 5 failed 8@6, 6 waiting 6@4, 7 running 6@12, 8 review 6@6. Source: `src/playground/core/config.ts`.
- **State mapping:** idle = idle; review = thinking (Sunday check, trade round); waiting = the shrug/pass (identical
  for everyone); jumping = picked/covering; waving = committed; failed = abort (shown on every ring member at once);
  running-left/right = walking to swap places when the ring closes; v2 look rows = facing the trade partner.
- **Choosing:** Telegram `/pet` sends the posters as an album with buttons; the dashboard has a picker. Default
  fallback pet: `debug-duck-v2`.
- **Licensing:** uploaders confirm they may share publicly, but there is no explicit reuse licence for pet art. So
  `scripts/fetch_pets.py` downloads the chosen pets at setup into `web/pets/` (git-ignored, not redistributed in the
  repo), and the README and the UI credit each creator with a link to the pet's page.
- A no-leak test runs the whole demo and scans every serialized message and log line for private values.
- Limits to state in the README: separate processes protect data from peers and employers, not from the server
  operator; allowed fields can still leak a little over many weeks; demo schedules are synthetic and labelled.

## 7. The simulator (built first; it decides the headline)

`sim/simulate.py`: 1,000 random weeks on a realistic 40-person Library roster (equal 4-hour shifts, same wage),
10% F-1, 20% FWS, conflict rate swept 5-25% (survey answers set the central value), **clustered** exam weeks (students
share courses) and Friday-night avoidance (adversarial, so trades don't look inflated), break weeks from ASU's
calendar, and adoption at 25% / 50% / 100% of the roster.
Report per scenario: conflicts fixed by a plain cover, extra fixed only by a trade ring, pay lost with and without
Tag Out. Write `docs/SIMULATION.md` with a chart. **Go/no-go:** if rings add under 10% in normal weeks, the headline
becomes "Sunday check + plain covers + Winter Break Handoff" and rings are a bonus.

## 8. Demo (video first, 3:00, 6 beats)

| Time | Beat |
|---|---|
| 0:00 | Stat card + ASU's own line "be proactive about finding shift coverage". |
| 0:20 | Ana texts her mascot her week; it imports her Canvas feed (real, blurred). **Sunday check: 3 collisions this week: an exam (Canvas), an interview (text), a dentist appointment (calendar). Reasons stay private.** |
| 0:45 | Arena: 6 mascots run a trade round; picks appear, a 3-cycle closes: Ana's Tue 6-10 -> Ben, Ben's Thu 2-6 -> Dev, Dev's Fri 10-2 -> Ana. Ana's mascot is unsure about Fri (her gym slot), asks her, she says OK. Judge view (red DEBUG banner, synthetic): Ben at 17 h of his 20 (his Dining hours count; Library can't see them); a plain cover would put him at 21; the ring keeps him at 17. |
| 1:20 | **The 10-second moment:** three phones buzz at once: "Ben takes your Tue, you take Dev's Fri 10-2, you keep your $64. Confirm?" Three taps, the ring closes on screen, the manager card approves, commit. |
| 1:50 | Break it: edit Dev's schedule before commit; the freshness check fails, abort, original shifts intact, the next ring is proposed. |
| 2:20 | Winter Break Handoff result + simulator chart + survey quote + architecture. Close: "Cubbie already plans a student's week. Tag Out lets students' Cubbies negotiate when their weeks collide." |

`make demo` replays the whole thing deterministically (fixed seeds, cached LLM outputs) for recording.

## 9. Stack (versions checked Oct 24 2026; details in `research/open-source-stack.md`)

- Python 3.12, FastAPI, SQLite (one DB per mascot), uvicorn.
- OR-Tools CP-SAT 9.15 (validation, minimum-change ring); a ~40-line TTC + BFS as the core and test oracle.
- anthropic SDK: `claude-haiku-5-5` for parsing texts and events, `claude-sonnet-5-5` for the private explanation a
  mascot sends its own student. Rules never go into a prompt.
- Pydantic 2 (`extra="forbid", frozen=True`).
- python-telegram-bot 22.8 (long polling, inline buttons, message edits).
- icalendar 7.3 + recurring-ical-events 3.8; ASU public calendar ICS:
  `https://calendar.google.com/calendar/ical/asu.edu_q065bkoducouhbr42c83548dgk%40group.calendar.google.com/public/basic.ics`
  (commit a snapshot).
- Codex Pets sprite sheets (see section 6) animated on a `<canvas>` (frame = column, state = row); Cytoscape.js +
  SSE (sse-starlette) for the arena graph, with each node rendered as the student's pet; no React build.
- Hypothesis + pytest + ruff; GitHub Actions CI badge.
- Optional only if ahead: a2a-sdk 1.2.3 Agent Cards per mascot (copy from repo samples, API changed in 1.0).
- Skip: Timefold, agent frameworks (they put agents in one process), MCP, React, Lottie/Rive, OAuth, n8n.

## 10. Repo layout (`Track 2/tag-out/`, public repo `neric-joel/tag-out`)

```
tag-out/
  README.md            pitch, demo GIF/video, rules table with quotes, simulator results, privacy model + limits, how to run
  docs/RULES.md        exact quoted policy lines with URLs
  docs/SIMULATION.md   results + chart
  docs/DESIGN.md       copy of this brief, sections 1-10
  config/rules.yaml    every limit as data (no hard-coding)
  rulebook/            pure functions + quote checker
  sim/                 simulate.py, ttc.py, oracle.py
  agents/mascot.py     FastAPI app, one process per student (port per mascot), own SQLite
  broker/              rounds, ttc, cpsat validation, two-phase commit
  steward/             manager agent, crunch forecast
  ingest/              ics.py (Canvas/personal/jobs/ASU), text intake (Claude + regex fallback + cache)
  bot/telegram_bot.py  intake, Sunday check, confirm buttons, manager card, guest link
  web/                 arena (Cytoscape + SSE), pet sprite renderer (canvas), pet picker, owner diary, judge view
  web/pets/            downloaded Codex Pets sprite sheets (git-ignored; fetched by scripts/fetch_pets.py)
  seeds/               6 students, Library roster, Ben's Dining hours, ASU calendar snapshot, fixture ICS files
  scripts/             run_all.py (spawns mascots + broker + web + bot), demo.py (make demo)
  tests/               rulebook, ttc vs oracle, Hypothesis invariants, 2PC aborts, no-leak
  Makefile, pyproject.toml, .github/workflows/ci.yml
```

## 11. Build phases (an autonomous session runs these in order; each ends with tests green and a commit)

| # | Phase | Est. | Gate / fallback |
|---|---|---|---|
| P0 | Repo, venv, deps, `.gitignore`, CI, seeds (copy `../pets.json` to `seeds/pets.json`), fixture ICS files, `scripts/fetch_pets.py` (downloads the chosen pets into `web/pets/`); fetch the 4 ASU rule pages and write `docs/RULES.md` with exact quotes; copy this brief to `docs/DESIGN.md` | 45 min | |
| P1 | Rulebook (pure functions, rules.yaml) + Hypothesis tests | 45 min | |
| P2 | TTC + oracle + simulator (adversarial sweep, adoption, break weeks) -> `docs/SIMULATION.md` | 60 min | **Go/no-go on rings (section 7)** |
| P3 | Mascot processes + Broker rounds (deadline release) + CP-SAT validation + one counter-offer round | 75 min | headless ring found |
| P4 | Two-phase commit, freshness abort, no-leak test | 60 min | **If P3-P4 fail by T0+5h: ship plain cover chains** |
| P5 | Ingest: ICS (Canvas, personal, jobs, ASU) + text intake (haiku, schema, regex fallback, cache) | 60 min | missing secrets -> fixtures |
| P6 | Telegram bot: intake, Sunday check, confirm buttons, Steward card, guest link (mocked tests; live if token + chat IDs exist) | 75 min | |
| P7 | Arena dashboard: Cytoscape + SSE, Codex Pets sprite renderer + pet picker, owner diary, judge view, footer | 75 min | |
| P8 | Winter Break Handoff + crunch forecast | 45 min | cut first if behind |
| P9 | `make demo` deterministic replay; draft dashboard recording with Playwright (optional) | 45 min | |
| P10 | README, Mermaid diagrams, `docs/DESIGN.md`, submission text draft, `MORNING.md` report | 45 min | always do this |

Cut order if behind: A2A cards, crunch forecast, Winter Break Handoff, guest link, Gmail interview detection.
Never cut: freshness checks, per-person + manager approvals, abort handling, correct rule labels, the footer.
