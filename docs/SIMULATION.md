# Simulation: plain covers vs Tag Out rings and chains

**Go/no-go: go.** At a 15% conflict rate with 100% of the roster on Tag Out, rings and chains fix 10.3 percentage points more of the week's conflicts than plain covers (95% CI ± 0.5), above the 10-point bar in docs/DESIGN.md section 7. Most of that gain comes from two-person swaps, which a well-run group chat could also arrange (stronger baseline below), so rings should not lead the pitch on their own. The lower end of the confidence interval (9.8) is under 10, so the margin is thin. The margin depends on assumptions: changed one at a time, these push it under 10 points: helpers take any number of shifts the rules allow (8.4); no clustering (every conflict is an individual event) (4.2); single TTC pass (passers' shifts stay in the pool) (9.5) (see Sensitivity).

**Against a stronger baseline** where the group chat also arranges two-person swaps before anyone covers (no app needed): it fixes 82.7% ± 0.9 of conflicts and loses $323 ± 8 of pay a week. Tag Out fixes 0.4 points ± 0.3 more than that and loses $283 ± 7. What a group chat can't do is the rest: rings of three or more, cover chains, and checking every move against limits it can't see.

- Typical case (15% conflicts, 100% adoption, 1,000 weeks): plain covers fix 72.8% ± 0.9 of conflicts; Tag Out fixes 83.1% ± 0.9; rings and chains add 10.3 points ± 0.5. Pay lost per week drops from $662 ± 10 to $283 ± 7.
- Worst case, same scenario: in at least 1 week in 20, rings and chains add nothing. The simulated broker never fixes fewer than plain covers, because it keeps the plain-cover plan when that plan is better (the live broker in broker/engine.py runs rings first and does not yet make that comparison).
- Worst case in the whole sweep: 5% conflicts with 25% adoption, where rings and chains add 0.4 points ± 0.1. At 15% conflicts with only 25% of the roster on Tag Out they add 2.1 points ± 0.2: rings need most of a roster on board.
- Pitch line (synthetic): "On a simulated 40-person roster, plain covers fix 73% of conflicts. A group chat that also arranged two-person swaps would reach 83% if everyone knew everyone's limits. Tag Out reaches 83% on its own every Sunday, without anyone sharing a reason, and blocks about 1.5 limit-breaking covers a week."

![Conflicts fixed and pay lost by conflict rate and adoption](img/simulation.png)

## Conflicts fixed

Mean ± 95% confidence interval over the simulated weeks, as a share of each week's conflicts. "Extra" is Tag Out minus plain covers in the same week, in percentage points. The last two columns say how Tag Out fixed them: many ring and chain fixes are conflicts a plain cover would also have fixed, but with the owner losing the pay (next table).

| Conflict rate (measured) | Conflicts / week | On Tag Out | Plain covers fix | Tag Out fixes | Extra (points) | Fixed by a ring | Fixed by a chain |
|---|---|---|---|---|---|---|---|
| 5% (5.2%) | 6.1 | 25% | 84.2% ± 1.2 | 84.6% ± 1.2 | 0.4 ± 0.1 | 3.0% ± 0.6 | 1.5% ± 0.4 |
| 5% (5.2%) | 6.1 | 50% | 84.2% ± 1.2 | 85.5% ± 1.2 | 1.3 ± 0.3 | 9.5% ± 1.1 | 4.5% ± 0.7 |
| 5% (5.2%) | 6.1 | 100% | 84.2% ± 1.2 | 87.4% ± 1.2 | 3.1 ± 0.4 | 28.0% ± 1.7 | 10.0% ± 1.1 |
| 10% (10.1%) | 12.1 | 25% | 78.9% ± 1.0 | 80.1% ± 1.0 | 1.2 ± 0.2 | 6.1% ± 0.6 | 1.7% ± 0.4 |
| 10% (10.1%) | 12.1 | 50% | 78.9% ± 1.0 | 82.2% ± 1.0 | 3.3 ± 0.3 | 17.9% ± 1.0 | 6.0% ± 0.7 |
| 10% (10.1%) | 12.1 | 100% | 78.9% ± 1.0 | 85.7% ± 1.0 | 6.8 ± 0.5 | 44.1% ± 1.3 | 11.4% ± 0.9 |
| 15% (15.2%) | 18.1 | 25% | 72.8% ± 0.9 | 74.9% ± 0.9 | 2.1 ± 0.2 | 7.6% ± 0.5 | 2.0% ± 0.3 |
| 15% (15.2%) | 18.1 | 50% | 72.8% ± 0.9 | 78.0% ± 0.9 | 5.2 ± 0.4 | 21.2% ± 0.8 | 5.2% ± 0.5 |
| 15% (15.2%) | 18.1 | 100% | 72.8% ± 0.9 | 83.1% ± 0.9 | 10.3 ± 0.5 | 49.8% ± 1.0 | 12.1% ± 0.7 |
| 20% (20.0%) | 23.9 | 25% | 67.7% ± 0.7 | 70.1% ± 0.7 | 2.4 ± 0.2 | 7.8% ± 0.5 | 1.9% ± 0.2 |
| 20% (20.0%) | 23.9 | 50% | 67.7% ± 0.7 | 73.6% ± 0.8 | 5.9 ± 0.3 | 21.4% ± 0.7 | 5.1% ± 0.4 |
| 20% (20.0%) | 23.9 | 100% | 67.7% ± 0.7 | 79.6% ± 0.8 | 11.9 ± 0.5 | 50.5% ± 0.8 | 12.8% ± 0.7 |
| 25% (25.0%) | 29.8 | 25% | 62.6% ± 0.6 | 65.7% ± 0.7 | 3.2 ± 0.2 | 8.7% ± 0.4 | 1.8% ± 0.2 |
| 25% (25.0%) | 29.8 | 50% | 62.6% ± 0.6 | 70.2% ± 0.7 | 7.6 ± 0.3 | 22.4% ± 0.6 | 5.4% ± 0.4 |
| 25% (25.0%) | 29.8 | 100% | 62.6% ± 0.6 | 76.6% ± 0.8 | 14.1 ± 0.5 | 49.8% ± 0.7 | 13.1% ± 0.6 |

## Pay lost and rule breaks

Pay lost is what students lose when their shift moves to someone else and they take nothing back (one shift = 4 h × $16 = $64). A conflict nobody fixes is not counted as pay lost: the student either works it anyway or calls out, and the model doesn't pick. Rule breaks prevented: covers an unchecked group chat would make (first free coworker who wants hours takes it) that break a limit, where that coworker is on Tag Out and their mascot says no.

| Conflict rate | On Tag Out | Pay lost / week, plain covers | Pay lost / week, Tag Out | Rule breaks prevented / week | Weeks Tag Out kept the plain plan |
|---|---|---|---|---|---|
| 5% | 25% | $301 ± 8 | $288 ± 7 | 0.14 ± 0.03 | 41 of 1000 |
| 5% | 50% | $301 ± 8 | $263 ± 7 | 0.26 ± 0.04 | 37 of 1000 |
| 5% | 100% | $301 ± 8 | $195 ± 6 | 0.53 ± 0.05 | 18 of 1000 |
| 10% | 25% | $508 ± 10 | $474 ± 9 | 0.27 ± 0.04 | 75 of 1000 |
| 10% | 50% | $508 ± 10 | $410 ± 9 | 0.53 ± 0.05 | 46 of 1000 |
| 10% | 100% | $508 ± 10 | $252 ± 7 | 1.07 ± 0.07 | 9 of 1000 |
| 15% | 25% | $662 ± 10 | $610 ± 10 | 0.39 ± 0.05 | 96 of 1000 |
| 15% | 50% | $662 ± 10 | $515 ± 9 | 0.75 ± 0.07 | 39 of 1000 |
| 15% | 100% | $662 ± 10 | $283 ± 7 | 1.49 ± 0.09 | 6 of 1000 |
| 20% | 25% | $784 ± 10 | $719 ± 10 | 0.49 ± 0.06 | 100 of 1000 |
| 20% | 50% | $784 ± 10 | $605 ± 10 | 0.94 ± 0.08 | 40 of 1000 |
| 20% | 100% | $784 ± 10 | $301 ± 7 | 1.87 ± 0.10 | 2 of 1000 |
| 25% | 25% | $884 ± 10 | $800 ± 10 | 0.55 ± 0.06 | 87 of 1000 |
| 25% | 50% | $884 ± 10 | $665 ± 10 | 1.08 ± 0.08 | 30 of 1000 |
| 25% | 100% | $884 ± 10 | $322 ± 7 | 2.18 ± 0.11 | 1 of 1000 |

Every final schedule in every plan was re-checked with `rulebook.rules.evaluate` and against each student's raw busy blocks: 0 accepted moves broke a limit or double-booked anyone.

## Winter Break Handoff

1,000 simulated winter-break weeks (Mon Dec 14 2026 to Sun Jan 10 2027, 4 weeks; F-1 limit 40 h in these weeks per config/rules.yaml). 50% of domestic students go home and want every shift gone; every F-1 student stays and wants hours, as do domestic students who stay and wanted more hours. Everyone is on Tag Out. Helpers take at most 4 extra shifts a week (assumption).

| Per break week | Mean ± 95% CI |
|---|---|
| Shifts going-home students want gone | 53.8 ± 0.2 |
| Shifts handed off | 32.3 ± 0.4 (60%) |
| of which F-1 students took | 13.6 ± 0.2 |
| F-1 students over 20 h that week (legal only in a listed break week) | 3.4 ± 0.0 of 4 |
| Dollars kept on campus (pay earned by students who stayed) | $2,066 ± 25 |
| Rule breaks in accepted handoffs | 0 in 1,000 weeks |
| Rule breaks an unchecked group chat would make | 3.70 ± 0.20 |

Over the whole 4-week break that is about 129 shifts handed off and $8,265 kept on campus for one 40-person roster, with 0 rule breaks. The number handed off is set mostly by how many extra shifts the people who stay will take (4, an assumption); a higher cap hands off more. In break weeks there is nothing to trade back (the people leaving can't take a shift), so this is matching plus the private limit check, not rings.

## TTC compared with the best possible rings

`sim/oracle.py` (`max_conflicts_solved`) searches every set of disjoint rings of up to 4 shifts that everyone in them would accept, before any covers. It is exhaustive, so it runs only in weeks with at most 10 conflicted shifts on Tag Out (100% adoption). TTC can also close rings longer than 4, so in a few weeks it can beat this bound. TTC follows each person's ranked picks instead of maximising the count, so it can fix fewer than the bound; passers leave with their own shift and the rest re-point (standard TTC with outside options). The sensitivity row "single TTC pass" shows what that release is worth.

| Conflict rate | Weeks with the bound | TTC ring fixes / week | Best rings of <= 4 / week |
|---|---|---|---|
| 5% | 965 of 1,000 | 1.79 ± 0.12 | 2.16 ± 0.15 |
| 10% | 332 of 1,000 | 3.30 ± 0.23 | 4.31 ± 0.30 |
| 15% | 24 of 1,000 | 3.92 ± 0.84 | 4.92 ± 1.15 |
| 20% | 0 of 1,000 | - | - |
| 25% | 1 of 1,000 | 8.00 ± 0.00 | 8.00 ± 0.00 |

Ring sizes at 15% conflicts, 100% adoption: 2 people: 2,269, 3 people: 886, 4 people: 306, 5 people: 89, 6 people: 25, 7 people: 7, 8 people: 3 (3% longer than 4).

## Sensitivity

Each row changes one assumption, at 15% conflicts and 100% adoption, same seeds.

| Change | Plain covers fix | Tag Out fixes | Extra (points) |
|---|---|---|---|
| none (the model above) | 72.8% ± 0.9 | 83.1% ± 0.9 | 10.3 ± 0.5 |
| helpers take at most 1 extra shift | 61.7% ± 0.8 | 80.8% ± 0.9 | 19.1 ± 0.7 |
| helpers take any number of shifts the rules allow | 74.8% ± 0.9 | 83.2% ± 0.9 | 8.4 ± 0.5 |
| no clustering (every conflict is an individual event) | 94.8% ± 0.4 | 99.0% ± 0.2 | 4.2 ± 0.3 |
| heavy clustering (80% of conflicts are shared exam evenings) | 51.9% ± 1.1 | 62.9% ± 1.3 | 11.0 ± 0.6 |
| single TTC pass (passers' shifts stay in the pool) | 72.8% ± 0.9 | 82.3% ± 0.9 | 9.5 ± 0.5 |

## How one week is played

1. A fresh roster: 40 students, each with classes, 2-4 Library shifts that avoid their classes, an 8-week hours history, and private limits (F-1 20 h across all on-campus jobs, 25 h average, FWS award, 40 h week). Then the week's life events: shared-course exam evenings (clustered) and individual events, calibrated so the expected share of shifts that collide equals the conflict rate. A shift never collides with its owner's class; classes only stop people taking other shifts.
2. **Plain covers** (the baseline, no Tag Out): conflicts go to the group chat in a random order; coworkers who want hours answer in a random order; the first one who is free and passes `check_change(add=[shift])` takes it. The owner loses that pay.
3. **Tag Out**: each conflicted shift owned by an adopter is one TTC agent. Its picks are the other conflicted adopters' shifts its owner is free for, would take, and that pass `check_change(add=[pick], drop=[own])`, ranked by the owner's private slot preference. `broker.ttc.ttc` closes rings. Then `broker.ttc.chains` builds cover chains from what is left: helpers are adopters who want hours; a covered owner may take another open shift hours-neutral. Then plain covers handle everything still open, including every non-adopter's conflict. Every ring and chain is re-checked as a whole before it commits; one no drops it (a chain falls back to a shorter one).
4. The broker never proposes a plan worse than plain covers: in a week where rings-first fixes fewer conflicts or loses more pay than the plain-cover plan, it keeps the plain-cover plan and adds only rings among the conflicts left over. The tables count those weeks.
5. Every final schedule is re-checked with `rulebook.rules.evaluate`.

## Model and assumptions

All parameters live in one dataclass, `Params`, at the top of `sim/simulate.py`.

| Parameter | Value | Source or assumption |
|---|---|---|
| `students` | 40 | task brief and docs/DESIGN.md s7: one 40-person Library roster |
| `wage` | 16.0 | docs/DESIGN.md s7 "same wage"; seeds/scenario.py WAGE |
| `shift_hours` | 4 | docs/DESIGN.md s7 "equal 4-hour shifts" |
| `slot_starts` | (10, 14, 18) | task brief: 10-14, 14-18, 18-22 every day |
| `shifts_per_student` | (2, 4) | task brief: 2-4 shifts a week (8-16 h) |
| `f1_share` | 0.1 | docs/DESIGN.md s7: 10% F-1 |
| `f1_other_hours` | (0, 9) | task brief: 0-9 h/week at another on-campus employer |
| `fws_share` | 0.2 | docs/DESIGN.md s7: 20% Federal Work-Study (domestic only; DESIGN s3) |
| `f1_continuing_share` | 0.85 | assumption: most F-1 student workers in fall continue into spring |
| `fws_award_remaining` | (0.0, 400.0) | task brief: $0-$400 left after the week's own shifts |
| `history_weeks` | 8 | task brief: 8 weeks of hours history for everyone |
| `history_noise` | 2.0 | assumption: past weekly totals vary +-2 h around the usual load |
| `near_cap_share` | 0.1 | assumption ("a few near the 25 h average"): a second ASU job puts them at 22-25 h |
| `courses` | 12 | assumption: the roster shares 12 courses, so exams pile onto the same evenings |
| `courses_per_student` | 4 | assumption: a 12-credit load |
| `clustered_share` | 0.5 | assumption: half of all conflicts are shared-course exam evenings (18-22) |
| `extra_events_per_student` | 1 | assumption: one more 2-3 h event a week that only blocks cover time |
| `fri_evening_avoid_share` | 0.4 | task brief: 40% never take Friday-evening shifts |
| `wants_hours_share` | 0.3 | task brief: 30% want more hours; only they act as cover helpers |
| `helper_extra_shifts` | 2 | assumption: someone who wants hours takes at most 2 extra shifts a week |
| `release_passers` | True | broker/ttc.py: a passer keeps their shift and leaves; the rest re-point (standard TTC) |
| `conflict_rates` | (0.05, 0.1, 0.15, 0.2, 0.25) | task brief sweep |
| `central_rate` | 0.15 | task brief: central conflict rate |
| `adoption` | (0.25, 0.5, 1.0) | task brief: share of the roster on Tag Out |
| `go_points` | 10.0 | docs/DESIGN.md s7 go/no-go: rings and chains must add 10 points |
| `term_monday` | 2026-10-26 | an in-session week (the demo week in seeds/scenario.py) |
| `break_mondays` | 2026-12-14, 2026-12-21, 2026-12-28, 2027-01-04 | config/rules.yaml: winter break Dec 14 - Jan 10 |
| `going_home_share` | 0.5 | task brief: half of domestic students go home and want every shift gone |
| `break_helper_extra_shifts` | 4 | assumption: someone staying over break takes at most 4 extra shifts |

Limits of this model:
- Synthetic students and calendars. The survey numbers are not in yet; the conflict rate is swept instead of measured.
- One employer, one role, equal shifts and wages. Other employers' hours count toward limits but their shifts can't be traded.
- Everyone answers. Nobody declines a ring at the confirm step, and no manager rejects one.
- Who is on Tag Out is random. Real adoption would cluster in friend groups and shared shifts.
- Weeks are independent; hours history doesn't carry from one simulated week to the next.

## Reproduce

```
python -m sim.simulate --weeks 1000 --seed 7
```

1,000 weeks per cell, seed 7, 6 worker processes, 118 s. Every week is seeded on its own, so the numbers do not depend on the worker count.

---

Synthetic data. Not legal or immigration advice. Your DSO and ASU Student Employment decide.
