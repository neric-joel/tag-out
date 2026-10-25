"""Simulator invariants on a short fixed-seed run. The full run is `python -m sim.simulate --weeks 1000 --seed 7`."""

import pytest

from sim.simulate import (
    Params,
    Plan,
    make_break_week,
    make_week,
    plain_covers,
    play_week,
    recheck,
    run_all,
    run_week,
)

P = Params()
SEED = 7
WEEKS = 20


@pytest.fixture(scope="module")
def played():
    out = []
    for i in range(WEEKS):
        week = make_week(P, SEED, P.central_rate, i)
        out.append((week, *play_week(P, week)))
    return out


def test_tag_out_never_fixes_fewer_conflicts_than_plain_covers(played):
    for week, plain, tag, _ in played:
        for share, (plan, _) in tag.items():
            assert plan.count() >= plain.count(), (week.adopter_order[0], share)
    assert sum(plan.count("ring") for *_, tag, _ in played for plan, _ in tag.values()) > 0, "no ring ever closed"


def test_no_accepted_move_breaks_a_limit(played):
    for _, plain, tag, _ in played:
        assert recheck(plain) == []
        for plan, _ in tag.values():
            assert recheck(plan) == []


def test_pay_lost_with_tag_out_is_never_more(played):
    for _, plain, tag, _ in played:
        for plan, _ in tag.values():
            assert plan.pay_lost() <= plain.pay_lost()


def test_same_seed_same_results():
    first = [run_week(P, SEED, 0.10, i) for i in range(5)]
    assert first == [run_week(P, SEED, 0.10, i) for i in range(5)]
    assert first != [run_week(P, SEED + 1, 0.10, i) for i in range(5)]
    assert run_all(P, 2, SEED, workers=1) == run_all(P, 2, SEED, workers=2)


def test_recheck_catches_a_move_nobody_checked():
    week = make_week(P, SEED, P.central_rate, 0)
    pid = next(x for x, person in week.people.items() if person.student.limits.f1_or_j1)
    plan = Plan(week)
    mine = {week.slot(s) for s in plan.held[pid]}
    for sid in [s for s in week.shift if plan.holder[s] != pid and week.slot(s) not in mine][:5]:
        if week.slot(sid) in mine:
            continue
        mine.add(week.slot(sid))
        plan.held[plan.holder[sid]].remove(sid)
        plan.held[pid].append(sid)
        plan.holder[sid] = pid
    assert any(f"{pid}: f1_weekly_20" in x for x in recheck(plan))


def test_winter_break_handoff_breaks_no_rule():
    for i in range(8):
        week = make_break_week(P, SEED, i)
        plan = plain_covers(Plan(week), P.break_helper_extra_shifts)
        assert plan.count() > 0
        assert recheck(plan) == []
