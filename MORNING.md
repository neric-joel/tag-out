# MORNING.md: Tag Out build status

Updated Sun Oct 25 2026, past midnight (Arizona). Submissions close 12:00 PM.

## Status

- [x] P0 repo, venv, seeds, fixtures, docs/RULES.md (67 verbatim quotes from 8 ASU and federal pages)
- [x] P1 Rulebook (pure functions, config/rules.yaml) + Hypothesis tests
- [x] P2 simulator (cloud session, merged): docs/SIMULATION.md, docs/simulation.json, chart
- [x] P3-P4 mascot processes, broker TTC rounds, counter-offer window, cover chains, CP-SAT, two-phase commit, freshness abort, no-leak test
- [x] P5 ingest: ICS (Canvas, personal, job exports, ASU calendar), Claude Haiku text intake with regex fallback and cache, Workday time import
- [x] P6 Telegram bot (@Naazhi_bot), live-tested end to end on your account: Sunday check, counter-offer question, confirm, commit
- [x] P7 website: the mascot commons (living pets), assistant chat, roster board, round log, simulation, judge view, pet gallery
- [ ] P8 Winter Break Handoff is in the simulator and on the site as numbers; there is no live break-week demo (cut first per the brief)
- [x] P9 deterministic demo driver (`python -m scripts.demo --all`) + headless capture script for a draft video
- [x] P10 README, docs/ARCHITECTURE.md, docs/PRIVACY.md, docs/SUBMISSION.md (cloud session, merged, then updated)

Tests: 34 passing (`.venv\Scripts\python -m pytest`), `ruff check .` clean. CI workflow runs both on push.

## Run it (one command)

```
cd "D:\Projects\Dev Hacks\Track 2\tag-out"
.venv\Scripts\python -m scripts.run_all --fresh
```

Then open http://127.0.0.1:8700 (commons) or http://127.0.0.1:8700/judge (adds phones, private limits, Break it).
Buttons: Run Sunday check, then Start trade rounds. Or in a second terminal: `.venv\Scripts\python -m scripts.demo --all`.
For real Telegram taps instead of the synthetic auto-taps: `python -m scripts.run_all --mode live` (60 s counter-offer window, 5 min to confirm).

## What is real, what is synthetic

- Real: the ASU rule quotes, the ASU public academic calendar, the Anthropic key (Haiku parses texts; about $0.01 spent so far), the Telegram bot, the Codex Pets art (downloaded, not committed), the simulator.
- Synthetic: the six students, their calendars, shifts, Workday time entries and limits (`seeds/scenario.py` is the single source).
- Not added: CANVAS_ICS_URL and GCAL_ICS_URL (only you can paste them into `D:\Projects\Dev Hacks\api.env`; the demo uses fixtures), survey numbers.

## The headline numbers (docs/simulation.json, 1,000 synthetic weeks, 40-person roster, 15% conflicts)

- Plain covers fix 73.7% of conflicts; with Tag Out's trades 83.7% (+10.0 points, 95% CI 9.5 to 10.5: borderline against the brief's 10-point bar, so lead with pay).
- Pay lost per week drops from $673 to $284 (58% less), because a swap fixes a collision without anyone giving up the shift.
- Winter break: 34.6 of 54 shifts handed off a week, $2,215 kept on campus, 0 rule breaks; an unchecked group chat would make about 3 a week.

## Demo week (what the video shows)

1. Sunday check: 5 collisions from 3 sources (Canvas exam prep for Ana, a texted Amazon interview for Ben, a dentist in Dev's calendar; Zoe's wedding trip; Marco's career fair). Priya has none, so her mascot stays quiet.
2. Round 1: no ring. Ana's only option is Dev's Fri 10-2, her gym slot, so her mascot asks her. She taps Take it.
3. Round 2: the ring Ana -> Dev -> Ben closes. Ben is F-1 at 17 of 20 (9 Dining hours the Library can't see); a plain cover would put him at 21.
4. Everyone confirms on their phone, the manager approves, commit. Priya covers Zoe's Saturday. Marco's Wed 2-6 honestly has no safe trade and goes to the manager as an open shift. Result: 4 of 5 fixed, $192 of pay kept.
5. Break it (judge view button): Dev's week changes before he confirms; stale vote, abort, nothing moved; the retry commits the chain Priya -> Ben -> Ana -> Dev.

## Your to-do list this morning

1. **8:30** Start it: the command above. Click through the commons and the judge view once. Drag a mascot, move the size slider, click a mascot to open its chat.
2. **Telegram with friends (optional but strong for the video):** each friend opens @Naazhi_bot, presses Start, sends `/join ben` / `/join dev` (you are `/join ana`; a fourth phone can be `/join manager`). Run with `--mode live`, then press Run Sunday check and Start trade rounds on the site. All phones buzz on the confirm step.
3. **Survey:** if you have answers, tell me the numbers and the best quote; I'll put them in the README and pitch. Until then the README says survey results are pending.
4. **Video (3 min):** follow the demo week above. A silent draft can be recorded headless: `.venv\Scripts\python -m scripts.capture video --all` (saves `recordings/demo.webm`, git-ignored). Upload it (YouTube unlisted) and put the link in the README.
5. **Make the repo public** (it's private now, as you asked): `gh repo edit neric-joel/tag-out --visibility public --accept-visibility-change-consequences`.
6. **Submit yourself** from `D:\Projects\Dev Hacks\cubbie-hackathon-kit\skills\cubbie-hackathon\scripts`: `python hackathon.py login --google`, then `python hackathon.py submit --track agents --team "Aju" --pitch "<line from docs/SUBMISSION.md>" --member "<Your Name> <ASU email>" --repo https://github.com/neric-joel/tag-out --video <url>` (preview first, then `--yes`).
7. **After the event:** rotate the Anthropic key, `/revoke` the bot token in BotFather.

## Notes

- Goku: the pet gallery can fetch any Codex Pets pet, including the Goku fan-art pets (Marco had one while testing). For the public video, keep the original-art defaults (Reset demo restores them) to avoid third-party characters.
- Workday: I looked at your Org Chart, Enter My Time and Job pages read-only and copied no personal data. What carried over is in the README section "What we took from ASU Workday" (Workday-shaped time import, hire-date measurement window, ASU-only hours for the 25 h average, job-profile gate, supervisor as approver). Notes: `Track 2/research/workday-findings.md` (outside the repo).
- Telegram messages are plain text now (no mascot images), per your feedback; the mascots live on the website.
- Not legal or immigration advice. Your DSO and ASU Student Employment decide.
