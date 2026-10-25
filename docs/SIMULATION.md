# Simulation: plain covers vs Tag Out rings and chains

**Go/no-go: borderline.** At a 15% conflict rate with 100% of the roster on Tag Out, rings and chains add 10.00 percentage points over plain covers (95% CI 9.5 to 10.5). The 10-point bar in docs/DESIGN.md section 7 sits inside that interval, so the simulation neither clears it nor misses it with confidence. Recommendation: lead with the Sunday check, plain covers and the pay that trades save (below), and present rings as the reason that pay is saved rather than as a bigger fix rate.

What rings and chains clearly change is pay: in the same scenario pay lost per week falls from $673 to $284 (58% less), because a swap fixes a conflict without anyone losing the shift. The points figure moves with the assumptions; changed one at a time (see Sensitivity): helpers take at most 1 extra shift: 19.5; helpers take any number of shifts the rules allow: 8.2; no clustering (every conflict is an individual event): 4.5; heavy clustering (80% of conflicts are shared exam evenings): 11.3; single TTC pass (passers' shifts stay in the pool): 9.0.

- Typical case (15% conflicts, 100% adoption, 1,000 weeks): plain covers fix 73.7% ± 0.9 of conflicts; Tag Out fixes 83.7% ± 0.8; rings and chains add 10.0 points ± 0.5. Pay lost per week drops from $673 ± 10 to $284 ± 7.
- Worst case, same scenario: in at least 1 week in 20, rings and chains add nothing. Tag Out never fixes fewer than plain covers, because the broker keeps the plain-cover plan when that plan is better.
- Worst case in the whole sweep: 5% conflicts with 25% adoption, where rings and chains add 0.5 points ± 0.2. At 15% conflicts with only 25% of the roster on Tag Out they add 1.9 points ± 0.2: rings need most of a roster on board.
- Pitch line (synthetic): "In our simulation of a 40-person roster, plain covers fixed 74% of conflicts; trades fixed 10 percentage points more, and students lost 58% less pay."

![Conflicts fixed and pay lost by conflict rate and adoption](img/simulation.png)

## Conflicts fixed

Mean ± 95% confidence interval over the simulated weeks, as a share of each week's conflicts. "Extra" is Tag Out minus plain covers in the same week, in percentage points. The last two columns say how Tag Out fixed them: many ring and chain fixes are conflicts a plain cover would also have fixed, but with the owner losing the pay (next table).

| Conflict rate (measured) | Conflicts / week | On Tag Out | Plain covers fix | Tag Out fixes | Extra (points) | Fixed by a ring | Fixed by a chain |
|---|---|---|---|---|---|---|---|
| 5% (5.1%) | 6.1 | 25% | 84.3% ± 1.3 | 84.7% ± 1.3 | 0.5 ± 0.2 | 2.8% ± 0.6 | 1.7% ± 0.5 |
| 5% (5.1%) | 6.1 | 50% | 84.3% ± 1.3 | 85.7% ± 1.3 | 1.4 ± 0.3 | 10.1% ± 1.1 | 4.7% ± 0.8 |
| 5% (5.1%) | 6.1 | 100% | 84.3% ± 1.3 | 86.9% ± 1.3 | 2.6 ± 0.4 | 27.9% ± 1.7 | 9.5% ± 1.1 |
| 10% (10.1%) | 12.1 | 25% | 78.7% ± 1.0 | 79.9% ± 1.0 | 1.2 ± 0.2 | 5.8% ± 0.6 | 1.9% ± 0.4 |
| 10% (10.1%) | 12.1 | 50% | 78.7% ± 1.0 | 82.0% ± 1.0 | 3.4 ± 0.3 | 17.8% ± 1.0 | 5.5% ± 0.6 |
| 10% (10.1%) | 12.1 | 100% | 78.7% ± 1.0 | 85.7% ± 1.0 | 7.1 ± 0.5 | 43.8% ± 1.3 | 11.8% ± 0.8 |
| 15% (15.2%) | 18.1 | 25% | 73.7% ± 0.9 | 75.6% ± 0.8 | 1.9 ± 0.2 | 7.3% ± 0.5 | 1.9% ± 0.3 |
| 15% (15.2%) | 18.1 | 50% | 73.7% ± 0.9 | 78.6% ± 0.8 | 5.0 ± 0.3 | 20.6% ± 0.8 | 5.4% ± 0.5 |
| 15% (15.2%) | 18.1 | 100% | 73.7% ± 0.9 | 83.7% ± 0.8 | 10.0 ± 0.5 | 50.1% ± 0.9 | 11.7% ± 0.7 |
| 20% (20.0%) | 23.9 | 25% | 67.8% ± 0.7 | 70.4% ± 0.7 | 2.7 ± 0.2 | 8.2% ± 0.5 | 1.8% ± 0.2 |
| 20% (20.0%) | 23.9 | 50% | 67.8% ± 0.7 | 74.4% ± 0.8 | 6.6 ± 0.4 | 22.1% ± 0.7 | 5.3% ± 0.4 |
| 20% (20.0%) | 23.9 | 100% | 67.8% ± 0.7 | 79.9% ± 0.8 | 12.1 ± 0.5 | 50.6% ± 0.8 | 12.1% ± 0.7 |
| 25% (25.0%) | 29.7 | 25% | 62.2% ± 0.6 | 65.4% ± 0.6 | 3.2 ± 0.2 | 8.4% ± 0.4 | 1.7% ± 0.2 |
| 25% (25.0%) | 29.7 | 50% | 62.2% ± 0.6 | 70.0% ± 0.7 | 7.8 ± 0.4 | 22.7% ± 0.6 | 5.3% ± 0.4 |
| 25% (25.0%) | 29.7 | 100% | 62.2% ± 0.6 | 76.8% ± 0.7 | 14.6 ± 0.5 | 49.8% ± 0.7 | 13.4% ± 0.6 |

## Pay lost and rule breaks

Pay lost is what students lose when their shift moves to someone else and they take nothing back (one shift = 4 h × $16 = $64). A conflict nobody fixes is not counted as pay lost: the student either works it anyway or calls out, and the model doesn't pick. Rule breaks prevented: covers an unchecked group chat would make (first free coworker who wants hours takes it) that break a limit, where that coworker is on Tag Out and their mascot says no.

| Conflict rate | On Tag Out | Pay lost / week, plain covers | Pay lost / week, Tag Out | Rule breaks prevented / week | Weeks Tag Out kept the plain plan |
|---|---|---|---|---|---|
| 5% | 25% | $299 ± 8 | $286 ± 7 | 0.12 ± 0.02 | 32 of 1000 |
| 5% | 50% | $299 ± 8 | $258 ± 7 | 0.23 ± 0.03 | 28 of 1000 |
| 5% | 100% | $299 ± 8 | $192 ± 6 | 0.49 ± 0.05 | 9 of 1000 |
| 10% | 25% | $504 ± 9 | $470 ± 9 | 0.26 ± 0.04 | 63 of 1000 |
| 10% | 50% | $504 ± 9 | $406 ± 8 | 0.50 ± 0.05 | 36 of 1000 |
| 10% | 100% | $504 ± 9 | $250 ± 7 | 1.04 ± 0.07 | 11 of 1000 |
| 15% | 25% | $673 ± 10 | $622 ± 9 | 0.37 ± 0.05 | 91 of 1000 |
| 15% | 50% | $673 ± 10 | $526 ± 9 | 0.71 ± 0.07 | 51 of 1000 |
| 15% | 100% | $673 ± 10 | $284 ± 7 | 1.47 ± 0.09 | 4 of 1000 |
| 20% | 25% | $791 ± 10 | $723 ± 10 | 0.47 ± 0.05 | 93 of 1000 |
| 20% | 50% | $791 ± 10 | $608 ± 9 | 0.91 ± 0.07 | 35 of 1000 |
| 20% | 100% | $791 ± 10 | $308 ± 8 | 1.85 ± 0.10 | 4 of 1000 |
| 25% | 25% | $888 ± 10 | $810 ± 10 | 0.56 ± 0.06 | 74 of 1000 |
| 25% | 50% | $888 ± 10 | $673 ± 10 | 1.06 ± 0.08 | 15 of 1000 |
| 25% | 100% | $888 ± 10 | $323 ± 8 | 2.23 ± 0.12 | 0 of 1000 |

Every final schedule in every plan was re-checked with `rulebook.rules.evaluate` and against each student's raw busy blocks: 0 accepted moves broke a limit or double-booked anyone.

## Winter Break Handoff

1,000 simulated winter-break weeks (Mon Dec 14 2026 to Sun Jan 10 2027, 4 weeks; F-1 limit 40 h in these weeks per config/rules.yaml). 50% of domestic students go home and want every shift gone; every F-1 student stays and wants hours, as do domestic students who stay and wanted more hours. Everyone is on Tag Out. Helpers take at most 4 extra shifts a week (assumption).

| Per break week | Mean ± 95% CI |
|---|---|
| Shifts going-home students want gone | 54.0 ± 0.2 |
| Shifts handed off | 34.6 ± 0.4 (64%) |
| of which F-1 students took | 16.0 ± 0.0 |
| F-1 students over 20 h that week (legal only in a listed break week) | 4.0 ± 0.0 of 4 |
| Dollars kept on campus (pay earned by students who stayed) | $2,215 ± 23 |
| Rule breaks in accepted handoffs | 0 in 1,000 weeks |
| Rule breaks an unchecked group chat would make | 3.05 ± 0.17 |

Over the whole 4-week break that is about 138 shifts handed off and $8,861 kept on campus for one 40-person roster, with 0 rule breaks. The number handed off is set mostly by how many extra shifts the people who stay will take (4, an assumption); a higher cap hands off more. In break weeks there is nothing to trade back (the people leaving can't take a shift), so this is matching plus the private limit check, not rings.

## TTC compared with the best possible rings

`sim/oracle.py` (`max_conflicts_solved`) searches every set of disjoint rings of up to 4 shifts that everyone in them would accept, before any covers. It is exhaustive, so it runs only in weeks with at most 10 conflicted shifts on Tag Out (100% adoption). TTC can also close rings longer than 4, so in a few weeks it can beat this bound. TTC follows each person's ranked picks instead of maximising the count, so it can fix fewer than the bound; passers leave with their own shift and the rest re-point (standard TTC with outside options). The sensitivity row "single TTC pass" shows what that release is worth.

| Conflict rate | Weeks with the bound | TTC ring fixes / week | Best rings of <= 4 / week |
|---|---|---|---|
| 5% | 964 of 1,000 | 1.78 ± 0.12 | 2.13 ± 0.14 |
| 10% | 324 of 1,000 | 3.24 ± 0.22 | 4.26 ± 0.29 |
| 15% | 21 of 1,000 | 3.05 ± 0.77 | 4.19 ± 1.04 |
| 20% | 0 of 1,000 | - | - |
| 25% | 1 of 1,000 | 6.00 ± 0.00 | 6.00 ± 0.00 |

Ring sizes at 15% conflicts, 100% adoption: 2 people: 2,306, 3 people: 828, 4 people: 348, 5 people: 81, 6 people: 31, 7 people: 7, 8 people: 1 (3% longer than 4).

## Sensitivity

Each row changes one assumption, at 15% conflicts and 100% adoption, same seeds.

| Change | Plain covers fix | Tag Out fixes | Extra (points) |
|---|---|---|---|
| none (the model above) | 73.7% ± 0.9 | 83.7% ± 0.8 | 10.0 ± 0.5 |
| helpers take at most 1 extra shift | 62.1% ± 0.8 | 81.6% ± 0.8 | 19.5 ± 0.7 |
| helpers take any number of shifts the rules allow | 75.5% ± 0.9 | 83.7% ± 0.8 | 8.2 ± 0.5 |
| no clustering (every conflict is an individual event) | 94.6% ± 0.4 | 99.0% ± 0.2 | 4.5 ± 0.4 |
| heavy clustering (80% of conflicts are shared exam evenings) | 52.0% ± 1.1 | 63.2% ± 1.3 | 11.3 ± 0.5 |
| single TTC pass (passers' shifts stay in the pool) | 73.7% ± 0.9 | 82.7% ± 0.9 | 9.0 ± 0.5 |

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
| `fws_award_remaining` | (0.0, 400.0) | task brief: $0-$400 left on the award |
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

1,000 weeks per cell, seed 7, 6 worker processes, 100 s. Every week is seeded on its own, so the numbers do not depend on the worker count.

---

Synthetic data. Not legal or immigration advice. Your DSO and ASU Student Employment decide.
