# Tag Out

About 10,000 students work at ASU each year ([ASU Work+](https://workplus.asu.edu/learn-more/impact)). When a shift collides with an exam or an interview, ASU's advice is to "be proactive about finding shift coverage" ([ASU Student Employment](https://studentemployment.asu.edu/students/starting-your-role/developing-schedule)), so finding cover is the student's job, and the coworker who takes the shift has no easy way to check it against limits that count hours from all of their campus jobs. Tag Out gives each student worker a mascot agent that privately holds their calendar and their shifts and knows which work-hour rules apply to them. Your mascot negotiates with your coworkers' mascots, and Cubbie can be how you talk to it (a Cubbie Skill is included). Every Sunday at 6 PM (in live mode) it checks the coming week and texts its student only when a shift collides with something. Then the mascots trade shifts in rings and cover chains through a broker that sees shift ids, picks, ok bits and votes, and never reasons, hours or which rule applies, so the people in a ring keep their hours and their pay and nobody has to say why they said no. Nothing changes until every student in the trade confirms (on Telegram, or through Cubbie with the included Skill) and the manager approves.

Built for DevHacks S3 x Cubbie, Track 2 (agent-to-agent coordination). Every student, calendar and number in the demo is synthetic.

## What happens in the demo week

The demo roster is six synthetic student workers at the Library for the week of Monday Oct 26 2026 (`seeds/scenario.py`). Each mascot loads its student's week through the real ingest path: a Canvas feed, a personal calendar and the Library's shift export as ICS files, plus texts parsed by Claude with a regex fallback.

### Sunday check

Five mascots find a collision and text their student. Priya has none, so her mascot stays quiet. The broker sends the Sunday check and gets an empty reply, so it never learns how many collisions anyone has.

| Student | Library shift | Collides with | Where the mascot found it |
|---|---|---|---|
| Ana | Tue 6-10 PM | the evening before her CSE 310 midterm, which her mascot protects for exam prep | her Canvas feed |
| Ben | Thu 2-6 PM | an Amazon interview at 3 PM | his text "I got the Amazon interview Thu 3pm!!" |
| Dev | Fri 10 AM-2 PM | a dentist appointment at 11 AM | his calendar |
| Zoe | Sat 10 AM-2 PM | her sister's wedding in Flagstaff | her calendar |
| Marco | Wed 2-6 PM | the fall career fair | his text "fall career fair wed 1-4, need to be there" |

All five tap "Find a trade". The only thing that leaves each mascot is the shift id.

### Trade rounds

1. The first swap round finds no ring. Ben's mascot picks Ana's Tuesday and Dev's picks Ben's Thursday. The only open shift Ana could take is Dev's Fri 10 AM-2 PM, and that is the slot she keeps for the gym with her roommate. That is a preference, not a rule, so her mascot passes and asks her: "A Fri 10 AM-2 PM Library shift could come to you in a trade, but that's your gym with your roommate slot. Take it so you keep your pay this week?"
2. Ana taps "Take it". In the round after the counter-offer window, her mascot counter-offers by picking Dev's Friday, and the ring Ana -> Dev -> Ben closes: Ana takes Dev's Fri 10 AM-2 PM, Dev takes Ben's Thu 2-6 PM, and Ben takes Ana's Tue 6-10 PM. All three keep their hours and their $64.
3. Nobody can swap with Zoe, so her Saturday goes to a cover round. Priya wants more hours and has room, so she covers it. Zoe gives up that shift's pay.
4. Marco's Wed 2-6 PM has no safe trade, and Tag Out says so. Every coworker is in class or already on shift that afternoon, including Priya, the only one who wants extra hours. The broker hands it to the manager as an open shift with no reason attached: "Open shift: Wed 2-6 PM (was Marco's). No safe trade this week. Post it or cover it?"
5. Before anything moves, each mascot re-checks the exact ring or chain it is in against its own Rulebook, CP-SAT keeps the proposals whose members all said ok and that share no person or shift (this week nothing overlaps, so it keeps both; it matters when a re-check fails or proposals compete), and the two-phase commit asks each student to confirm on Telegram and the manager to approve.

The week ends with 5 asked, 4 fixed (3 by the ring, 1 by Priya's cover), 1 open shift, and $192 of pay kept: the three ring shifts at 4 hours and $16 an hour each. `tests/test_flow.py` checks each of these numbers.

### Ben's 17 hours

Ben is an F-1 student, so he may work at most 20 hours a week across all on-campus jobs. He works 9 hours a week in Dining, which the Library can't see, and 8 at the Library, so he is at 17 of 20. A plain cover of Ana's Tuesday would put him at 21. The ring keeps him at 17, and his confirm text says so: "You'd be at 17 of your 20 hours across all jobs." Only Ben sees that line. The broker and the manager only learn that his mascot said yes.

### Break it

`python -m scripts.demo --break-it` (or `POST /demo/break` on the broker) changes Dev's week after the ring is prepared and before he confirms: he texts "physical therapy thu 3pm". His mascot's schedule version goes up, it votes stale on the held trade, and the ring aborts with every shift where it was. Ana, Ben and Dev each get "That trade was cancelled before anything changed. Your shifts are exactly as they were." Priya's cover of Zoe's Saturday is a separate transaction and still commits.

The broker then runs a second attempt. Dev can't take Ben's Thursday any more, so no ring closes, and the retry commits the chain Priya -> Ben -> Ana -> Dev instead: Priya covers Ben's Thu 2-6 PM, Ben takes Ana's Tue 6-10 PM, Ana takes Dev's Fri 10 AM-2 PM, and Dev drops his Friday. The week still ends with 4 of 5 fixed (`test_editing_a_week_before_commit_aborts_and_retries`). Priya, also on an F-1, would end that week at exactly 20 of her 20 hours with no slack to stay late, so her mascot asks her first (the safe answer comes first) instead of picking the shift on its own.

## Quick start

Python 3.12.

```
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
python -m scripts.fetch_pets     # downloads the mascot art into web/pets/ (git-ignored)
python -m scripts.run_all        # 6 mascots, the Steward, the broker, and the Telegram bot if a token is set
```

Open http://127.0.0.1:8700 for the commons, where the mascots live (next section), with the roster, round log and simulator results below it, or http://127.0.0.1:8700/judge for the judge view, which adds the on-screen phones and the synthetic students' private numbers under a red banner. In a second terminal with the same virtual environment:

```
python -m scripts.demo --all     # the demo week, a reset, then the break-it beat
```

By default the synthetic students tap their own buttons after a short delay. `python -m scripts.run_all --mode live` waits for real taps instead, and `--no-bot` skips Telegram. Logs go to `runtime/logs/`. Without an Anthropic key, text intake uses the committed cache in `seeds/llm_cache` and the regex parser, so the demo runs offline.

### Where the mascots live

The home page is the commons: a small square where all six mascots live on a canvas (`web/js/world.js`). They walk around using every animation in the Codex Pets sprite sheet: idle, running left and right, waving when two of them meet, jumping, waiting, the review pose while they think, the failed pose on an abort, and the 16 look directions on version-2 pets, which they use to face a trade partner. When a trade round opens, the mascots whose students asked for a trade walk to the table; picks appear as grey arrows, a closed ring as blue arrows, and each confirm as a tick over the mascot. After the week they wander off again. You can drag a mascot anywhere, click one to open that student's chat with it, and change their size with the slider.

The chat panel next to the commons is each student's private thread with their own mascot (the same messages arrive on Telegram). The Pets button opens a picker that searches the [Codex Pets](https://codex-pets.net) gallery (3,500+ pets), downloads the chosen sprite sheet into `web/pets/` and gives it to that student; no two students on a roster can share one. Fan art of copyrighted characters (for example the several Goku pets) works locally, but the default roster sticks to original art so a public demo video carries no third-party characters.

### Telegram

1. Create a bot with BotFather. Put its token in a file named `api.env` one folder above the repo's parent, which is `../../api.env` relative to the repo root. The Anthropic key can go in the same file and is optional. Environment variables with the same names also work, and `TAGOUT_ENV_FILE` points to a different file.

   ```
   TELEGRAM_BOT_TOKEN=<token from BotFather>
   ANTHROPIC_API_KEY=<optional>
   ```

2. Start everything with `python -m scripts.run_all --mode live` so the mascots wait for your taps.
3. In Telegram, open your bot and send `/start`, then `/join ana <code>` with Ana's join code (`scripts/run_all.py` prints one code per student and the manager at startup). That chat is now Ana's phone. `/join manager <code>` from another chat gets the manager's approval cards. `/cubbie` sends that student's mascot address and owner token for the Cubbie Skill. Telegram carries plain text and buttons only; the mascots themselves live on the website. Other commands: `/week` lists your shifts, `/diary` shows your room before your tightest limit, `/sunday` runs the Sunday check, `/trade` starts the rounds.

## How it plugs into Cubbie

Cubbie already reads a student's Canvas and Google Calendar and texts them. In Tag Out that makes Cubbie the natural front door to the student's mascot, so the repo includes a Cubbie Skill, [`cubbie-skill/tag-out/`](cubbie-skill/tag-out/SKILL.md), that passes the kit's validator (`validate_cubbie_skill.py`):

- Every Sunday at 6 PM (a Cubbie scheduled check-in) Cubbie reads next week's Canvas exams and due dates and calendar events with its own abilities and hands them to the student's mascot through the owner channel (`POST /import`). The titles stay with the student's mascot; coworkers and the employer only ever see "busy".
- Cubbie relays the mascot's texts (the collision, the "it's your gym slot, take it?" question, the confirm card) to the student by text and taps their answer back (`tagout.py inbox`, `tagout.py answer <code>`). It never answers for the student.
- `python cubbie-skill/tag-out/scripts/tagout.py --sample inbox` runs the whole walk-through offline. The script uses only the Python standard library, as Cubbie's sandbox expects, and the owner token comes from Cubbie's secure input.

So each student's Cubbie becomes their negotiator: it knows their week, and the mascots behind it trade with coworkers' Cubbies without anyone sharing why. Telegram (`bot/`) is the same owner channel for students who don't use Cubbie.

## What we took from ASU Workday

ASU student workers already live in Workday, so Tag Out follows its shapes (checked on a real student account; no data copied):

- Time is entered per day and per position, in Mon-Sun weeks inside a biweekly time period, and each entry is approved by the supervisor. Mascots read their hours history from a Workday-shaped time export (`seeds/workday/<student>_time.csv`, synthetic) through `ingest/workday.py`, summing every ASU position.
- The 25 h average counts ASU jobs only. Ben's Dining job is Aramark, which is not in Workday, so it counts toward his F-1 20 hours but not toward the 25 h average (`Limits.non_asu_employers`).
- The hire date starts the 25 h measurement period: the first 12 months after hire, then October to September (`rulebook.rules.measurement_window`).
- A shift needs a job profile, and a mascot never picks a shift its student's profile can't work (an instructional assistant can't cover a grader).
- The supervisory organization names the manager who approves time; that is who gets the Steward's approval card.

## The agents

| Agent | Runs as | Holds | Does |
|---|---|---|---|
| Mascot x6 (Ana, Ben, Dev, Priya, Zoe, Marco) | one FastAPI process each on ports 8711-8716, each with its own SQLite file `runtime/mascot_<id>.db` | its student's calendar as busy blocks with private labels, their Library shifts, their limits (F-1/J-1 flag, Federal Work-Study award left, hours at other employers, hours history), their preferences (wants more hours, days they never work, soft slots like Ana's gym time) and a private diary | runs the Sunday check; answers each round with one shift id or a pass; asks its student about a soft-preference shift and counter-offers in the next round; re-checks the exact final ring or chain; holds the shifts on PREPARE, asks its student to confirm, and votes yes, no or stale |
| Steward (one per employer, the Library here) | one process on port 8701 | the roster, which the employer already shares with its staff, and pending approvals | serves the roster; on PREPARE checks that each giver still owns the shift; sends the manager an Approve/Deny card and votes; tells the manager about shifts no trade could fill; gives a crunch forecast that reports a slot only when at least 3 staff are busy |
| Broker | one process on port 8700, which also serves the commons website and the event stream | shift ids, picks, ok bits, schedule version numbers and votes | runs Top Trading Cycles swap rounds, the counter-offer window and cover chains; asks every member for an ok bit on the exact final ring or chain; picks proposals with CP-SAT; runs the two-phase commit; retries after an abort |
| Rulebook | a library inside each mascot process (`rulebook/`), with no network and no LLM | the limits in `config/rules.yaml` and the quotes in `docs/rule_quotes.json`; reads one student's numbers at a time | returns eligible, blocked or unverified for a proposed change, with the deciding rule; missing hours history is unverified, never safe; refuses to cite a quote that isn't verbatim in `docs/RULES.md` |

The Telegram bot (`bot/telegram_bot.py`, relay on port 8702) is each student's phone line, not an agent. It forwards texts and taps to the owning mascot with that mascot's owner token and delivers the mascot's messages.

TTC is a central matching step: the broker sees every mascot's pick and closes the cycles. The agent work happens in the mascots, which keep their preferences and rule checks private, ask their student when unsure, and make the counter-offer.

## How it fits together

```mermaid
flowchart TB
    student(["Students on Telegram"])
    manager(["Library manager on Telegram"])
    bot["Telegram bot relay :8702"]
    mascots["6 mascot processes on :8711-8716 (Ana, Ben, Dev, Priya, Zoe, Marco), each with its own SQLite file and Rulebook"]
    anthropic["Anthropic API"]
    broker["Broker :8700, rounds, TTC, CP-SAT, two-phase commit"]
    steward["Steward :8701, Library roster and approvals"]
    arena["Commons website in the browser"]

    student <-->|texts and taps| bot
    manager <-->|approval cards and taps| bot
    bot <-->|owner channel with the owner token| mascots
    bot <-->|manager channel| steward
    mascots -.->|student texts to parse| anthropic
    mascots <-->|TradeRequest, PickRequest and Pick, RingCheck and Eligibility, Prepare, Vote, Decision| broker
    mascots <-->|SlotQuery and BusyBits for the crunch forecast| steward
    broker <-->|roster, Prepare, Vote, Decision, OpenShift| steward
    broker -->|event stream| arena
```

One trade, from the round to the commit:

```mermaid
sequenceDiagram
    participant S as Students on Telegram
    participant M as Ring mascots (Ana, Dev, Ben)
    participant B as Broker
    participant W as Steward
    participant G as Manager on Telegram

    B->>M: PickRequest (open shifts, the shift you would give)
    M-->>B: Pick (one shift id, or a pass)
    Note over B: Every reply is held until the round deadline, then all picks are released together
    B->>B: TTC finds the cycle Ana, Dev, Ben
    B->>M: RingCheck (the exact moves)
    M-->>B: Eligibility (ok bit from each private Rulebook check)
    B->>M: GET /version
    M-->>B: VersionReport
    B->>B: CP-SAT picks proposals with no shared person or shift
    par PREPARE
        B->>M: Prepare (moves, seen_version)
        M->>M: version unchanged, hold the shifts
        M->>S: Confirm this trade?
    and
        B->>W: Prepare (moves)
        W->>W: each giver still owns the shift, hold it
        W->>G: Approve or Deny card
    end
    alt everyone confirms and the manager approves
        S->>M: taps Confirm
        M->>B: Vote yes
        G->>W: taps Approve
        W->>B: Vote yes
        B->>M: Decision commit
        B->>W: Decision commit
        M->>S: Done, the trade went through
    else Dev's week changes before he confirms
        M->>M: version bumped, the held trade is stale
        M->>B: Vote stale
        B->>M: Decision abort
        B->>W: Decision abort
        M->>S: Cancelled before anything changed
        B->>B: next attempt with the shifts still open
    end
```

A `no` vote, a Deny, or no answer before the vote timeout ends the same way as `stale`. [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) lists every endpoint, message type, round phase and commit state.

## Rules the mascots check

Every limit is data in `config/rules.yaml`. The quotes below come from `docs/rule_quotes.json`, and a test fails if any of them is not verbatim in [docs/RULES.md](docs/RULES.md), which has the full passages, the fetch dates and notes on where the sources disagree.

| Rule | Who | Quote | Source |
|---|---|---|---|
| 25 hours a week on average across all ASU jobs and stipends (`aca_25_avg`) | every ASU student worker | "To safeguard the academic success of every student, all student employees are limited to a rolling average of 25 hours per week for the year." | [SSM 305-05](https://public.powerdms.com/ASU/documents/1560576) |
| 20 hours a week in session, summed across every on-campus employer (`f1_weekly_20`) | F-1 and J-1 students | "You are not allowed to work more than 20 hours per week during the fall and spring semesters." | [ASU Student Employment, hourly limits](https://studentemployment.asu.edu/students/international-students/hourly-limits-and-work-rules) |
| 40 hours a week in ASU-listed break weeks (`f1_break_40`) | F-1 and J-1 students | "If you have more than one employer, you are only allowed to work for a total of 20 hours per week combined during the semester and 40 hours per week combined during the summer semester/winter or spring break." | [ASU Student Employment, hourly limits](https://studentemployment.asu.edu/students/international-students/hourly-limits-and-work-rules) |
| Earnings up to the award (`fws_award`) | Federal Work-Study students | "You can only earn up to the amount of your FWS award." | [ASU Student Employment, Federal Work-Study](https://studentemployment.asu.edu/students/preparing-student-employment/federal-work-study) |
| 40 hours a week (`weekly_40`) | everyone | "Students should not work more than a total of 40 hours per week." | [SSM 305-05](https://public.powerdms.com/ASU/documents/1560576) |
| No work during your own class time (`class_time`) | everyone | "Federal Work-Study or hourly student employees may not work during the hours they are scheduled to be in class." | [SSM 305-05](https://public.powerdms.com/ASU/documents/1560576) |

`docs/rule_quotes.json` also holds the two quotes in the pitch above (`stats` and `coverage_on_student`). Tag Out cites them but doesn't enforce them.

## Simulator results

`sim/simulate.py` plays 1,000 random weeks on a synthetic 40-person Library roster with clustered exam evenings, students who avoid Friday nights, and private limits (10% F-1, 20% Federal Work-Study). The headline case from `docs/simulation.json` is 15% of shifts colliding with something and the whole roster on Tag Out (seed 7):

| | Plain covers only | Group chat with two-person swaps (everyone's limits known) | Tag Out |
|---|---|---|---|
| Conflicts fixed | 73.8% | 83.5% | 83.7% |
| Pay lost per week | $671 | $326 | $285 |

The honest reading: most of the gain over plain covers comes from simple two-person swaps, which a well-run group chat could also arrange. Tag Out adds only 0.2 points (± 0.3) of conflicts fixed over that stronger baseline and $41 a week less pay lost (rings of three or more and cover chains). What it changes is how the result is reached: the swaps happen on their own every Sunday instead of through a group chat; nobody posts a reason; and every move is checked against limits that no coworker or manager can see. An unchecked group chat makes about 1.4 limit-breaking covers a week on this roster (1.44 ± 0.09), and Tag Out blocks those. The `docs/DESIGN.md` go/no-go (rings must add 10 points over plain covers) is borderline at 9.8 ± 0.5, so rings are not the headline; the Sunday check, private limit checks and pay kept are ([docs/SIMULATION.md](docs/SIMULATION.md)).

Winter Break Handoff, per simulated break week (Dec 14 2026 to Jan 10 2027, when the F-1 limit is 40 hours): students going home want 54.0 shifts gone, 34.6 of them are handed off to students who stay, and $2,215 of pay stays on campus. Accepted handoffs break 0 rules; an unchecked group chat would break about 3 a week (3.05).

![Conflicts fixed and pay lost per week, plain covers vs Tag Out at 25%, 50% and 100% adoption, by conflict rate](docs/img/simulation.png)

The survey of ASU student workers that would set the real conflict rate is pending, so the conflict rate is swept from 5% to 25% instead of measured. Reproduce with `python -m sim.simulate --weeks 1000 --seed 7`.

## Questions we expect

**Isn't this a central algorithm with extra steps?** The matching step (TTC) is central and sees every pick; we say so. The agent boundary is about custody: each student's calendar, other jobs and limits live in their own mascot process, and the inputs can't be pooled because no employer can see the others. The judge view shows what a Library-only scheduler does with the same week: it offers Ben the Tuesday (it sees 12 Library hours, not his 9 at Aramark, so 21 of 20 F-1 hours) and Dev the Thursday (over the 25-hour average with his rec center job). A careful Ben would catch it himself; the point is that nothing in the employer's tools can, and every check falls on the student. The mascots also do the part a solver can't: Ana's mascot asks her before trading into her gym slot, and Priya's asks before going within an hour of her F-1 limit.

**Is the demo week rigged?** Yes, it is a tour, tuned so each path shows once: a ring after a counter-offer, a cover, an honest open shift, and (in the break-it beat, a live edit) a stale abort. The simulator runs the same TTC, chain and Rulebook functions (`broker/ttc.py`, `rulebook/`) on 1,000 random 40-person rosters, without the processes, counter-offers or two-phase commit, and those are the numbers we quote.

**Why not a group chat that swaps?** If everyone knew everyone's limits, a careful group chat would fix about as many collisions (83.5% vs 83.7%). Nobody knows them, so an unchecked group chat makes about 1.4 limit-breaking covers a week on that roster, everyone has to post why they need out, and someone has to organize it. Tag Out does it on Sunday without anyone asking or explaining.

**Who adopts it first?** The manager, per roster: the Sunday check works for a single student, the crunch forecast and the export are for managers, and rings need most of a roster on board (only 1.9 points at 25% adoption). For students, Cubbie is the distribution: the Skill makes a student's existing Cubbie their mascot's front door.

**Where does an approval land?** The Steward's roster updates and the manager downloads it as CSV or a calendar file for their scheduler or shared sheet. Students enter their time in Workday as they already do; nothing writes to Workday, which ASU controls.

## Privacy

The model:

- Every agent-to-agent message is a closed Pydantic schema in `core/wire.py` with `extra="forbid"` and `frozen=True`. A pick carries one shift id or nothing, an eligibility answer is one boolean, and a vote is yes, no, stale or timeout. There is no field for hours, reasons, rule names or event labels, so a message carrying one fails to parse.
- Each mascot is its own process with its own SQLite file. A student's calendar, limits and preferences live only in that file, and only that process opens it.
- Replies are released together at the round deadline, so how fast a mascot answered says nothing to the other agents or to the commons.
- Passes look identical. A pass because of the F-1 limit, a class, a preference or not wanting the shift is the same message, `"shift_id": null`.
- The no-leak test runs the whole demo week including the abort, records every agent-to-agent request and response, and fails if a key outside the wire schemas or any private string (every calendar label, preference label and other employer's name, plus words like "F-1" and "visa") shows up. It scans the public event stream and the manager's messages too.

Its limits:

- Separate processes protect a student's data from peers and from the employer, not from whoever runs the server. In this build every mascot runs on one machine, and its operator can open every database.
- The allowed fields can still leak a little over many weeks. Which shifts someone asks to trade, their picks and passes, and their stale or no votes are visible to the broker and, by name, on the public event stream the commons shows, and patterns build up.
- TTC is a central matching step. The broker sees every mascot's pick, though only the pick.
- The demo data is synthetic: the six students, their calendars, and the simulated roster.
- With an Anthropic key, the texts a student sends their mascot go to the Anthropic API to be parsed. With `TAGOUT_LLM_EXPLAIN=1`, so do the explanation texts a mascot sends its own student, which carry the private label and, for F-1 students, their hours. Rules and limits never go into a prompt.

[docs/PRIVACY.md](docs/PRIVACY.md) goes party by party and lists the remaining gaps, including peer endpoints that don't authenticate their caller and the Telegram path.

## Tests and CI

[![ci](https://github.com/neric-joel/tag-out/actions/workflows/ci.yml/badge.svg)](https://github.com/neric-joel/tag-out/actions/workflows/ci.yml)

```
ruff check .
pytest
```

`.github/workflows/ci.yml` runs both commands on every push and pull request with Python 3.12 and `TAGOUT_OFFLINE=1`, so CI never calls an API. The end-to-end tests mount every agent's app on one in-process HTTP client (`scripts/inproc.py`); each mascot keeps its own app and SQLite file, and only the transport changes.

| Suite | What it proves |
|---|---|
| `tests/test_rulebook.py` | Every cited quote is verbatim in `docs/RULES.md`. Ben's 9 Dining hours count, so a cover is blocked at 21 hours while a swap keeps him eligible. Break weeks raise the F-1 limit to 40. Missing history is unverified and blocks added hours. The 25-hour average, the Federal Work-Study award and class time each block. A Hypothesis property: no change the Rulebook allows ever breaks the 40-hour, F-1 or 25-hour-average limit. |
| `tests/test_ttc.py` | The demo ring needs the second round. Cycle finding matches a brute-force oracle on random pick graphs (Hypothesis). TTC never puts anyone in two cycles, only gives people shifts they picked, and never beats the oracle's bound. Chains end with someone dropping a shift. |
| `tests/test_twophase.py` | Under every mix of yes, no, stale and silent votes from three mascots and the Steward (Hypothesis), the commit happens only if all say yes, every participant gets the same decision, and an abort leaves the original owners. A forged vote without that member's ballot changes nothing. CP-SAT drops proposals with a no and proposals that overlap. |
| `tests/test_flow.py` | The full demo week end to end: Sunday texts only on collisions, 5 asked, 4 fixed, $192 kept, the counter-offer round, Ben's "17 of your 20 hours", Marco's open shift, and the break-it abort followed by the retry chain. |
| `tests/test_privacy.py` | The schemas reject a pick with `hours` or `reason`, an eligibility answer with a rule, a vote with a reason, and badges that describe limits. The no-leak scan over a full run with the abort. The reason still reaches its owner's phone. |
| `tests/test_baseline.py` | The same week through a Library-only scheduler (sees availability and Library hours, not other jobs) puts Ben at 21 of 20 F-1 hours and Dev over the 25-hour average; the manager's CSV and calendar exports mark the traded shifts. |
| `tests/test_workday.py` | Workday-shaped time rows sum across positions by Mon-Sun week and skip sent-back entries; Aramark hours count for F-1 but not the ASU average; the measurement window starts at the hire date, then runs October to September. |
| `tests/test_cubbie_skill.py` | The Skill's sample mode runs offline, its description fits Cubbie's 200-character list, and items it imports become private busy time on the mascot (and count as a schedule change, so a held trade goes stale). |
| `tests/test_simulate.py` | Tag Out never fixes fewer conflicts or loses more pay than plain covers, no accepted move breaks a limit, the recheck catches a move nobody checked, the same seed gives the same results whatever the worker count, and Winter Break Handoff breaks no rule. |

## Stack

From `pyproject.toml` (minimum versions):

- Python 3.12
- FastAPI 0.162 and uvicorn 0.54 for every agent process, httpx 0.28 between them
- Pydantic 2.14 for the closed wire schemas
- OR-Tools 9.15 (CP-SAT) to choose which rings and chains run
- python-telegram-bot 22.8 with long polling and inline buttons
- icalendar 7.3 and recurring-ical-events 3.8 for Canvas, calendar and shift feeds
- sse-starlette 3.5 for the commons' event stream
- anthropic 2.3: Claude Haiku parses student texts and Claude Sonnet can rephrase a mascot's texts (model ids in `ingest/llm.py`)
- PyYAML 6.0 for `config/rules.yaml`, matplotlib 3.11 for the simulator chart (Pillow comes with it and cuts the pet frames for Telegram)
- SQLite from the Python standard library, one file per mascot
- Development: pytest 9, pytest-asyncio 1.4, Hypothesis 6.170, ruff 0.17

## Credits

The mascots are pets from [Codex Pets](https://codex-pets.net), whose site code is MIT licensed ([portons/codex-pet-share](https://github.com/portons/codex-pet-share)). The pet art has no explicit reuse license, so `scripts/fetch_pets.py` downloads it at setup into `web/pets/`, which is git-ignored. The art is not in this repo. Creators, from `seeds/pets.json`:

| Pet | Creator | In the demo |
|---|---|---|
| [Kitsune](https://codex-pets.net/#/pets/kitsune-spirit) | lama-bird | Ana |
| [Tide](https://codex-pets.net/#/pets/tide-kraken) | lama-bird | Ben |
| [Prism](https://codex-pets.net/#/pets/crystal-kirin) | lama-bird | Dev |
| [Luma](https://codex-pets.net/#/pets/moon-phoenix) | lama-bird | Priya |
| [Gale](https://codex-pets.net/#/pets/storm-griffin) | lama-bird | Zoe |
| [Frost](https://codex-pets.net/#/pets/frost-yeti) | lama-bird | Marco |
| [Cinder](https://codex-pets.net/#/pets/ember-dragon) | lama-bird | |
| [Bolt](https://codex-pets.net/#/pets/thunder-roc) | lama-bird | |
| [Bandit](https://codex-pets.net/#/pets/raccoon) | lama-bird | |
| [Kumo](https://codex-pets.net/#/pets/kumo) | lama-bird | |
| [Nori](https://codex-pets.net/#/pets/nori) | zhan | |
| [Ali](https://codex-pets.net/#/pets/ali) | lillian | |
| [✶✶ (biscuit)](https://codex-pets.net/#/pets/biscuit) | lillian | |
| [white](https://codex-pets.net/#/pets/white) | jinsol | |
| [Cappy](https://codex-pets.net/#/pets/cappy) | bruh | |
| [Rook](https://codex-pets.net/#/pets/rook) | klubbyte | |
| [Rusty](https://codex-pets.net/#/pets/rusty) | luoskrad | |
| [Debug Duck v2](https://codex-pets.net/#/pets/debug-duck-v2) | mbs | default when a student hasn't picked |

---

Not legal or immigration advice. Your DSO and ASU Student Employment decide. Rules are cited; limits are configurable.
