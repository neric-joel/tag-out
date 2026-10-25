"""The campus around the Library desk: two more departments, ten more student workers and the people above them.

Everything here is invented and labelled synthetic, like seeds/scenario.py. The Library's six students and its
manager (the Steward) stay as they are; Ben also works at Dining and Dev at the Rec center, so they show up in
those departments too. `scripts/make_fixtures.py` writes the ICS files the new mascots import.

The chain of command follows a Workday supervisory org: student mascot -> shift lead -> department manager ->
backup manager -> Student Employment. ISSC (the international students office) takes F-1 questions only, and
only when the student says to send one. Every rung has a timer; silence counts as no, so a timeout moves a case
up one rung and never approves anything.
"""

from __future__ import annotations

from datetime import datetime

from core.timeutil import PHX

DEPARTMENTS = {
    "library": {"name": "Library front desk", "employer": "library", "role": "desk", "lead": "jordan",
                "manager": "steward"},
    "dining": {"name": "Dining (Aramark, Memorial Union)", "employer": "dining", "role": "dining", "lead": "nia",
               "manager": "dining_mgr"},
    "rec": {"name": "Rec center front desk", "employer": "rec center", "role": "rec", "lead": "theo",
            "manager": "rec_mgr"},
}

# Library students who also work in another department (their one mascot answers for both jobs)
ALSO = {"ben": ["dining"], "dev": ["rec"], "raj": ["dining"]}
JOB_PROFILES = {"ben": ["desk", "dining"], "dev": ["desk", "rec"]}

# weekday index: 0=Mon .. 6=Sun; times are 24h Phoenix. Same shape as seeds/scenario.py, plus a department.
ORG_STUDENTS: list[dict] = [
    {"id": "lena", "name": "Lena", "pet_id": "cappy", "dept": "dining", "job_profiles": ["dining"],
     "limits": {"hours_history": [12, 12, 12, 12, 12, 12, 12, 12], "hire_date": "2025-08-18"},
     "prefs": {}, "shifts": [(1, 11, 15), (3, 11, 15), (5, 10, 14)],
     "classes": [("NUR 210", [0, 2, 4], (8, 0), (9, 50))]},
    {"id": "kofi", "name": "Kofi", "pet_id": "kumo", "dept": "dining", "job_profiles": ["dining"],
     "limits": {"f1_or_j1": True, "f1_continuing": False, "program_end": "2026-12-12",
                "hours_history": [16, 16, 16, 16, 16, 16, 16, 16], "hire_date": "2025-01-13"},
     "prefs": {}, "shifts": [(0, 11, 15), (2, 11, 15), (4, 11, 15), (6, 10, 14)],
     "classes": [("CSE 485", [1, 3], (13, 30), (14, 45))],
     "texts_later": ["Can I work 40 hours over winter break on my F-1 if I graduate in December?"]},
    {"id": "mei", "name": "Mei", "pet_id": "nori", "dept": "dining", "job_profiles": ["dining"],
     "limits": {"f1_or_j1": True, "f1_continuing": True, "hours_history": [12, 12, 12, 12, 12, 12, 12, 12],
                "hire_date": "2026-01-12"},
     "prefs": {}, "shifts": [(1, 16, 20), (3, 16, 20), (5, 14, 18)],
     "classes": [("ACC 231", [0, 2], (10, 30), (11, 45))]},
    {"id": "diego", "name": "Diego", "pet_id": "bramble", "dept": "dining", "job_profiles": ["dining"],
     "limits": {"hours_history": [10, 10, 12, 10, 10, 12, 10, 10], "hire_date": "2025-08-18"},
     "prefs": {"wants_more_hours": True}, "shifts": [(0, 16, 20), (4, 16, 20)],
     "calendar": [("Moving apartments", 5, (8, 0), (15, 0), "other")]},
    {"id": "hana", "name": "Hana", "pet_id": "white", "dept": "dining", "job_profiles": ["dining"],
     "limits": {"hours_history": [8, 8, 8, 8, 8, 8, 8, 8], "hire_date": "2026-05-18"},
     "prefs": {"wants_more_hours": True, "never_weekdays": [5]}, "shifts": [(2, 16, 20), (6, 14, 18)]},
    {"id": "omar", "name": "Omar", "pet_id": "ember-dragon", "dept": "rec", "job_profiles": ["rec", "dining"],
     "limits": {"hours_history": [10, 10, 10, 10, 10, 10, 10, 10], "hire_date": "2024-08-19"},
     "prefs": {"wants_more_hours": True}, "shifts": [(1, 17, 21), (3, 17, 21)]},
    {"id": "tess", "name": "Tess", "pet_id": "red-fox-cub", "dept": "rec", "job_profiles": ["rec"],
     "limits": {"fws": True, "fws_award_remaining": 260.0, "hours_history": [12, 12, 12, 12, 12, 12, 12, 12],
                "hire_date": "2025-08-18"},
     "prefs": {}, "shifts": [(0, 6, 10), (2, 6, 10), (5, 8, 12)],
     "texts_later": ["The fire exit by the weight room is blocked with boxes again, it's unsafe"]},
    {"id": "raj", "name": "Raj", "pet_id": "thunder-roc", "dept": "rec", "job_profiles": ["rec", "dining"],
     "limits": {"f1_or_j1": True, "f1_continuing": True, "other_employer_hours": {"dining": 6.0},
                "non_asu_employers": ["dining"], "hours_history": [18, 18, 18, 18, 18, 18, 18, 18],
                "hire_date": "2025-08-18"},
     "prefs": {"wants_more_hours": True}, "shifts": [(0, 17, 21), (2, 17, 21), (4, 17, 21)],
     "jobs": [("Dining shift (Aramark)", 1, (11, 0), (14, 0)), ("Dining shift (Aramark)", 3, (11, 0), (14, 0))]},
    {"id": "ivy", "name": "Ivy", "pet_id": "kite", "dept": "rec", "job_profiles": ["rec", "dining"],
     "limits": {"hours_history": [8, 8, 8, 8, 8, 8, 8, 8], "hire_date": "2026-08-17"},
     "prefs": {"wants_more_hours": True}, "shifts": [(1, 6, 10), (4, 6, 10)],
     "calendar": [("Hiking trip, Sedona", 5, (6, 0), (18, 0), "other")]},
    {"id": "sam", "name": "Sam", "pet_id": "raccoon", "dept": "rec", "job_profiles": ["rec"],
     "limits": {"hours_history": [12, 12, 12, 12, 12, 12, 12, 12], "hire_date": "2025-01-13"},
     "prefs": {}, "shifts": [(0, 10, 14), (3, 10, 14), (6, 12, 16)]},
]

# The people above the students. Each is its own agent with its own inbox (what lands on their phone).
# `up` is the next rung; `minutes` is how long a case waits for them before it moves up; `answers` says whether
# they act on cases in the recorded demo (the Dining manager is in a meeting all morning, so its timer runs out).
ROLES: dict[str, dict] = {
    "jordan": {"name": "Jordan", "title": "Library shift lead", "kind": "lead", "dept": "library",
               "pet_id": "folio", "up": "steward", "minutes": 120},
    "nia": {"name": "Nia", "title": "Dining shift lead", "kind": "lead", "dept": "dining", "pet_id": "rusty",
            "up": "dining_mgr", "minutes": 120},
    "theo": {"name": "Theo", "title": "Rec center shift lead", "kind": "lead", "dept": "rec", "pet_id": "rook",
             "up": "rec_mgr", "minutes": 120},
    "steward": {"name": "Library manager", "title": "Library front desk manager", "kind": "manager",
                "dept": "library", "pet_id": "rivet", "up": "backup", "minutes": 30},
    "dining_mgr": {"name": "Dining manager", "title": "Aramark unit manager, Memorial Union", "kind": "manager",
                   "dept": "dining", "pet_id": "biscuit", "up": "backup", "minutes": 30, "answers": False},
    "rec_mgr": {"name": "Rec manager", "title": "Rec center operations manager", "kind": "manager", "dept": "rec",
                "pet_id": "bruno", "up": "backup", "minutes": 30},
    "backup": {"name": "Assistant director", "title": "On-call backup manager, all three departments",
               "kind": "backup", "dept": None, "pet_id": "goldie", "up": "hr", "minutes": 30},
    "hr": {"name": "Student Employment", "title": "ASU Student Employment (HR)", "kind": "hr", "dept": None,
           "pet_id": "ali", "up": None, "minutes": 60},
    "issc": {"name": "ISSC", "title": "International Students and Scholars Center (F-1 questions only)",
             "kind": "issc", "dept": None, "pet_id": "owl", "up": None, "minutes": 2 * 24 * 60},
}

# The three things that happen on the demo morning, as each student texts their own mascot.
ORG_DEMO = {
    "callout": ("lena", "I woke up sick, can't make my Saturday shift"),
    "safety": ("tess", "The fire exit by the weight room is blocked with boxes again, it's unsafe"),
    "question": ("kofi", "Can I work 40 hours over winter break on my F-1 if I graduate in December?"),
}

# The story clock for the hierarchy: cases start on Saturday morning of the demo week.
CAMPUS_START = datetime(2026, 10, 31, 6, 30, tzinfo=PHX)


def everyone() -> dict[str, str]:
    """Every person's display name, Library students included (for messages and the org chart)."""
    from seeds.scenario import STUDENTS

    return ({s["id"]: s["name"] for s in STUDENTS} | {s["id"]: s["name"] for s in ORG_STUDENTS}
            | {r: v["name"] for r, v in ROLES.items()})


def members(dept: str) -> list[str]:
    """Who works in a department: its own students plus Library students with a second job there."""
    from seeds.scenario import STUDENTS

    if dept == "library":
        return [s["id"] for s in STUDENTS]
    return [s["id"] for s in ORG_STUDENTS if s["dept"] == dept] + [sid for sid, d in ALSO.items() if dept in d]


def with_profile(role: str) -> list[str]:
    """Everyone trained for a job profile, in any department (the backup manager's campus-wide offer)."""
    from seeds.scenario import STUDENTS

    lib = [s["id"] for s in STUDENTS if role in JOB_PROFILES.get(s["id"], ["desk"])]
    return lib + [s["id"] for s in ORG_STUDENTS if role in s["job_profiles"]]
