"""Optional looping soundtrack, independent of the piano note player.

Uses system audio on macOS/Windows and the existing aplay dependency on Linux.
The bundled PCM WAV has its ending crossfaded into its beginning in advance.
No Python audio packages, internet connection, or external converter are needed.
"""

from __future__ import annotations

import array
import ctypes
import shutil
import subprocess
import sys
import threading
import wave
from pathlib import Path

MUSIC_PATH = Path(__file__).resolve().parents[2] / "assets" / "music" / "arrival_at_zenith_loop.wav"


class _MacPlayer:
    def __init__(self, path: Path) -> None:
        self._appkit = ctypes.CDLL("/System/Library/Frameworks/AppKit.framework/AppKit")
        self._objc = ctypes.CDLL("/usr/lib/libobjc.A.dylib")
        self._objc.objc_getClass.argtypes = [ctypes.c_char_p]
        self._objc.objc_getClass.restype = ctypes.c_void_p
        self._objc.sel_registerName.argtypes = [ctypes.c_char_p]
        self._objc.sel_registerName.restype = ctypes.c_void_p
        self._methods = {}
        pointer = ctypes.c_void_p
        pool = self._call(self._objc.objc_getClass(b"NSAutoreleasePool"), "alloc", pointer)
        pool = self._call(pool, "init", pointer)
        name = self._call(self._objc.objc_getClass(b"NSString"), "alloc", pointer)
        name = self._call(name, "initWithUTF8String:", pointer, (ctypes.c_char_p,),
                          str(path).encode("utf-8"))
        try:
            sound = self._call(self._objc.objc_getClass(b"NSSound"), "alloc", pointer)
            self._sound = self._call(sound, "initWithContentsOfFile:byReference:", pointer,
                                     (pointer, ctypes.c_bool), name, False)
            if not self._sound:
                raise OSError("Could not load the background music")
            self._call(self._sound, "setLoops:", None, (ctypes.c_bool,), True)
        finally:
            self._call(name, "release", None)
            self._call(pool, "drain", None)

    def _call(self, obj, selector, result, arguments=(), *values):
        key = (selector, result, arguments)
        if key not in self._methods:
            signature = ctypes.CFUNCTYPE(result, ctypes.c_void_p, ctypes.c_void_p, *arguments)
            self._methods[key] = signature(("objc_msgSend", self._objc))
        return self._methods[key](obj, self._objc.sel_registerName(selector.encode()), *values)

    def start(self) -> None:
        if not self._call(self._sound, "play", ctypes.c_bool):
            raise OSError("Background music output unavailable")

    def set_gain(self, gain: float) -> None:
        self._call(self._sound, "setVolume:", None, (ctypes.c_float,), gain)

    def close(self) -> None:
        if self._sound:
            self._call(self._sound, "stop", ctypes.c_bool)
            self._call(self._sound, "release", None)
            self._sound = None


class _WindowsPlayer:
    def __init__(self, path: Path) -> None:
        self._winmm = ctypes.WinDLL("winmm")
        self._winmm.mciSendStringW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p,
                                               ctypes.c_uint, ctypes.c_void_p]
        self._winmm.mciSendStringW.restype = ctypes.c_uint
        self._alias = f"dup_me_music_{id(self)}"
        self._opened = False
        # A separate MCI device can mix with winsound piano notes. The digital
        # media driver supports native repeat and device-local volume changes.
        self._command(f'open "{path}" type mpegvideo alias {self._alias}')
        self._opened = True

    def _command(self, command: str) -> None:
        error = self._winmm.mciSendStringW(command, None, 0, None)
        if error:
            raise OSError(f"Background music device error {error}")

    def start(self) -> None:
        self._command(f"play {self._alias} repeat")

    def set_gain(self, gain: float) -> None:
        self._command(f"setaudio {self._alias} volume to {round(gain * 1000)}")

    def close(self) -> None:
        if self._opened:
            self._winmm.mciSendStringW(f"close {self._alias}", None, 0, None)
            self._opened = False


class _LinuxPlayer:
    def __init__(self, path: Path) -> None:
        self._command = shutil.which("aplay")
        if not self._command:
            raise OSError("Background music needs aplay on Linux")
        self._path = path
        with wave.open(str(path), "rb") as track:
            if track.getsampwidth() != 2 or not track.getnframes():
                raise OSError("Background music must be a nonempty 16-bit PCM WAV")
            self._rate, self._channels = track.getframerate(), track.getnchannels()
        self._gain = 0.0
        self._stop = threading.Event()
        self._process = None
        self._thread = None
        self.error = ""

    def start(self) -> None:
        self._process = subprocess.Popen(
            [self._command, "-q", "-t", "raw", "-f", "S16_LE", "-r", str(self._rate),
             "-c", str(self._channels), "--buffer-size=4096", "--period-size=1024"],
            stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            bufsize=0,
        )
        self._thread = threading.Thread(target=self._stream, name="dup-me-music", daemon=True)
        self._thread.start()

    def _stream(self) -> None:
        try:
            with wave.open(str(self._path), "rb") as track:
                while not self._stop.is_set():
                    data = track.readframes(1024)
                    if not data:
                        track.rewind()
                        continue
                    gain = self._gain
                    if gain == 0:
                        data = bytes(len(data))
                    elif gain != 1:
                        samples = array.array("h", data)
                        if sys.byteorder != "little":
                            samples.byteswap()
                        samples = array.array("h", (round(sample * gain) for sample in samples))
                        if sys.byteorder != "little":
                            samples.byteswap()
                        data = samples.tobytes()
                    pending = memoryview(data)
                    while pending and not self._stop.is_set():
                        written = self._process.stdin.write(pending)
                        if not written:
                            raise OSError("Background audio output stopped")
                        pending = pending[written:]
        except (OSError, ValueError, wave.Error) as exc:
            if not self._stop.is_set():
                self.error = str(exc)

    def set_gain(self, gain: float) -> None:
        self._gain = gain

    def close(self) -> None:
        self._stop.set()
        if self._process:
            if self._process.poll() is None:
                self._process.terminate()
            try:
                self._process.wait(timeout=0.5)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait()
        if self._thread:
            self._thread.join(timeout=1)
        if self._process and self._process.stdin:
            self._process.stdin.close()


def _make_player(path: Path):
    if sys.platform == "darwin":
        return _MacPlayer(path)
    if sys.platform == "win32":
        return _WindowsPlayer(path)
    return _LinuxPlayer(path)


class BackgroundMusic:
    def __init__(self, path: Path = MUSIC_PATH) -> None:
        self.path = Path(path).resolve()
        self.volume = 18
        self.muted = False
        self.error = ""
        self._player = None
        self._started = False
        self._closed = False
        self._gain = None
        try:
            if not self.path.is_file():
                raise OSError("Background music file is missing")
            self._player = _make_player(self.path)
        except (OSError, ValueError, wave.Error) as exc:
            self.error = str(exc)

    @property
    def available(self) -> bool:
        return self._player is not None and not self._closed and not getattr(self._player, "error", "")

    def _failed(self, exc: Exception) -> None:
        self.error = str(exc)
        self.close()

    def start(self) -> None:
        if not self.available or self._started:
            return
        self._apply_volume()
        if not self.available:
            return
        try:
            self._player.start()
            self._started = True
        except (OSError, ValueError) as exc:
            self._failed(exc)

    def _apply_volume(self) -> None:
        gain = 0.0 if self.muted else self.volume / 100
        if not self.available or gain == self._gain:
            return
        try:
            self._player.set_gain(gain)
            self._gain = gain
        except (OSError, ValueError) as exc:
            self._failed(exc)

    def set_volume(self, value: int) -> None:
        self.volume = max(0, min(100, int(value)))
        self._apply_volume()

    def set_muted(self, muted: bool) -> None:
        self.muted = bool(muted)
        self._apply_volume()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._player:
            try:
                self._player.close()
            except (OSError, ValueError):
                pass
        self._player = None
