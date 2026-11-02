# Dup Me 4.3 — Neon multiplayer lounge

A two-player piano memory game built with Python sockets and Tkinter. This release adds matching animated host, join, and waiting-room screens while preserving the original opening GIF, 17-key piano, four instruments, adaptive opponent, and extended matches. **Use version 4.3 on both computers.** See [UI_UPDATE.md](UI_UPDATE.md) for the updated flow and checks.

Start with **[RUN_AND_TEST.md](RUN_AND_TEST.md)**. Open **[docs/professor-notes.md](docs/professor-notes.md)** during your presentation; it contains the network facts, architecture, questions and answers, and demo checklist. **[docs/rubric.md](docs/rubric.md)** maps each marking item to its implementation and evidence. **[TEST_RESULTS.md](TEST_RESULTS.md)** distinguishes automated checks from the physical demo still needed.

## Quick start

Extract the ZIP before running it. Use Python 3.10 or newer with Tkinter (development checks used Python 3.12 on macOS). Install Pillow once for the animated opening screen:

```sh
python3 -m pip install -r requirements.txt
python3 play.py
```

On Windows, install with `py -3 -m pip install -r requirements.txt`, then use `py -3 play.py`. In PyCharm or VS Code, open the extracted folder and run `play.py` with a local Python interpreter.

- **One computer:** **SINGLE PLAYER** → enter your nickname → pick AI level → **2 STD** rounds → **START**.
- **Two computers:** connect both to the same network. Both choose **MULTIPLAYER** and enter different nicknames. A picks **HOST A GAME → START HOSTING**; B picks **JOIN A GAME**, which searches automatically, then presses **JOIN GAME**. In the waiting room B presses **I'M READY** and A presses **START GAME**. Nobody types an IP or port.
- **Boss co-op (two computers):** both choose **MULTIPLAYER**, set **GAME MODE → BOSS CO-OP**, then A picks **HOST A GAME → START HOSTING** and B picks **JOIN A GAME → JOIN GAME**. B marks ready in the waiting room; A starts the fight. The join list only shows games of the mode you picked. See [Boss co-op](#boss-co-op) below.
- If discovery is blocked, A can **Save Connection File** directly from the waiting room or server dashboard. Transfer that file to B, select **JOIN A GAME → LOAD FILE**, then **JOIN GAME**. This requires an actual reachable TCP connection and does not bypass network isolation.
- **Practice (offline):** **PRACTICE** → pick a level (Easy / Medium / Hard: 3 / 4 / 5 notes to find) and 10, 20 or 30 melodies → **START**. Listen, then play the melody back by ear. Only the first note is shown (and lit on the keyboard), so you find the rest by interval; it is not scored. **Space** replays the melody. Like a typing test, the board shows live **ACC** (exact notes), **PREC** (pitch closeness: one semitone off still scores 92%), **NPM** (correct notes per minute) and **COMBO**, and the results screen adds perfect melodies, best combo, average miss distance and the notes you missed most.
- **Standard** follows the required two rounds. **Extended match** offers 4, 6, 8, 10 or 12 rounds. The joining client follows the host's selection.

HOST A GAME runs a server dashboard inside the game window. Open it with **DASHBOARD** in the lobby or **SERV** on the game board. It displays the online player count, names, addresses, roles, scores, timer, and activity log. **RESET ROOM** clears the scores and returns everyone to the waiting room for fresh readiness and host start (the standalone server retains **RESTART MATCH**); **END MATCH** ends the match now and declares the winner on current scores. **BACK TO GAME** (or Esc) hides it; the server keeps running. Closing the host's main game window stops the server.

## Animated disco opening

The opening screen plays the exact supplied Orbit Keyboard GIF: rotating disco ball, piano presses, pad lights and twinkling stars. The five pictured buttons open the same existing Single Player, Multiplayer, Practice, Settings and Quit actions. Use the mouse, or Up/Down/Tab and Enter. The complete artwork stays visible at every window size; extra space is filled with dark margins. Keep `assets/ui/disco-opening.gif` with the game. Pillow is used only to decode and scale this artwork; gameplay, networking, scoring and audio are unchanged.

## Menu and boss artwork

The menu pages use the approved disco-space artwork in `assets/ui`, played and fitted to the window like the opening screen:

| Page | Artwork |
|---|---|
| Single Player (Play vs DupBot) | `single-orbit-dojo.gif` (S1 · Orbit Dojo) |
| Multiplayer | `multiplayer-rooftop-jam.gif` (M2 · Rooftop Jam) |
| Practice | `practice-meteor-rehearsal.gif` (P2 · Meteor Rehearsal) |
| Settings | `settings-orbital-mixer.gif` (T1 · Orbital Mixer) |
| Boss co-op fight | `boss-concert-party.png` (Concert Party) |

The painted buttons are the real buttons. Controls whose state changes (nickname box, choice buttons, sliders, checkbox, status text) are drawn live exactly over the painted ones; on Multiplayer the 1V1 / BOSS CO-OP switch sits where the Wi-Fi hint was painted. In the boss fight, the painted piano is the playable keyboard, and the phrase, HP, P1/P2 tags, banner and note ribbons are drawn live over the artwork. Host, Join, and both waiting-room views now share a simpler neon lounge in `src/client/lobby_screen.py`: a rotating disco ball, animated keyboard, city skyline, two player cards, and live controls. Results and Help keep the original pixel-room pages.

## Game rules

The server randomly selects the first creator. Creation lasts 10 seconds, with a maximum of 20 notes; the opponent watches and memorizes. Repetition lasts up to 20 seconds, ending early if every position has been answered. One point is awarded for each correct note at the correct position. Roles swap in round two, then both players see **WIN**, **LOST**, or **DRAW**, and both scores. Both must press **REMATCH**. The previous winner creates first; a draw chooses randomly.

A full pattern does not shorten the creation countdown. An empty pattern remains empty and earns zero points. In launcher-hosted rooms, Reset Room clears the match and scores, clears guest readiness, and returns to the waiting room. In standalone-server mode, Restart Match still starts round 1 immediately when two players remain. Any player can press **EXIT** on the game board to leave at once: the player who exits always gets **LOST**, the opponent **WIN**, with the scores so far. In offline practice EXIT returns to the main menu.

## Boss co-op

You and a friend team up against **THE DISSONANT** (80 HP). Each player has 8 HP.

1. **Listen:** every phrase, the boss plays each of you your own melody. Your notes appear one by one in your ribbon and light up on the keyboard.
2. **Repeat:** the notes hide. Play your melody back in order before the timer ends. **Correct key = 1 boss damage. Wrong key = 1 self damage.** Notes you leave unplayed count as wrong.
3. **Team attack:** both melodies are revealed with ✓ / ✗ and the total damage dealt to the boss.

Melodies grow from 4 to 8 notes. A player on 0 HP is knocked out and watches; the team loses if both are knocked out and wins when the boss reaches 0 HP. EXIT leaves the fight, which ends it as a defeat for both. REMATCH needs both votes. The host's **SERVER DASHBOARD** shows boss HP, player HP and damage dealt.

## Controls and extras

White keys: `Z X C V B N M , . /` · Black keys: `S D G H J L ;`. Mouse clicks work too. The range is chromatic C4–E5.

**SET** selects Classic Piano, Synthesizer, Electric Piano or Organ, volume, mute and key flashes. `F11` toggles fullscreen (some laptops require Fn); `Ctrl+M` toggles mute; `F1` opens help. Offline preview supports undo and clear. Live notes are final. Match results offer a round-by-round review and CSV export; these reveal no extra information during a live turn.

**Background music:** Arrival at Zenith starts automatically and repeats continuously across menus, gameplay, practice, and results. Open **SETTINGS → MUSIC · ARRIVAL AT ZENITH** to change its volume (default 18%). Set music to **0** to turn it off while keeping the piano audible. **PIANO VOLUME** controls the notes separately; the speaker button and `Ctrl+M` mute all audio. Closing the game stops the soundtrack. The bundled two-minute WAV has a crossfaded transition, so it is ready to loop offline without conversion or extra Python packages. Keep the `assets` folder with the game. macOS and Windows use native audio; Linux uses `aplay`, as the piano already does. If music output is unavailable, the game still runs.

## Network facts

Gameplay uses **TCP 55000**. Automatic nearby discovery uses **UDP 55001**. Hosting listens on `0.0.0.0`; remote clients connect to the host's actual LAN IPv4 address. Solo mode uses `127.0.0.1` and an OS-assigned private TCP port. There is no cloud service, website, database, API key, or mandatory internet connection.

The application is intended for a trusted local network: it uses plain TCP with nickname identification, without TLS or account authentication. Do not describe it as a secured public internet service.

## Automated tests

```sh
python3 self_test.py
python3 -m tests.gui_smoke
python3 -m tests.opening_smoke
python3 -m tests.boss_smoke
```

`tests.boss_smoke` opens two real game windows and plays a boss fight: listen, repeat, team damage, victory, rematch and forfeit.

The first runs unit and actual socket tests. The second opens temporary windows and tests the game flow. The third checks the exact animated artwork, menu hit areas, resizing, keyboard navigation and animation cleanup. The GUI checks require a desktop display and permission for local networking. Keep port UDP 55001 available for the GUI discovery test. These checks do not substitute for demonstrating two physical computers.
