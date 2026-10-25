# Tag Out demo transcript

Two scripts: the narration of the 2:50 demo video, word for word with what is on screen, and a 4 to 5 minute version for the judging table. Everything on screen is synthetic students and schedules.

## The demo video (2:50)

| Time | On screen | What I say |
|---|---|---|
| 0:00 | Title card | Tag Out: mascots that trade campus shifts without sharing why. |
| 0:05 | The commons: 16 mascots, Ben's card (21 of 20 h vs 17 of 20 h), a mascot picked up and dropped | Ben is on an F-1 visa. A Library-only scheduler gives him twenty-one of twenty hours; his mascot, seventeen. |
| 0:14 | The pet gallery (Codex Pets) | Each student picks their own Codex Pet, and no two share one. |
| 0:21 | Run Sunday check; Ana's Telegram slides in with her mascot's text | On Sunday, Ana's mascot sees her shift hits a midterm, and texts her on Telegram. |
| 0:27 | Ana taps Find a trade in Telegram; the trade rounds start | She taps Find a trade. Mascots trade a shift id and a yes or no, never why. |
| 0:35 | A 3-way ring forms in the commons; the Take it and Confirm cards in Telegram | Nothing moves until everyone confirms and the manager approves. |
| 0:40 | Ana taps Confirm; the roster updates | Ana confirms in Telegram. Three students swapped, and everyone kept their pay. |
| 0:51 | Ana types "Can I pick up extra hours this week?" in Telegram | She asks her mascot in Telegram if she can pick up extra hours. |
| 0:57 | The answer in Telegram, then the same answer in her chat on the site | The answer lands in Telegram and on the site, checked against her award. |
| 1:03 | Signed in as Ben: his week and his private limits | Ben's own page shows his week and his limits across both jobs. |
| 1:08 | Ben types "dentist Thu 3pm"; his mascot notes it | He texts: dentist Thursday at three. Only busy leaves his mascot. |
| 1:14 | Signed in as the Library manager | His coworkers and manager never see his hours or reasons. |
| 1:19 | The manager posts an extra shift and asks for the best meeting hour | The manager posts an extra shift, and finds the best hour for a team meeting. |
| 1:25 | The meeting options (how many are free, no names) | Each mascot answers only busy or free. |
| 1:31 | Judge view: every phone side by side, each mascot's private limits | The judge view shows every phone, and each mascot's private limits. |
| 1:40 | Reset, Sunday check and trade rounds again (sped up) | Now let's break it. |
| 1:48 | The ring waits for confirmations; Break it changes Dev's week | While a ring waits for confirmations, I change Dev's week. |
| 1:55 | Every phone shows the trade cancelled; the broker tries again | Dev's mascot votes no, so the whole ring aborts, and the broker retries. |
| 2:02 | Org chart: Play the morning; Lena's call-out climbs | The org chart has twenty-seven agents. When nobody covers Lena's Saturday, her case climbs. |
| 2:09 | Each rung's timer; the Dining manager doesn't answer | Every rung gets a timer, and silence never approves anything. |
| 2:16 | The safety report and the F-1 question cases; the EHS and ISSC inboxes | Visa questions reach ISSC, and safety reports reach Environmental Health and Safety. |
| 2:26 | How it works: the agent graph; a block dragged | Every message between agents is real, and you can move the blocks around. |
| 2:32 | Snoop: 6 of 6 mascots refuse "why did you pass?" | Snoop asks every mascot why it passed, and the schemas refuse. |
| 2:37 | A message inspected; the Why Telegram panel | No message has a field for a reason. Telegram is just each student's private line. |
| 2:45 | End card | Code and live demo are linked below. Thanks for watching. |

## At the judging table (4 to 5 minutes)

Open the deck, then the live site at tag-out.vercel.app, with the video in a tab as a fallback.

1. **Who and what (20 s).** "I'm Neric. Tag Out gives every student worker a mascot agent that privately knows their week, and the mascots trade shifts with each other without anyone sharing why."
2. **The problem (40 s).** "About 10,000 students work at ASU each year, and when a shift collides with an exam or an interview, ASU's advice is to be proactive about finding shift coverage. So the student does the searching, but their limits are private: an F-1 student can work 20 hours a week across every on-campus job, Work-Study has an award cap, and the reasons are private too. Two employers can't see each other's hours."
3. **Ben (30 s).** "Ben is F-1 and works at the Library and at Aramark Dining. A Library-only scheduler would hand him a 4-hour shift and push him to 21 of 20 hours. His mascot knows both jobs, passes, and closes a three-way swap that keeps him at 17. Nobody learns why."
4. **Live: the week (60 s).** On the site, press Play the week. "Each mascot checks its own student's calendar and texts them. They trade with a shift id and a yes or no, never a reason. Nothing moves until every student confirms and the manager approves." Then type a message to a mascot, for example "I'm sick, can't make Saturday" as a Dining student on the Org chart, and show the case climb.
5. **Why agents (40 s).** "No single system sees every employer, and it shouldn't. Each mascot is its own app with its own database and rulebook. The messages are closed schemas with no field for a reason: Snoop asks every mascot why it passed, and all six reject it before any code runs."
6. **Trust (30 s).** "118 automated tests, including a break-it suite: change Dev's week while a ring waits and the whole trade aborts, nothing moves, and the broker retries. Every limit quotes ASU's own wording; rules are code, never a prompt."
7. **Close (20 s).** "Telegram or Cubbie is the student's private line. The demo video and the code are linked on the last slide. Thanks!"

## Everything in the demo

- **Commons:** 16 student mascots (Codex Pets, no two the same), drag and drop, a size slider, live speech bubbles, pick lines, rings and cover chains.
- **Pet gallery:** search the Codex Pets gallery and give a student a new mascot (live system).
- **Sunday check:** each mascot compares next week with its own student's Canvas and calendar and texts them on Telegram.
- **Trade rounds:** picks with only a shift id and a yes or no, rings and cover chains, CP-SAT to keep non-conflicting proposals, a two-phase commit with each student's and the manager's taps.
- **Telegram:** the real bot chat; Find a trade, Take it, Confirm, and free-text questions answered in Telegram and on the site at once.
- **A student's page:** their week, their private limits across every job, and a chat where "dentist Thu 3pm" becomes a busy block (Claude Haiku routes the text; the rules are code).
- **Manager's page:** approval cards, posting an extra shift, finding the best meeting hour (counts only, no names), the swap rule, the roster download.
- **Judge view:** every phone side by side, each mascot's private limits, a Library-only baseline, and Break it (abort and retry), with a way back out.
- **Org chart:** 27 agents, timed escalations (shift lead, manager, backup), signed escalations, safety reports to EHS, F-1 questions to ISSC, and a box to text as any student.
- **How it works:** every message between agents, draggable blocks, Snoop, a message inspector, and why Telegram.
- **Hosted site:** tag-out.vercel.app replays the real system and runs it live on your own message, with Claude.
