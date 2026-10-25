from datetime import date

from core.models import Limits, Student
from ingest.workday import history, parse_time_csv, positions, weekly_totals
from rulebook.rules import asu_week_hours, measurement_window, rooms
from tests.test_rulebook import MON, shift

CSV = """Date,Position,Time Type,Hours,Status
2026-10-12,P1 Student Worker II - Library,Regular Hours Worked - Elapsed,4,Approved
2026-10-14,P1 Student Worker II - Library,Regular Hours Worked - Elapsed,3,Approved
2026-10-15,P2 Student Worker II - Rec center,Regular Hours Worked - Elapsed,5,Submitted
2026-10-16,P1 Student Worker II - Library,Regular Hours Worked - Elapsed,2,Sent Back
2026-10-19,P1 Student Worker II - Library,Regular Hours Worked - Elapsed,6,Approved
not-a-date,P1,Regular,4,Approved
"""


def test_workday_rows_sum_across_positions_by_monday_week():
    rows = parse_time_csv(CSV)
    assert len(rows) == 5  # the malformed row is skipped
    assert positions(rows) == ["P1 Student Worker II - Library", "P2 Student Worker II - Rec center"]
    totals = weekly_totals(rows)
    assert totals[date(2026, 10, 12)] == 12  # 4 + 3 + 5; the sent-back entry doesn't count
    assert history(rows, date(2026, 10, 26), weeks=3) == [0.0, 12.0, 6.0]


def test_aramark_counts_for_f1_but_not_the_asu_average():
    ben = Student(id="ben", name="Ben", limits=Limits(f1_or_j1=True, other_employer_hours={"dining": 9},
                                                      non_asu_employers=["dining"], hours_history=[8] * 8))
    mine = [shift(0, 10), shift(3, 14)]
    assert asu_week_hours(ben, mine, MON) == 8
    by_rule = {r.rule_id: r for r in rooms(ben, mine, MON)}
    assert by_rule["f1_weekly_20"].used == 17 and by_rule["aca_25_avg"].used == 8


def test_measurement_window_starts_at_hire_then_runs_oct_to_sep():
    new = Student(id="n", name="N", limits=Limits(hire_date=date(2026, 5, 18)))
    assert measurement_window(new, MON) == (date(2026, 6, 1), date(2027, 6, 1), "initial")
    old = Student(id="o", name="O", limits=Limits(hire_date=date(2024, 8, 19)))
    assert measurement_window(old, MON) == (date(2026, 10, 1), date(2027, 9, 30), "standard")
