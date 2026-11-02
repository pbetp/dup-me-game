# Update verification — 2 November 2026 (v4.3)

- Full unit/network suite: **105 tests passed** using Python 3.12. Local networking was enabled for the socket tests.
- Original opening smoke: passed exact rendered artwork pixels, all 192 animation frames, wraparound, three window sizes, menu routes, keyboard activation, modal pause/resume, and timer cleanup.
- New lobby smoke: passed host/join layouts at 960×700, 1280×800 and 1600×900, actual disco tile/keyboard color changes, round choices, empty/full/selected/loading room states, keyboard controls, hidden-room hit testing, ready/cancel/disconnect, and animation lifecycle.
- Full GUI gameplay smoke: passed two real clients, discovery, manual ready/start, match/scoring/role swap, rematch, reset-room flow, host dashboard, forfeit, solo bot, connection-file fallback, keys/instruments/settings/help, and responsive solo animation.
- Boss gameplay smoke: passed co-op readiness/start, listening/repetition, HP and team damage, victory, rematch and forfeit.
- New boss-art smoke: passed checks for visible white keys and no obscuring disabled-state rectangle, live hit areas, input gating and note flashes across listening/play/results at three sizes.
- Source assets and the original opening playback code were compared byte-for-byte with the supplied archive and preserved.

The original records below describe the earlier release. The new launcher multiplayer flow requires guest readiness and host Start Game. Reset Room returns launcher players to that waiting room.

---

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
# Music update verification — 10 October 2026

Verified on macOS with Python 3.12:

- The 70 existing regression checks passed, covering game rules, real local sockets, discovery, reconnects, the AI, scoring, and piano UI logic.
- All 10 new music checks passed: asset format/duration/join, independent music volume, master mute (including piano volume zero), single playback instance, cleanup, unavailable files/devices, Windows MCI command handling, and Linux stream rewind/volume behavior. Windows/Linux checks use controlled substitutes for the native output devices.
- The 27 focused music and piano/UI unit checks passed after the final mute change.
- The full GUI smoke check passed with two local clients, automatic discovery, completed matches, rematch, hosting controls, practice/setup, keyboard controls, settings, and selection highlights. No Tk callback errors occurred.
- The real macOS audio check passed: native playback crossed the 120-second boundary and kept playing; piano notes did not interrupt the soundtrack; menu/preview changes preserved playback; Settings fit 960×700 and 1280×800; mute and independent music volume worked; closing released the sound.
- The packaged soundtrack is 120.000 seconds, stereo 44.1 kHz 16-bit PCM, with a four-second circular crossfade. The loop boundary's largest sample step is under 0.01 full scale; peak level is below 0.981.

Actual Windows/Linux audio playback and a two-physical-computer demo were not run in this macOS environment. No third-party Python packages are needed to play the updated game.

Earlier release verification follows below.
