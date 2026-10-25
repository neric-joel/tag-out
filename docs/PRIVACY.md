# Privacy

A mascot knows a lot about its student: their calendar with every label (an exam, a dentist, an interview, a wedding), their shifts at every campus job, whether they are on an F-1 or Federal Work-Study, how many hours they work elsewhere, and their hours history. Trading shifts needs coworkers' mascots to cooperate without learning any of that. This page says what each party can and cannot see in the current build, then lists the leaks that remain.

## What can cross between agents

Only the closed schemas in `core/wire.py`. Every one of them sets `extra="forbid"` and `frozen=True`, so a field that isn't declared fails to parse. The declared fields are shift ids, roster facts about a shift (employer, start, end, owner), a pick (one shift id or null), an ok bit, a schedule version number, a vote (`yes`, `no`, `stale`, `timeout`), a commit or abort decision, one busy bit per roster slot for the forecast, and a public face. There is no field for hours, a reason, a rule name, an event label or a preference. `tests/test_privacy.py` builds a pick with `hours=17`, a pick with a `reason`, an eligibility answer with a `rule` and a vote with a `why`, and each one is rejected.

A few other choices keep the allowed fields quiet:

- The Sunday check reply is empty, so the broker doesn't learn how many collisions a student has.
- A pass is the same message whatever the reason: the F-1 limit, a class, a soft preference, or not wanting the shift.
- The broker waits for the pick deadline and publishes every reply of a round at once, so the arena and other agents can't tell who answered fast.
- The public face is a closed list: name, pet, an animation state, trades made and badges from `Clutch`, `Chain Link` and `Streak`. Nothing about hours, limits, visa status or work-study. Every student goes through the same code path; the F-1 limit is just a private number in their mascot.
- The mascot's private diary (room before the limit that binds first, which limit, the quoted rule) is an owner endpoint.
- The Rulebook runs inside the mascot process with no network and no LLM.

## Who sees what

| Party | Can see | Cannot see |
|---|---|---|
| The student's own mascot | everything about its own student: calendar events with labels and sources, shifts, limits and hours history, preferences, answers to its questions, the diary | any other student's calendar, limits, preferences, picks or votes |
| The student, through the owner channel | their mascot's texts with the reasons ("Your Tue 6-10 PM Library shift hits CSE 310 Midterm 2 prep (from Canvas)"), and their diary | anyone else's |
| Peer mascots | the open shifts offered in a round, with each one's owner (so who asked to trade which shift), the moves of any proposal they are in, coworkers' names in their own student's confirm text, and anyone's public face | why anyone asked, picked, passed or declined; anyone's hours, limits, labels or preferences; other mascots' picks and votes |
| Broker | the roster, every trade request, every pick and pass by agent, each member's ok bit on each proposal, schedule version numbers, every vote | reasons, labels, hours, limits, preferences, collision counts |
| Steward and the manager | the roster it already owns; each proposed trade's moves; an approval card that says "each one's mascot checked their own work limits privately (eligible)"; open shifts with no reason ("No safe trade this week"); crunch forecast counts for slots where at least 3 staff are busy. The Steward process also receives each mascot's busy bit per slot for the forecast. | reasons, event labels, hours at other employers, F-1 or work-study status, why a trade was declined |
| Anthropic | student texts sent to their mascot, for parsing, when an API key is set; with `TAGOUT_LLM_EXPLAIN=1`, the texts a mascot sends its own student | the rules, the limits and the Rulebook's decisions, which never go into a prompt |
| Telegram | every message to and from a linked student's or manager's chat | agent-to-agent messages |
| Anyone who can reach the broker's port | the public event stream and `/state`: trade requests, picks and passes by name, cycles and chains, each vote by name, commits, aborts, the weekly summary, public faces | reasons, labels, hours, limits |
| Whoever runs the server | everything: every SQLite file, the owner tokens in `runtime/tokens/`, the logs, the event log, the Claude cache in `cache/llm/` | nothing is hidden from them |

Ben in the demo shows the difference. His mascot knows he is on an F-1, works 9 hours a week in Dining and would reach 21 hours with a plain cover of Ana's Tuesday. The broker sees only that his mascot picked Ana's Tuesday as a swap and said ok to the ring. The manager's card says his mascot checked his limits privately. Outside the debug judge view, only Ben's own phone and diary show his hours: "You'd be at 17 of your 20 hours across all jobs."

## How it is tested

`tests/test_privacy.py::test_no_private_value_crosses_between_agents` runs the whole demo week in one process, including the break-it abort and the retry. A wiretap on the shared HTTP client records every request and response on the peer paths (`/round/pick`, `/ring/check`, `/version`, `/txn/prepare`, `/txn/decide`, `/txn/vote`, `/trade`, `/sunday`, `/public`, `/busybits`, `/roster`, `/people`, `/open`). The test requires more than 100 recorded messages and more than 25 private strings, then fails if:

- any JSON key in any message is outside the fields the wire schemas declare, or
- any private string appears in any message body. The private strings are every busy-block label and its longer words, every soft-preference label, every other employer's name, the field and rule names `f1_or_j1`, `fws_award`, `hours_history`, `aca_25_avg` and `f1_weekly_20`, and the words "F-1", "visa" and "Aramark".

It runs the same string check over the public event stream and the manager's messages. A second test checks that Ana's own phone does get "CSE 310", because the reason is meant to reach its owner.

What the test does not cover: numbers are not in the list of private strings, because shift times and ids are full of digits; the schemas, which have no field that could hold hours, cover numbers instead. The owner channel, Telegram and the Anthropic calls are outside the scan by design. Timing is not measured.

## Leaks that remain

- Whoever runs the server sees everything. Separate processes and separate SQLite files protect a student's data from peers and from the employer, not from the operator. In this build every mascot runs on one machine. Protecting students from the operator would need each mascot on hardware the student controls.
- The allowed fields can still leak a little over many weeks. Which shifts someone asks to trade, which shifts they pick, when they pass, how often their schedule version changes and whether they ever pick up covers are all visible to the broker. A pattern like "always passes on Friday evenings" can build up over a semester. Nothing adds noise or limits how long the broker keeps history.
- The public event stream names people. `GET /events` and `GET /state` have no authentication and show each pick, each pass and each vote by name, including a `no` or a `stale`. A pass looks the same whatever the reason, but who passed or declined is visible to anyone who can reach port 8700.
- TTC is a central matching step. The broker sees every mascot's pick and per-member ok bits in one place. It is the only party that does; the picks carry no reasons.
- The round deadline hides answer speed from the stream and from other agents, but the broker process itself sees each HTTP reply arrive and could time it.
- Peer endpoints don't authenticate their caller. They rely on binding to 127.0.0.1. A process on the same machine could send a crafted `PickRequest` or `RingCheck` and learn from the answer, for example whether one more 4-hour shift fits under a student's limit. `/busybits` answers any slots it is given, so such a caller could map when a student is busy, though not what the events are. `/version` shows when a student's schedule changes.
- The Steward receives each mascot's busy bits with the mascot's id. The rule of reporting only slots where at least 3 people are busy limits what the manager is shown, not what the Steward process receives.
- Debug mode opens the owner channel. `scripts/run_all.py` always sets `TAGOUT_DEBUG=1` because the demo data is synthetic. In that mode owner endpoints skip the token and the judge view (`/admin/debug`, `/admin/judge`) shows each student's private numbers under a red DEBUG banner. A deployment with real students must leave `TAGOUT_DEBUG` unset. The Steward's manager channel (`/tap`, `/phone`) and its `/admin/auto` have no token in this build at all.
- Anthropic sees what is sent to it. With an API key, each text a student sends their mascot goes to Claude Haiku with the reference week, unless the same text is already cached, for example "I got the Amazon interview Thu 3pm!!". With `TAGOUT_LLM_EXPLAIN=1`, each text a mascot sends its own student goes to Claude Sonnet to be rephrased; those carry the private label and, for F-1 students, their hours ("You'd be at 17 of your 20 hours across all jobs."). Answers are cached on disk: the synthetic demo texts in `seeds/llm_cache/` (committed) and everything else in `cache/llm/` (git-ignored). Tests and CI run with `TAGOUT_OFFLINE=1` and never call the API.
- Telegram sees the owner channel. A student's collision texts, questions and confirm cards travel through Telegram's servers, reasons and hours included. The bot keeps httpx logging at WARNING so the bot token, which sits in request URLs, never reaches the log.
- The demo data is synthetic. The six students, their calendars, their limits, and the simulated 40-person roster are invented. No real student's data was used.

---

Not legal or immigration advice. Your DSO and ASU Student Employment decide. Rules are cited; limits are configurable.
