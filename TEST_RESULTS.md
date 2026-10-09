# Verification — Dup Me 4.0

Date: 8 October 2026. Environment: local macOS, Python 3.12, Tk 8.6. Socket/display permissions were enabled for the tests. Source: this `dup-me-rubric` release.

| Verification | Observed result |
|---|---|
| Python compilation | Passed for project source and tests |
| `python3 -m unittest discover -s tests -v` | **61 tests passed, 27.643 seconds, OK** |
| `python3 -m tests.gui_smoke` | **PASS**, two real Tk client windows; zero Tk callback errors |
| Discovery | Real UDP response identified the real TCP endpoint; malformed discovery datagrams did not break the responder |
| File fallback | Valid saved file reached a server without discovery; malformed/version-mismatched profiles were rejected |
| Full standard match | Correct scores, role swap, WIN/LOST, both names, welcome and result review/export |
| Extended rounds | All supported counts checked in game-engine tests; complete 12-round TCP match and rematch passed; eight-round solo startup checked in GUI |
| Rematch | Both votes required; previous winner starts; draw path covered; selected count retained |
| Reset | Scored match clears; connected users retained; fresh phase token and zero scores on restart |
| Server dashboard | Count/list, hide/reopen, integrated and standalone server, Reset Game |
| Heartbeats | Quiet lobby stays connected; silent client/server triggers disconnect recovery |
| Protocol | Framing, fragmentation/coalescing, malformed/oversized messages, version rejection, turn-token and role checks |
| Lifecycle | Port conflicts, stop/restart, cancelled connection, duplicate names, disconnect/rejoin |
| AI | Adaptive difficulty unit checks; actual TCP human/bot match and rematch; cancelled old bot moves |
| Piano/audio | All 17 key mappings/mouse hit regions; four distinct valid generated WAV variants and cache cleanup |
| Layout | Join modes at 960×700 and 1280×800; game/settings/help interactions and result panel bounds |

Integration/GUI tests shorten selected countdown/display delays to run quickly. Dedicated checks verify production defaults (10/20 seconds) and unchanged creation deadline at 20-note capacity. An empty-pattern test verifies no invented notes or points.

## Not established by these tests

- Two **physical** computers across the actual classroom Wi-Fi or phone hotspot.
- Physical Windows/Linux execution, OS-specific firewall setup, or sound heard through the final presentation speakers.
- A guaranteed grade, creativity score, or instructor acceptance/counting of AI and non-AI features.

Run the physical checklist in `RUN_AND_TEST.md` before final submission. The local two-window test uses real sockets but is not a substitute for that demonstration.
