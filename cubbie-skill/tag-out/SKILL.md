---
name: tag-out
description: Checks the student's campus job shifts for next week against their Canvas due dates, exams and calendar every Sunday, and lets their Tag Out mascot trade a colliding shift with coworkers without saying why. Use when the student works an on-campus job and asks to check next week for work conflicts, to find someone to take or swap a shift, or to set up the Sunday shift check.
---

# Tag Out

The student's Tag Out mascot is their private scheduling agent at work: it knows their shifts and their work-hour
limits, and it trades shifts with coworkers' mascots so nobody loses pay or breaks a limit their employer can't see.
This Skill makes Cubbie the mascot's front door: Cubbie reads Canvas and Google Calendar, hands the mascot the
student's week, and carries the mascot's questions and the student's answers by text.

## Setup

No packages. `scripts/tagout.py` uses only the Python 3.12 standard library.

Once per student:

1. Ask for their Tag Out mascot address and their owner token, using Cubbie's **secure input** (the token is a
   secret; name the field `TAGOUT_OWNER_TOKEN`). The student finds both on the Tag Out site under their mascot.
2. Run `python scripts/tagout.py setup --mascot-url <address>`. The script reads the token from the
   `TAGOUT_OWNER_TOKEN` environment variable and saves both under `~/.config/tag-out/` (file mode 600).
3. Offer a **weekly check-in every Sunday at 6 PM** in the student's time zone and create it only after they say yes.

To try it without an account: add `--sample` to any command. It uses `assets/sample_*.json` and never touches the
network.

## Steps for the Sunday check (or "check my week for work conflicts")

1. With Cubbie's **Canvas** ability, get assignments, quizzes and exams due from next Monday to Sunday. Save them as
   `canvas.json`: a list of `{"title", "start", "end", "kind"}` with ISO times in the student's time zone and
   `kind` one of `exam` or `due`. If Canvas is not connected, say so, skip it and continue.
2. With Cubbie's **Google Calendar** ability, get next week's events the same way into `calendar.json` (`kind`
   can be `appointment`, `interview`, `class`, `vacation` or `other`; leave it `other` when unsure).
3. Run `python scripts/tagout.py sync --source canvas --events canvas.json`, then the same with
   `--source calendar --events calendar.json`. The titles go only to the student's own mascot; coworkers and the
   employer only ever see that the student is busy.
4. Run `python scripts/tagout.py inbox`. For each new message, text the student the message as written and its
   choices as a short numbered list. If there is nothing new, send nothing (the mascot only speaks up when a shift
   collides).
5. When the student answers, run `python scripts/tagout.py answer <choice code>` with the code the inbox printed
   for that choice, and text back the one-line reply the script prints.
6. While a trade is open (the inbox said it is waiting for confirmations), create a **background task** that runs
   `inbox` every 2 minutes for up to 30 minutes and texts any new message, so the confirm step reaches the student
   quickly.

## Other things the student can say

- "dentist Thu 3pm", "I got the Amazon interview Thu 2pm", "never schedule me Fridays": run
  `python scripts/tagout.py tell "<their words>"` and text back the reply.
- "Find someone to take my Tue shift": run `inbox`; if no trade is open, tell them the mascot will look in its next
  round and offer to run the check now.

## Rules

- Never answer a trade question or confirm a trade for the student. Run `answer` only after they reply.
- Text only the student. Never message coworkers or the manager; their mascots and the Tag Out bot do that.
- Do not repeat the student's reasons (course names, appointments) to anyone else, and never include them in a
  message the student might forward.
- Footer for any message about work-hour limits: "Not legal or immigration advice. Your DSO and ASU Student
  Employment decide."

## When something fails

- The script prints one line starting with `error:`. Tell the student that line and stop; retry once only if it says
  the mascot was unreachable.
- Missing setup: `error: not set up` means run Setup first.

More detail on what the mascot keeps private: `references/privacy.md`.
