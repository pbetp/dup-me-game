# Arrival at Zenith

`arrival_at_zenith_loop.wav` is derived from the user's supplied `Arrival_at_Zenith.mp3`.

- Duration: exactly 120.000 seconds.
- Format: stereo, 44,100 Hz, 16-bit PCM WAV.
- A small tempo adjustment (approximately 2.6% slower, with pitch preserved) makes room for a four-second equal-power crossfade while keeping the loop exactly two minutes long.
- The fade-out is blended with the beginning, and the file starts just after that overlap. This removes the original silent tail from the repeat point.
- Peak level is limited to 0.98 full scale before PCM export. The in-game music volume is independently adjustable and starts at 18%.

The game loads this file relative to its own source folder, so launching from a different working directory is supported. No audio conversion tools are required to run the game.
