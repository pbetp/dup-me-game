"""Small, optional note player using only Python and the operating system.

Audio failure never interrupts a match. Generated WAVs live in a private
temporary directory and are removed when the window closes.
"""

from __future__ import annotations

import array
import math
import shutil
import subprocess
import sys
import tempfile
import wave
from pathlib import Path
from src.common.config import INSTRUMENTS, NOTE_FREQUENCIES


class NotePlayer:
    def __init__(self) -> None:
        self.volume = 60
        self.muted = False
        self._instrument = INSTRUMENTS[0]
        self._folder = tempfile.TemporaryDirectory(prefix="dup-me-notes-")
        self._processes: list[subprocess.Popen] = []
        self._winsound = None
        self._command: str | None = None
        if sys.platform == "win32":
            import winsound
            self._winsound = winsound
        else:
            self._command = shutil.which("afplay" if sys.platform == "darwin" else "aplay")

    @property
    def available(self) -> bool:
        return self._winsound is not None or self._command is not None

    @property
    def instrument(self) -> str:
        return self._instrument

    @instrument.setter
    def instrument(self, value: str) -> None:
        if value not in INSTRUMENTS:
            raise ValueError("Unknown instrument")
        self._instrument = value

    def _note_file(self, color: str) -> Path:
        # Quantize volume to keep the temporary cache small.
        level = max(0, min(100, round(self.volume / 5) * 5))
        path = Path(self._folder.name) / f"{self.instrument}-{color}-{level}.wav"
        if path.exists():
            return path
        rate, duration = 22050, 0.65
        frequency = NOTE_FREQUENCIES[color]
        samples = array.array("h")
        count = int(rate * duration)
        for index in range(count):
            t = index / rate
            phase = 2 * math.pi * frequency * t
            attack = min(1.0, t / 0.006)
            release = min(1.0, (duration - t) / 0.12)
            if self.instrument == "Classic Piano":
                # A struck string: upper harmonics fade faster than the fundamental.
                tone = sum(amplitude * math.sin(phase * harmonic) * math.exp(-decay * t)
                           for harmonic, amplitude, decay in ((1, 1, 4), (2, .38, 7), (3, .18, 11), (4, .08, 16)))
                envelope = attack * release
            elif self.instrument == "Synthesizer":
                tone = sum(math.sin(phase * harmonic) / harmonic for harmonic in range(1, 9)) / 1.8
                envelope = min(1.0, t / .018) * math.exp(-1.5 * t) * release
            elif self.instrument == "Electric Piano":
                tone = math.sin(phase + 1.8 * math.exp(-8 * t) * math.sin(2 * phase))
                tone += .22 * math.sin(phase * 3) * math.exp(-10 * t)
                envelope = attack * math.exp(-3 * t) * release
            else:  # Organ: sustained drawbar harmonics and a soft release.
                tone = math.sin(phase) + .45 * math.sin(2 * phase) + .25 * math.sin(3 * phase) + .12 * math.sin(4 * phase)
                envelope = min(1.0, t / .025) * release * .8
            sample = int(tone * envelope * 17000 * level / 100)
            samples.append(max(-32767, min(32767, sample)))
        if sys.byteorder != "little":
            samples.byteswap()
        with wave.open(str(path), "wb") as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(rate)
            output.writeframes(samples.tobytes())
        return path

    def play(self, color: str) -> None:
        if self.muted or self.volume <= 0 or color not in NOTE_FREQUENCIES or not self.available:
            return
        try:
            path = self._note_file(color)
            if self._winsound:
                self._winsound.PlaySound(
                    str(path), self._winsound.SND_FILENAME | self._winsound.SND_ASYNC
                )
            else:
                self._processes = [p for p in self._processes if p.poll() is None]
                if len(self._processes) >= 6:
                    self._processes.pop(0).terminate()
                arguments = [self._command, str(path)]
                if sys.platform != "darwin":
                    arguments.insert(1, "-q")
                self._processes.append(subprocess.Popen(
                    arguments, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                ))
        except (OSError, wave.Error):
            return

    def close(self) -> None:
        if self._winsound:
            self._winsound.PlaySound(None, 0)
        for process in self._processes:
            if process.poll() is None:
                process.terminate()
            try:
                process.wait(timeout=0.3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        self._processes.clear()
        self._folder.cleanup()
