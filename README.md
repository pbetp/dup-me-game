# Dup Me 4.0

A two-player piano memory game built with Python sockets and Tkinter. This release closes the identified rubric gaps and preserves the 17-key piano, four instruments, adaptive opponent, and extended matches. **Use version 4.0 on both computers.**

Start with **[RUN_AND_TEST.md](RUN_AND_TEST.md)**. Open **[docs/professor-notes.md](docs/professor-notes.md)** during your presentation; it contains the network facts, architecture, questions and answers, and demo checklist. **[docs/rubric.md](docs/rubric.md)** maps each marking item to its implementation and evidence. **[TEST_RESULTS.md](TEST_RESULTS.md)** distinguishes automated checks from the physical demo still needed.

## Quick start

Extract the ZIP before running it. Use Python 3.10 or newer with Tkinter (development checks used Python 3.12 on macOS). There are no third-party Python dependencies.

```sh
python3 play.py
```

On Windows, use `py -3 play.py`. In PyCharm or VS Code, open the extracted folder and run `play.py` with a local Python interpreter.

- **One computer:** **SINGLE PLAYER** → enter your nickname → pick AI level → **2 STD** rounds → **START**.
- **Two computers:** connect both to the same network. Both choose **MULTIPLAYER** and enter different nicknames. A picks **HOST A GAME → START HOSTING**; B picks **JOIN A GAME**, which searches automatically, then presses **JOIN**. Nobody types an IP or port.
- If discovery is blocked, A's server dashboard can **Save Connection File**. Transfer that file to B, select **JOIN A GAME → LOAD FILE**, then **JOIN**. This requires an actual reachable TCP connection and does not bypass network isolation.
- **Practice (offline):** **PRACTICE** → pick a level (Easy / Medium / Hard: 3 / 4 / 5 notes to find) and 10, 20 or 30 melodies → **START**. Listen, then play the melody back by ear. Only the first note is shown (and lit on the keyboard), so you find the rest by interval; it is not scored. **Space** replays the melody. Like a typing test, the board shows live **ACC** (exact notes), **PREC** (pitch closeness: one semitone off still scores 92%), **NPM** (correct notes per minute) and **COMBO**, and the results screen adds perfect melodies, best combo, average miss distance and the notes you missed most.
- **Standard** follows the required two rounds. **Extended match** offers 4, 6, 8, 10 or 12 rounds. The joining client follows the host's selection.

HOST A GAME runs a server dashboard inside the game window. Open it with **SERVER DASHBOARD** in the lobby or **SERV** on the game board. It displays the online player count, names, addresses, roles, scores, timer, and activity log. **RESTART MATCH** clears the scores and starts round 1 again immediately; **END MATCH** ends the match now and declares the winner on current scores. **BACK TO GAME** (or Esc) hides it; the server keeps running. Closing the host's main game window stops the server.

## Game rules

The server randomly selects the first creator. Creation lasts 10 seconds, with a maximum of 20 notes; the opponent watches and memorizes. Repetition lasts up to 20 seconds, ending early if every position has been answered. One point is awarded for each correct note at the correct position. Roles swap in round two, then both players see **WIN**, **LOST**, or **DRAW**, and both scores. Both must press **REMATCH**. The previous winner creates first; a draw chooses randomly.

A full pattern does not shorten the creation countdown. An empty pattern remains empty and earns zero points. Restart clears the match and scores and starts round 1 immediately when two players remain. Any player can press **EXIT** on the game board to leave at once: the player who exits always gets **LOST**, the opponent **WIN**, with the scores so far. In offline practice EXIT returns to the main menu.

## Controls and extras

White keys: `Z X C V B N M , . /` · Black keys: `S D G H J L ;`. Mouse clicks work too. The range is chromatic C4–E5.

**SET** selects Classic Piano, Synthesizer, Electric Piano or Organ, volume, mute and key flashes. `F11` toggles fullscreen (some laptops require Fn); `Ctrl+M` toggles mute; `F1` opens help. Offline preview supports undo and clear. Live notes are final. Match results offer a round-by-round review and CSV export; these reveal no extra information during a live turn.

## Network facts

Gameplay uses **TCP 55000**. Automatic nearby discovery uses **UDP 55001**. Hosting listens on `0.0.0.0`; remote clients connect to the host's actual LAN IPv4 address. Solo mode uses `127.0.0.1` and an OS-assigned private TCP port. There is no cloud service, website, database, API key, or mandatory internet connection.

The application is intended for a trusted local network: it uses plain TCP with nickname identification, without TLS or account authentication. Do not describe it as a secured public internet service.

## Automated tests

```sh
python3 self_test.py
python3 -m tests.gui_smoke
```

The first runs unit and actual socket tests. The second opens temporary windows and tests the game flow; it requires a desktop display and permission for local networking. Keep port UDP 55001 available for the GUI discovery test. Neither command substitutes for demonstrating two physical computers.
