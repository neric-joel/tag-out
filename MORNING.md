# MORNING.md: Tag Out build status

Updated after every phase. Times are Arizona.

## Status
- [x] P0 repo, venv, seeds, fixtures, docs/RULES.md (67 verbatim quotes, 8 pages)
- [x] P1 Rulebook + Hypothesis tests
- [ ] P2 simulator
- [ ] P3-P4 mascots, broker, CP-SAT, 2PC
- [ ] P5-P6 ingest, Telegram bot
- [ ] P7-P8 dashboard, Winter Break Handoff, forecast
- [ ] P9-P10 demo replay, README

## What is real vs mocked
- Real: Anthropic key (Haiku text intake works, cached in seeds/llm_cache), Telegram bot token (@Naazhi_bot) in api.env.
- Synthetic: all six students and their calendars (seeds/scenario.py -> seeds/ics/*.ics).
- Missing (only you can add): CANVAS_ICS_URL, GCAL_ICS_URL, survey numbers.
