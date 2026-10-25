# Demo video: shot list and narration (about 3 minutes)

`python -m scripts.video` records this tour from the hosted replay with captions and music (`recordings/tagout_demo.mp4`,
git-ignored). To narrate it, read the lines below over the matching captions; each line fits its caption's time.

| Time | On screen | Say |
|---|---|---|
| 0:00 | Card: Ben's hours, 8 + 9 + 4 = 21 of 20 | Ben is on an F-1 visa, so he can work 20 hours a week across every campus job. The Library sees his 8 hours. It can't see his 9 at Aramark Dining, so its scheduler would hand him a cover that puts him at 21. |
| 0:07 | Card: Tag Out | Tag Out gives every student worker a mascot agent that holds their calendar, shifts and limits privately, and trades shifts with coworkers' mascots. |
| 0:13 | Commons, Play the week | Every Sunday each mascot checks next week. Five find a collision and text their student. Only the shift id ever leaves a mascot. |
| 0:28 | Rounds, Ana's ask | In each round a mascot answers with one pick or a pass. Ana's only option is her gym slot, so her mascot asks her instead of deciding. |
| 0:42 | Ring closes, commit | She says yes, a three-way ring closes, and nothing moves until everyone confirms and the manager approves. Four of five fixed, 192 dollars of pay kept. |
| 0:56 | Signed in as Ben | This is Ben's own page: his week, his private chat with his mascot, and 17 of his 20 hours, which only he sees. |
| 1:08 | Ben taps "I'm sick" | Monday morning he wakes up sick. One text opens a cover round right away; his manager hears at once, with no reason, and Ben is told he's still on the schedule until a cover is approved. |
| 1:30 | Manager page, Post an extra shift | The manager sees approvals and open shifts, never reasons. An extra shift goes to every mascot at once; each checks its own student's limits, and Zoe, who wants hours, takes it. |
| 1:52 | How it works, the live graph | Here is every message between the agents. Click one and you read exactly what crossed: a pick is one shift id or nothing. Zero fields outside the schemas, zero private labels. |
| 2:15 | Snoop | We even played a nosy broker that asks every mascot why it passed. All six refuse. |
| 2:28 | Sources and claims, Judge view | Every number traces to a rule quote, the simulator or a test, and a Library-only scheduler would have put Ben at 21 of 20. |
| 2:52 | End card | Tag Out. Try it at tag-out.vercel.app. Not legal or immigration advice: your DSO and ASU Student Employment decide. |

Notes

- The default mascots are original pixel art from a public gallery; the art is loaded from its gallery at runtime, not
  stored in the repo.
- If you film a real phone, use Telegram's light (Day) theme so it matches the site, and open only the bot's chat
  (archive or hide other chats first) so no personal conversations appear.
- Music: "Backed Vibes Clean" by Kevin MacLeod (incompetech.com), CC BY 4.0. Put this credit in the video description.
- Every student and number in the demo is synthetic; say so in the description.
