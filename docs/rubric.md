# Dup Me 4.0 — rubric mapping

Source: the supplied three-page **Dup Me** assignment PDF (`Dupme-1525379-17884898224135.pdf`). This is an evidence map, not an awarded grade. The rubric totals **25 points: creativity/demo 5, fundamentals 10, extras up to 10**. It says extras are not considered until fundamental implementation is complete.

**Current position:** the identified implementation gaps are closed. All 61 automated tests and the two-client GUI test pass locally. A physical two-computer demonstration, the actual hotspot check, and the professor's acceptance of creative/extra/AI features remain external verification steps.

## Fundamental implementation — 10 points

“Implemented/tested” below refers to source and local automated evidence. The live setup on two actual computers must still be demonstrated.

| Criterion | Weight | Implementation and evidence | Remaining live proof |
|---|---:|---|---|
| All requirements completed | 1.0 | Implementation mapped in this table; standard rules checked by socket/GUI tests | Complete physical checklist before claiming full completion |
| A runs server and player | 0.5 | Host and play launches both; separate `server.py` + `play.py` also supported | Show A's running programs/windows |
| B runs client only, directly connected | 0.5 | Join opens TCP to host; no server is launched on B | Show B on a second physical computer |
| No manual IP/port entry | 0.5 | START discovers LAN hosts; saved connection JSON fallback | Join B without typing network fields |
| Server sends connected-user information | 1.0 | Welcome/player-list messages; lobby list and both game names | Show both names |
| Nickname and welcome | 0.5 | Validated nickname; explicit `Welcome, name.` in lobby and game | Show each screen |
| Player name and score | 0.5 | Both name/score panels update from server feedback | Demonstrate scoring |
| At least five buttons/keys | 0.5 | 17 chromatic notes with keyboard and mouse input | Play several notes |
| 10-second create / 20-second repeat countdowns | 0.5 | Server deadlines; full creation time even at capacity; early repeat completion only after every position answered | Show normal unaccelerated timers |
| Opponent sees created pattern | 0.5 | Broadcast accepted notes; visible during creation, hidden for repeat | Demonstrate watch/memorize |
| Ordered score, final status and both scores | 0.5 | Correct-index comparison; WIN/LOST/DRAW and final scores | Intentionally make one wrong move |
| Both can rematch | 0.5 | Server counts distinct votes; both are required | One vote waits; second starts |
| Server displays online count and list | 1.0 | Attached and standalone dashboards show count, names and IPs; probes are not players | Show count 2 and names |
| Server reset clears game and scores | 1.0 | RESTART MATCH button (clears scores, restarts round 1) in integrated and separate hosting | Restart after scoring a point |
| Random first player | 0.5 | New match calls random selection from the active pair | Explain/show code; short samples need not alternate |
| Previous winner starts rematch | 0.5 | Server retains winner and selects that player; draw uses random choice | Complete non-draw match and rematch |
| **Total** | **10.0** | **Implementation coverage exists for every item** | **Physical demonstration still required** |

Additional base rules: Standard is exactly two rounds; roles swap; scores are positional; both results offer REMATCH. Longer games are explicitly **Extended match**, so the base demo remains unchanged. The original losing “NICE TRY” label and “HI” welcome were replaced with explicit required wording. The host now always has dashboard access.

## Extra-feature submission candidates — capped at 10 points

The rubric offers 2 points per accepted AI feature and 1 per accepted non-AI feature, with at least one AI feature required. Present the actual behavior below. **The professor determines which features count separately; these are candidate claims, not automatic credit.** Eight accepted non-AI features plus one accepted AI feature would reach the 10-point cap. Additional piano capability is included as a reserve candidate.

| Feature to demonstrate | Category / possible weight | Implementation | Demo |
|---|---|---|---|
| Adaptive DupBot opponent | AI / 2 | Observes human accuracy and recent results, changes difficulty/pattern complexity/recall; uses real TCP | Play with AI; terminal explanation; `test_ai.py` |
| Four synthesized instruments | Non-AI / 1 | Separate Classic Piano, Synthesizer, Electric Piano and Organ waveforms/caches | SET → Instrument; play same note |
| Extended match mode | Non-AI / 1 | 4/6/8/10/12 rounds, alternating roles and accumulated scores | Explicit Extended mode before hosting |
| Offline piano practice/editor | Non-AI / 1 | Works with no server; undo and clear for practice sequences | `play.py --preview` → notes → UNDO/CLEAR (not on the main menu) |
| Post-match positional review | Non-AI / 1 | Expected vs actual note, correct/wrong/missing, round accuracy | ROUND REVIEW after a match |
| CSV match-report export | Non-AI / 1 | User-saved portable report of each position and final scores | SAVE CSV REPORT and open file |
| Sound/visual accessibility settings | Non-AI / 1 | Volume, mute and flash toggle, applied locally | SET controls; Ctrl+M |
| Adaptive display/fullscreen | Non-AI / 1 | Scaled canvas/hit regions across window sizes; fullscreen toggle | Resize and F11, then click keys |
| Connection-loss recovery | Non-AI / 1 | Heartbeat expiry, clear error, safe match cancellation and rejoin | Close peer/reconnect; heartbeat tests simulate silence |
| Expanded chromatic piano and dual input | Reserve non-AI candidate / 1 | 17 correctly positioned white/black keys with both keyboard and mouse | Play C4–E5 with both methods |

AI is rule-based adaptive game intelligence, **not a trained neural model or LLM**. The rubric does not define the algorithm required; confirm the professor's interpretation during the progress check. Review/export and other related features may be grouped by the instructor, so do not promise a specific score before feedback.

Automatic discovery and the server dashboard are presented as fundamental fixes rather than relying on them for extra credit.

## Creativity/demo preparation — 5 points

The existing pixel-art room, chromatic piano, local synthesized audio and adaptive opponent provide creative material. The code cannot guarantee these subjective points. Prepare two charged computers, the same release, a tested shared network, a short pattern, and the [demo sequence](professor-notes.md#a-short-demo-script). Keep [professor notes](professor-notes.md) open. Use Standard first, then demonstrate optional features separately.

## Evidence to retain before final submission

- A completed physical test checklist from [RUN_AND_TEST.md](../RUN_AND_TEST.md).
- A screenshot/photo of both computers playing and A's server count/list.
- A non-draw result and rematch where the winner starts.
- A reset demonstration after a score is earned.
- The test output from `self_test.py` and the GUI test.
- Professor feedback on AI qualification and which extras are counted separately.
