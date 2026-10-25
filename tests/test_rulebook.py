from datetime import date, timedelta

from hypothesis import given, settings
from hypothesis import strategies as st

from core.models import BusyBlock, Limits, Shift, Student
from core.timeutil import at
from rulebook.quotes import quote_for, unverified_quotes
from rulebook.rules import binding, check_change, evaluate, in_break_week

MON = date(2026, 10, 26)


def shift(day: int, start: int, hours: int = 4, sid: str | None = None) -> Shift:
    d = MON + timedelta(days=day)
    return Shift(id=sid or f"s{day}{start}", employer="library", start=at(d, start), end=at(d, start + hours))


def ben() -> Student:
    return Student(id="ben", name="Ben", limits=Limits(f1_or_j1=True, other_employer_hours={"dining": 9},
                                                       hours_history=[17] * 8))


def test_every_quote_is_verbatim_in_rules_md():
    assert unverified_quotes() == []
    for rid in ["aca_25_avg", "f1_weekly_20", "f1_break_40", "fws_award", "weekly_40", "class_time"]:
        quote, url = quote_for(rid)
        assert quote and url and url.startswith("https://")


def test_f1_counts_hours_the_library_cannot_see():
    mine = [shift(0, 10), shift(3, 14)]  # 8 library hours + 9 dining = 17
    cover = shift(1, 18, sid="ana-tue")
    v = check_change(ben(), mine, add=[cover], drop=[], busy=[])
    assert v.status == "blocked" and v.deciding.rule_id == "f1_weekly_20"
    assert "21" in v.deciding.detail


def test_a_swap_keeps_f1_student_where_they_were():
    mine = [shift(0, 10), shift(3, 14, sid="ben-thu")]
    v = check_change(ben(), mine, add=[shift(1, 18, sid="ana-tue")], drop=[mine[1]], busy=[])
    assert v.status == "eligible"


def test_break_week_raises_f1_limit_to_40():
    assert in_break_week(date(2026, 12, 14)) and in_break_week(date(2027, 3, 8))
    assert not in_break_week(MON)
    s = Student(id="p", name="P", limits=Limits(f1_or_j1=True, f1_continuing=True, hours_history=[12] * 8))
    winter = date(2026, 12, 14)
    shifts = [Shift(id=f"w{i}", employer="library", start=at(winter + timedelta(days=i), 9),
                    end=at(winter + timedelta(days=i), 15)) for i in range(5)]  # 30 h
    v = evaluate(s, shifts, [], winter)
    assert any(f.rule_id == "f1_break_40" and f.status == "eligible" for f in v.findings)


def test_break_week_40_needs_next_term_enrollment_and_ends_at_completion():
    from rulebook.rules import f1_cap_for
    winter = date(2026, 12, 14)
    unknown = Student(id="u", name="U", limits=Limits(f1_or_j1=True))
    assert f1_cap_for(unknown, winter) == 20  # not confirmed as continuing: stay at 20
    done = Student(id="d", name="D", limits=Limits(f1_or_j1=True, f1_continuing=False, program_end=date(2026, 12, 13)))
    assert f1_cap_for(done, winter) == 0  # after the program completion date, no on-campus work
    cont = Student(id="c", name="C", limits=Limits(f1_or_j1=True, f1_continuing=True))
    assert f1_cap_for(cont, winter) == 40 and f1_cap_for(cont, MON) == 20


def test_missing_history_is_unverified_never_safe():
    s = Student(id="g", name="Guest")
    v = check_change(s, [], add=[shift(2, 10)], drop=[], busy=[])
    assert v.status == "blocked"  # adding hours with an unknown average is not allowed
    assert v.deciding.rule_id == "aca_25_avg" and v.deciding.status == "unverified"
    swap = check_change(s, [shift(1, 10, sid="x")], add=[shift(2, 10)], drop=[shift(1, 10, sid="x")], busy=[])
    assert swap.status == "unverified"


def test_aca_average_blocks_extra_hours_but_not_a_swap():
    dev = Student(id="dev", name="Dev", limits=Limits(other_employer_hours={"rec": 12},
                                                      hours_history=[25, 26, 24, 25, 25, 26, 24, 25]))
    mine = [shift(2, 10), shift(4, 10, sid="dev-fri"), shift(6, 14)]
    assert check_change(dev, mine, add=[shift(3, 14)], drop=[], busy=[]).deciding.rule_id == "aca_25_avg"
    assert check_change(dev, mine, add=[shift(3, 14)], drop=[mine[1]], busy=[]).status == "eligible"


def test_fws_award_blocks_earning_past_the_award():
    marco = Student(id="m", name="M", limits=Limits(fws=True, fws_award_remaining=40, hours_history=[12] * 8))
    v = check_change(marco, [], add=[shift(1, 10)], drop=[], busy=[])
    assert v.status == "blocked" and v.deciding.rule_id == "fws_award"


def test_no_work_during_class():
    s = Student(id="a", name="A", limits=Limits(hours_history=[10] * 8))
    cls = BusyBlock(id="c", start=at(MON + timedelta(days=3), 13, 30), end=at(MON + timedelta(days=3), 14, 45),
                    kind="class", label="CSE 310", source="class")
    v = check_change(s, [], add=[shift(3, 14)], drop=[], busy=[cls])
    assert v.deciding.rule_id == "class_time"


def test_binding_limit_is_the_smallest_room():
    mine = [shift(0, 10), shift(3, 14)]
    r = binding(ben(), mine, MON)
    assert r.rule_id == "f1_weekly_20" and r.room == 3


@settings(max_examples=150, deadline=None)
@given(
    f1=st.booleans(),
    other=st.integers(0, 15),
    base=st.lists(st.integers(0, 6), min_size=0, max_size=4, unique=True),
    hist=st.lists(st.integers(5, 30), min_size=1, max_size=12),
    add_days=st.lists(st.integers(0, 6), min_size=0, max_size=3, unique=True),
)
def test_eligible_changes_never_break_a_limit(f1, other, base, hist, add_days):
    s = Student(id="x", name="X", limits=Limits(f1_or_j1=f1, other_employer_hours={"o": other}, hours_history=hist))
    current = [shift(d, 10, sid=f"b{d}") for d in base]
    adds = [shift(d, 15, sid=f"a{d}") for d in add_days]
    v = check_change(s, current, add=adds, drop=[], busy=[])
    total = 4 * (len(base) + len(adds)) + other
    if v.status != "blocked":
        assert total <= 40
        if f1:
            assert total <= 20
        assert (sum(hist) + total) / (len(hist) + 1) <= 25
