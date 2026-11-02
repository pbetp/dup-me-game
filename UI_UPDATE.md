# DUP ME 4.3 — animated rooftop multiplayer lounge

This update implements the approved Host a Game, Join a Game, host waiting-room, and client waiting-room layouts.

## Run the game

Extract the entire ZIP into a new folder. Keep the `assets` folder beside `play.py`. Use this same updated release on both computers.

macOS/Linux:

```sh
python3 -m pip install -r requirements.txt
python3 play.py
```

Windows:

```sh
py -3 -m pip install -r requirements.txt
py -3 play.py
```

In PyCharm, open this extracted folder and run `play.py`. Use a working local Python environment; the archive intentionally excludes the old computer-specific virtual environment.

## Host and join

1. Both players choose Multiplayer, enter different nicknames, and choose the same game mode.
2. The host chooses Host a Game, selects rounds for 1v1, and presses Start Hosting.
3. The client chooses Join a Game, selects the discovered room, and presses Join Game. If needed, the host can save a connection file directly from the waiting room and the client can load it.
4. Both players remain in the waiting room. The client presses I'm Ready. The host's Start Game button activates.
5. The host presses Start Game. The existing match begins.

The client can cancel readiness before the host starts. Join stays disabled when there is no valid selected room or the selected room is full. Search and connection operations run without blocking the interface.

The host can open Dashboard from the waiting room. Reset Room clears scores, returns both players to the waiting room, and asks the client to mark ready again. Closing the room stops its local server. Leaving a client room returns to game discovery.

## Artwork and motion

The home, single-player, multiplayer-menu, practice, settings and boss artwork assets are preserved. In particular, the original opening GIF and its playback code retain the spinning disco ball, moving piano keys, flashing pads and stars.

The revised lounge uses the exact original `multiplayer-rooftop-jam.gif` at its original 192-frame timing, including both musicians, the disco ball, piano keys, neon trails, skyline and DUP ME logo. The detailed painted neon border stays intact; only the panel interior is replaced with live controls. All four pages share this same animated asset. Round choices use two rows and player cards stack vertically so neither musician is covered. The four approved mockups are included in `docs/design-reference/`. The controls, room list, round choices, player names and ready states are live. Host actions are cyan; client actions are pink; waiting messages are gold.

Only the current decoded animation frame is retained, avoiding a large frame cache. Every new page fits the window with the same 16:9 proportions. It pauses background motion while hidden or behind its modal controls, resumes when visible, and stops timers when the page closes. Tab and Shift-Tab move focus; Enter or Space activates the focused control. Arrow keys and scrolling navigate discovered rooms.

## Boss piano visibility fix

The boss fight piano now remains visible while listening, waiting, and viewing results. Its old disabled-state black stipple cover could appear as an opaque rectangle on macOS. That cover has been removed; input remains blocked until the repeat phase, and the usual note flashes still work.

## Compatibility

The protocol version is 4.3 so older clients without the Ready control cannot accidentally join a manual waiting room. Solo play and separately launched standalone servers still start automatically. Scoring, musical notes, instruments, match roles, practice, and explicit rematch voting retain their existing behavior.

Local automated checks exercise host/client connections on one computer. Wi-Fi discovery between two physical computers still depends on their network and firewall settings.
