"""The demo roster: six synthetic Library student workers, week of Mon Oct 26 2026.

Everything here is invented and labelled synthetic. `scripts/make_fixtures.py` turns it into the ICS files the
mascots import through the real ingest path (Canvas feed, personal calendar, job exports); the two texts go
through the text intake. Pets are each student's own pick from seeds/pets.json, no duplicates.
"""

from __future__ import annotations

from datetime import date

DEMO_MONDAY = date(2026, 10, 26)
EMPLOYER = "library"
WAGE = 16.0

# weekday index: 0=Mon .. 6=Sun; times are 24h Phoenix
STUDENTS: list[dict] = [
    {
        "id": "ana", "name": "Ana", "pet_id": "kitsune-spirit", "port": 8711,
        "limits": {"fws": True, "fws_award_remaining": 300.0,
                   "hours_history": [12, 14, 16, 12, 14, 12, 16, 14], "hire_date": "2025-08-18"},
        "prefs": {"protect_exam_eves": True,
                  "soft_avoid": [{"weekday": 4, "start_hour": 10, "end_hour": 12, "label": "gym with your roommate"}]},
        "library_shifts": [(1, 18, 22), (5, 10, 14)],
        "classes": [("MAT 343", [0, 2, 4], (9, 0), (9, 50)), ("CSE 310", [1, 3], (13, 30), (14, 45)),
                    ("HST 109", [2], (15, 0), (16, 15))],
        "canvas": [("CSE 310 Midterm 2", 2, (9, 0), (10, 15), "exam"),
                   ("MAT 343 Homework 7 due", 3, (23, 59), (23, 59), "due")],
    },
    {
        "id": "ben", "name": "Ben", "pet_id": "tide-kraken", "port": 8712,
        "limits": {"f1_or_j1": True, "other_employer_hours": {"dining": 9.0}, "non_asu_employers": ["dining"],
                   "hours_history": [8, 8, 8, 9, 8, 8, 8, 8], "hire_date": "2026-01-12"},
        "prefs": {},
        "library_shifts": [(0, 10, 14), (3, 14, 18)],
        "classes": [("CSE 330", [1, 3], (9, 0), (10, 15)), ("CSE 340 lab", [2], (13, 30), (16, 15)),
                    ("EEE 202", [4], (10, 45), (11, 35))],
        "jobs": [("Dining shift (Aramark)", 5, (9, 0), (13, 0)), ("Dining shift (Aramark)", 6, (9, 0), (14, 0))],
        "texts": ["I got the Amazon interview Thu 3pm!!"],
    },
    {
        "id": "dev", "name": "Dev", "pet_id": "crystal-kirin", "port": 8713,
        "limits": {"other_employer_hours": {"rec center": 12.0},
                   "hours_history": [25, 26, 24, 25, 25, 26, 24, 25], "hire_date": "2024-08-19"},
        "prefs": {},
        "library_shifts": [(2, 10, 14), (4, 10, 14), (6, 14, 18)],
        "classes": [("IEE 380", [0, 2, 4], (15, 0), (15, 50))],
        "jobs": [("Rec center front desk", 1, (17, 0), (21, 0)), ("Rec center front desk", 5, (9, 0), (13, 0)),
                 ("Rec center front desk", 3, (9, 0), (13, 0))],
        "calendar": [("Dentist (Dr. Okafor)", 4, (11, 0), (12, 0), "appointment")],
    },
    {
        "id": "priya", "name": "Priya", "pet_id": "moon-phoenix", "port": 8714,
        "limits": {"f1_or_j1": True, "hours_history": [12, 12, 12, 12, 12, 12, 12, 12], "hire_date": "2026-05-18"},
        "prefs": {"wants_more_hours": True},
        "library_shifts": [(0, 14, 18), (2, 14, 18), (4, 14, 18)],
        "classes": [("BME 300", [1, 3], (10, 30), (11, 45)), ("ENG 301", [1], (18, 0), (20, 45)),
                    ("BME 350", [4], (9, 0), (11, 45))],
    },
    {
        "id": "zoe", "name": "Zoe", "pet_id": "storm-griffin", "port": 8715,
        "limits": {"hours_history": [14, 12, 12, 14, 12, 12, 14, 12], "hire_date": "2025-01-13"},
        "prefs": {"wants_more_hours": True, "never_weekdays": [4]},
        "library_shifts": [(1, 10, 14), (5, 10, 14), (6, 10, 14)],
        "classes": [("PSY 290 lab", [2], (13, 30), (16, 20)), ("PSY 230", [3], (13, 30), (16, 15))],
        "calendar": [("Dance team practice", 1, (18, 0), (21, 0), "other"),
                     ("Sister's wedding in Flagstaff", 4, (18, 0), (23, 59), "vacation"),
                     ("Sister's wedding in Flagstaff", 5, (0, 0), (23, 0), "vacation")],
    },
    {
        "id": "marco", "name": "Marco", "pet_id": "frost-yeti", "port": 8716,
        "limits": {"fws": True, "fws_award_remaining": 40.0,
                   "hours_history": [12, 12, 12, 12, 12, 12, 12, 12], "hire_date": "2025-08-18"},
        "prefs": {},
        "library_shifts": [(2, 14, 18), (3, 10, 14), (5, 14, 18)],
        "classes": [("ECN 211", [1], (18, 0), (20, 45)), ("ACC 231", [3], (15, 0), (16, 15))],
        "calendar": [("Internship (off campus)", 4, (9, 0), (13, 0), "other"),
                     ("Intramural soccer", 5, (10, 0), (12, 0), "other")],
        "texts": ["fall career fair wed 1-4, need to be there"],
    },
]

# The edit a judge makes in the "break it" beat: Dev books physical therapy on Thu afternoon after the ring is
# proposed, so Dev can no longer take Ben's Thu 2-6. The freshness check must abort the ring.
BREAK_IT_EDIT = {"student": "dev", "text": "physical therapy thu 3pm", "weekday": 3, "start": (15, 0),
                 "end": (16, 0), "kind": "appointment", "label": "Physical therapy"}

# Workday positions (synthetic numbers). Dev's rec center job is a second ASU position, so it shows in Workday;
# Ben's Dining job is Aramark, so it doesn't (his mascot knows it from his own calendar).
POSITIONS = {"library": "P900101 Student Worker II - Library front desk",
             "rec center": "P900233 Student Worker II - Rec center front desk"}
SUPERVISORY_ORG = "University Libraries >> Library Front Desk Student Workers (synthetic)"

# Who confirms on behalf of the employer.
MANAGER = {"id": "manager", "name": "Library manager"}
