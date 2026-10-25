# Demo video: shot list and narration (3 minutes)

Record the judge view (http://127.0.0.1:8700/judge) so the phones are on screen, or the commons with a real phone
next to it. Start the system with `python -m scripts.run_all --fresh`, then drive it with the buttons or
`python -m scripts.demo --all`. A silent headless draft: `python -m scripts.capture video --all`
(`recordings/demo.webm`). About 400 words; read at a normal pace.

| Time | On screen | Say |
|---|---|---|
| 0:00 | The commons, mascots walking around | About 10,000 students work at ASU. When a shift collides with an exam or an interview, ASU's advice is to find your own coverage. And the coworker who covers you can't see that it would put an F-1 student over 20 hours, because his other job is somewhere else. |
| 0:15 | Click a mascot, its chat opens | Tag Out gives every student worker a mascot. Each one is its own agent, with its own process and its own database, and it holds its student's calendar, shifts and work-hour limits privately. |
| 0:30 | Run Sunday check: five mascots react, Priya stays still | Every Sunday the mascots check next week. Five find a collision, from Canvas, a calendar, and a text that Claude parsed. Priya has none, so her mascot doesn't bother her. |
| 0:45 | Ana's phone: the collision text and "Find a trade" | Ana's Tuesday shift is the night before her midterm. She taps Find a trade. The only thing that leaves her mascot is the shift id. |
| 0:55 | Start trade rounds; log shows "no ring", Ana's ask | The mascots trade through a broker that sees shift ids and yes or no, never reasons or hours. Round one finds nothing: the shift Ana could take is her gym slot. That's a preference, so her mascot asks her instead of deciding. |
| 1:10 | Ring closes: Ana, Dev, Ben | She says yes, and a three-way ring closes: Ana takes Dev's Friday, Dev takes Ben's Thursday, Ben takes Ana's Tuesday. Everyone keeps their hours and their pay. |
| 1:25 | Ben's phone: "17 of your 20 hours" | Ben is on an F-1 with nine hours at Dining that the Library can't see. A plain cover would put him at 21. The ring keeps him at 17, and only Ben sees that number. |
| 1:40 | Confirms land, manager approves, commit; Priya covers Zoe; Marco's shift goes to the manager | Nothing moves until every student confirms and the manager approves. Priya covers Zoe's Saturday. Marco's Wednesday has no safe trade, and Tag Out says so instead of forcing one. |
| 1:55 | Ben's chat: "I woke up sick, can't make it Monday" | Sunday doesn't catch everything. On Monday Ben wakes up sick and texts his mascot. It opens a cover round right away. |
| 2:05 | Zoe takes Ben's Monday | Zoe, who gave up her Saturday for a wedding, has room and takes it, which gets her that pay back. The word "sick" never leaves Ben's mascot. |
| 2:15 | Reset, then Break it: Dev's week changes, "stale", abort | Now we try to break it. While a ring waits for confirmations, Dev books physical therapy. His mascot sees its version change, votes stale, and the whole ring aborts with nothing moved. The broker retries and a chain commits instead. |
| 2:35 | Judge view, Library-only scheduler table | A scheduler that only sees Library hours would have offered Ben the shift that puts him at 21 of 20, and Dev a shift over his 25-hour average. |
| 2:45 | Simulator table | On a simulated 40-person roster a careful group chat that swaps fixes about as many collisions. Tag Out does it on its own every Sunday, without anyone posting a reason, and blocks about one and a half limit-breaking covers a week. |
| 2:55 | Footer | Tag Out. Not legal or immigration advice: your DSO and ASU Student Employment decide. |

Notes

- Keep the default mascots (Reset demo restores them) so no third-party characters are in the public video.
- If friends join on Telegram (`/join <name> <code>` with the codes `run_all` prints), run `--mode live` and film one
  real phone buzzing on the confirm step; it is the strongest shot for "agents, not a script".
- Every student and number in the demo is synthetic; say so in the video description.
