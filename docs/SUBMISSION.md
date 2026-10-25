# Submission

DevHacks S3 x Cubbie, Track 2 (agent-to-agent coordination). Due Sun Oct 25 2026, 12:00 PM Arizona.

Track: `agents`

## One-line pitch

Each ASU student worker gets a mascot agent that spots next week's shift collisions and trades shifts with coworkers' mascots, checking work-hour limits nobody else can see.

## Three sentences

Tag Out gives each ASU student worker a mascot agent that privately holds their calendar, shifts and work-hour limits, and texts them on Sunday only when a shift next week collides with an exam, an interview or an appointment. The mascots trade shifts in rings and cover chains through a broker that sees shift ids, picks and yes/no answers but never reasons or hours; each mascot re-checks the exact trade against ASU's cited limits, including the F-1 limit of 20 hours across every on-campus job that no single employer can see, and nothing moves until every student confirms and the manager approves. On a simulated 40-person roster, Tag Out fixes about as many collisions as a group chat that swaps would if everyone knew everyone's limits (83.7% vs 83.5%), but on its own every Sunday, with no one posting a reason, and it blocks about 1.4 covers a week that would break a limit nobody else can see.

## 150 words

About 10,000 students work at ASU each year, and when a shift collides with school, ASU's advice is to "be proactive about finding shift coverage". Tag Out gives each student worker a mascot agent, its own process and database, that reads their Canvas feed, calendars, Workday-style hours and texts. Every Sunday it texts only about real collisions. Mascots trade shifts in Top Trading Cycles rings and cover chains through a broker that never sees reasons or hours. Each mascot checks the exact trade in private against ASU's cited limits, including the F-1 limit across all on-campus jobs, and asks its student before going near a limit. A two-phase commit needs every student's confirm and the manager's approval; a changed schedule aborts it. Students see their mascots live on the website and chat with them on Telegram; a Cubbie Skill (tested against a local mascot) lets Cubbie be that chat. A Library-only scheduler would have offered an F-1 student a shift that put him at 21 of 20 hours.

## Sources for the numbers above

- 10,000 students and the coverage quote: `docs/rule_quotes.json` (`stats`, `coverage_on_student`), verbatim in `docs/RULES.md`.
- 84% vs 74%, the group-chat-with-swaps comparison and 1.4 limit-breaking covers a week: `docs/simulation.json` (1,000 weeks, seed 7, 15% conflicts, full adoption). Tag Out adds only 0.2 points over the swap-capable group chat; the gain is privacy, automation and the blocked limit breaks, not more fixes. See `docs/SIMULATION.md`.
- 21 of 20 hours: the judge view's Library-only scheduler comparison and `tests/test_baseline.py` (Ben's 9 Aramark Dining hours are invisible to the Library).
- 20 hours across every on-campus job: `f1_weekly_20` in `docs/RULES.md`.

## Still to do before submitting

- [ ] Record the 3-minute demo video and add its link near the top of the README (a silent draft: `python -m scripts.capture video --all`).
- [ ] Survey results are pending. Add the numbers from the ASU student worker survey to the README and the pitch only once they are collected. Until then nothing in the repo or the submission claims a survey result.
- [ ] Make `neric-joel/tag-out` public, then check on GitHub that the simulator chart, the Mermaid diagrams and the CI badge render.
- [ ] Submit on the Cubbie site with the kit CLI, track `agents`, before 12:00 PM Arizona on Sun Oct 25 2026.

---

Not legal or immigration advice. Your DSO and ASU Student Employment decide. Rules are cited; limits are configurable.
