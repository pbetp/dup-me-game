# Animated disco opening — design-only update

This copy uses the exact approved `03-orbit-keyboard-natural-motion-smooth.gif` as its opening artwork. The file has been copied without editing or re-encoding: 1280 × 720, 192 frames, a 9.6-second loop at 20 frames per second.

The five pictured buttons call the original Single Player, Multiplayer, Practice, Settings and Quit actions. Mouse and keyboard navigation work. The complete image is fitted inside the window without stretching or cropping; dark margins accommodate other window shapes. Animation pauses beneath Settings/Help dialogs and while minimized, then resumes. Background music continues independently.

## Run

Extract the whole ZIP. Install the artwork dependency once and start the game:

```sh
python3 -m pip install -r requirements.txt
python3 play.py
```

On Windows, replace `python3` with `py -3`. Keep the `assets` folder with the game. Pillow is used only for animated-image decoding and scaling.

## What changed

- `src/client/opening_screen.py`: opening artwork playback, resizing and menu hit areas.
- `src/client/client_ui.py`: import/hold/clean up that screen and replace `show_menu` presentation. Every other existing method is unchanged.
- `assets/ui/disco-opening.gif`: the exact approved animation.
- `requirements.txt` and setup instructions: the Pillow dependency.
- GUI test helpers: accommodate the new opening layout and use a timed normal event loop for continuous animation.

## Engine preservation

Compared every original file against `dup-me-looping-music.zip`. All server/game-engine, common/protocol/networking and bot files are byte-for-byte unchanged. The game board, local game, practice logic, match reports, note audio, music player and WAV soundtrack are also byte-for-byte unchanged. No gameplay rules, scoring, timing, networking messages or audio behavior were edited.

Original files changed: README.md, RUN_AND_TEST.md, START_HERE.txt, requirements.txt, src/client/client_ui.py, tests/gui_smoke.py, tests/music_smoke.py.

Artwork SHA-256: `b7415801ac388b3a1caa12440c39078d0f60124d61fc1abad14e22f075c6b83e`.

## Verification — 11 October 2026

- All 80 existing unit and socket regression tests passed.
- Opening check passed: exact displayed artwork pixels at 960×700, 1280×800 and 1600×900; all five buttons; keyboard navigation; looping; modal blocking and pause/resume; minimize/resume; disposal of animation callbacks. Playback measured about 19–20 fps on the test Mac.
- Existing full desktop game-flow check passed, including two real local GUI clients, complete matches, scores, rematch, hosting/discovery, practice, settings and return to the menu.
- Existing music check passed: native 120-second soundtrack looping, piano alongside music, screen changes, mute, music volume, settings layout and audio cleanup.
- No Tk callback errors in the completed GUI checks.

Checks ran on macOS with Python 3.12, Tk 8.6 and Pillow 12.3. Windows and Linux were not physically tested here.
