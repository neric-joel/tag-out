# Submission

DevHacks S3 x Cubbie, Track 2 (agent-to-agent coordination). Due Sun Oct 25 2026, 12:00 PM Arizona.

Track: `agents`

## One-line pitch

Each ASU student worker gets a mascot agent that spots next week's shift collisions and trades shifts with coworkers' mascots, checking work-hour limits privately and never sharing why.

## Three sentences

Tag Out gives each ASU student worker a mascot agent that privately holds their calendar and shifts, knows which work-hour limits apply to them, and texts them on Sunday when a shift next week collides with something. The mascots then trade shifts in Top Trading Cycles rings through a broker that only sees which shift each one would take, each mascot re-checks the final ring against its own rulebook, and a two-phase commit needs every student's Telegram confirm and the manager's approval. In a simulated 40-person roster, trades fixed 10.0 more percentage points of conflicts than plain covers (95% CI 9.5 to 10.5) and cut pay lost per week from $673 to $284.

## 150 words

About 10,000 students work at ASU each year, and when a shift collides with school, ASU's advice is to "be proactive about finding shift coverage". Tag Out gives each student worker a mascot agent (its own process and SQLite file) that imports their Canvas feed, calendars, shift exports and texts. Every Sunday it texts only about real collisions. The mascots trade shifts in Top Trading Cycles rings and cover chains through a broker that sees only picks. Each mascot checks the exact final ring in private against ASU's cited limits, including the F-1 limit of 20 hours across every on-campus job, which no single employer sees. CP-SAT picks trades, and a two-phase commit needs every student's Telegram confirm and the manager's approval; a stale schedule aborts it. Closed message schemas and a no-leak test keep reasons private. In a simulated 40-person roster, trades cut pay lost per week by 58%.

## Sources for the numbers above

- 10,000 students and the coverage quote: `docs/rule_quotes.json` (`stats`, `coverage_on_student`), verbatim in `docs/RULES.md`.
- 10.0 points, 9.5 to 10.5, $673, $284 and 58%: `docs/simulation.json` (1,000 weeks, seed 7, 15% conflicts, full adoption). The go/no-go against the 10-point bar is borderline; see `docs/SIMULATION.md`.
- 20 hours across every on-campus job: `f1_weekly_20` in `docs/RULES.md`.

## Still to do before submitting

- [ ] Merge the dashboard (`web/`) and the docs PR into `main`, then run the README quick start from a fresh clone, including `python -m scripts.demo --all`.
- [ ] Record the 3-minute demo video (the six beats in `docs/DESIGN.md` section 8) and add its link near the top of the README.
- [ ] Survey results are pending. Add the numbers from the ASU student worker survey to the README and the pitch only once they are collected. Until then nothing in the repo or the submission claims a survey result.
- [ ] Make `neric-joel/tag-out` public, then check on GitHub that the simulator chart, the Mermaid diagrams and the CI badge render.
- [ ] Submit on the Cubbie site with the kit CLI, track `agents`, before 12:00 PM Arizona on Sun Oct 25 2026.

---

Not legal or immigration advice. Your DSO and ASU Student Employment decide. Rules are cited; limits are configurable.
