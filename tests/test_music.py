"""Soundtrack controls and portable backend contracts, without audio hardware."""
import array
import tempfile
import unittest
import wave
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from src.client.client_ui import ClientWindow
from src.client.music import BackgroundMusic, MUSIC_PATH, _LinuxPlayer, _WindowsPlayer


class MusicTests(unittest.TestCase):
    def setUp(self):
        self.backend = Mock(error="")
        self.factory = patch('src.client.music._make_player', return_value=self.backend)
        self.factory.start()
        self.addCleanup(self.factory.stop)
        self.music = BackgroundMusic()
        self.addCleanup(self.music.close)

    def test_start_is_quiet_and_does_not_restart_on_controls(self):
        self.music.start()
        self.backend.set_gain.assert_called_with(.18)
        self.music.set_volume(25)
        self.music.start()
        self.music.set_muted(True)
        self.backend.set_gain.assert_called_with(0)
        self.music.set_volume(45)
        self.backend.set_gain.assert_called_with(0)
        self.music.set_muted(False)
        self.backend.set_gain.assert_called_with(.45)
        self.backend.start.assert_called_once()

    def test_zero_volume_and_close_are_safe(self):
        self.music.set_volume(-20)
        self.music.start()
        self.backend.set_gain.assert_called_with(0)
        self.music.set_volume(200)
        self.backend.set_gain.assert_called_with(1)
        self.music.close()
        self.music.close()
        self.music.start()
        self.music.set_volume(20)
        self.backend.close.assert_called_once()
        self.backend.start.assert_called_once()
        self.assertFalse(self.music.available)

    def test_missing_file_does_not_interrupt_game(self):
        with tempfile.TemporaryDirectory() as directory:
            missing = BackgroundMusic(Path(directory) / 'missing.wav')
            missing.start()
            missing.set_muted(True)
            missing.close()
            self.assertFalse(missing.available)
            self.assertIn('missing', missing.error)

    def test_output_failure_closes_backend_without_raising(self):
        self.backend.start.side_effect = OSError('device unavailable')
        self.music.start()
        self.assertFalse(self.music.available)
        self.assertIn('unavailable', self.music.error)
        self.backend.close.assert_called_once()

    def test_volume_failure_also_releases_backend(self):
        self.backend.set_gain.side_effect = OSError('device closed')
        self.music.start()
        self.backend.start.assert_not_called()
        self.backend.close.assert_called_once()

    def test_master_mute_and_music_volume_are_independent(self):
        app = ClientWindow.__new__(ClientWindow)
        app.audio = SimpleNamespace(volume=60, muted=False)
        app.music = self.music
        app._refresh_board = Mock()
        app.toggle_mute()
        self.assertTrue(app.audio.muted and self.music.muted)
        app.set_music_volume(30)
        self.assertTrue(app.audio.muted and self.music.muted)
        app.toggle_mute()
        self.assertFalse(app.audio.muted or self.music.muted)
        self.assertEqual(self.music.volume, 30)
        app.set_music_volume(0)
        self.assertEqual(app.audio.volume, 60)

    def test_master_mute_still_works_when_piano_slider_is_zero(self):
        app = ClientWindow.__new__(ClientWindow)
        app.audio = SimpleNamespace(volume=0, muted=False)
        app.music = self.music
        app._refresh_board = Mock()
        app.toggle_mute()
        self.assertTrue(app.music.muted)
        self.assertEqual(app.audio.volume, 0)
        app.toggle_mute()
        self.assertFalse(app.music.muted)
        self.assertEqual(app.audio.volume, 0)


class BundledAudioTests(unittest.TestCase):
    def test_asset_is_two_minute_stereo_pcm_and_has_a_smooth_join(self):
        with wave.open(str(MUSIC_PATH), 'rb') as track:
            self.assertEqual((track.getnchannels(), track.getsampwidth(), track.getframerate()),
                             (2, 2, 44100))
            self.assertEqual(track.getnframes(), 120 * 44100)
            beginning = array.array('h', track.readframes(1))
            track.setpos(track.getnframes() - 1)
            ending = array.array('h', track.readframes(1))
            self.assertLess(max(abs(a-b) for a,b in zip(beginning, ending)), 500)


class NativeBackendTests(unittest.TestCase):
    def test_windows_uses_independent_device_repeat_and_local_volume(self):
        winmm = Mock()
        winmm.mciSendStringW.return_value = 0
        with patch('src.client.music.ctypes.WinDLL', return_value=winmm, create=True):
            player = _WindowsPlayer(Path('C:/Game music/Arrival.wav'))
            player.set_gain(.18)
            player.start()
            player.close()
            player.close()
        commands = [call.args[0] for call in winmm.mciSendStringW.call_args_list]
        self.assertIn('"C:/Game music/Arrival.wav" type mpegvideo', commands[0])
        self.assertIn('volume to 180', commands[1])
        self.assertTrue(commands[2].endswith(' repeat'))
        self.assertEqual(len(commands), 4)

    def test_linux_rewinds_in_one_stream_and_scales_samples(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'tiny.wav'
            with wave.open(str(path), 'wb') as track:
                track.setparams((1, 2, 8000, 0, 'NONE', 'not compressed'))
                track.writeframes(array.array('h', [1000, -1000, 2000, -2000]).tobytes())
            with patch('src.client.music.shutil.which', return_value='/usr/bin/aplay'):
                player = _LinuxPlayer(path)
            player.set_gain(.5)
            chunks = []

            def write(data):
                chunks.append(bytes(data))
                if len(chunks) == 3:
                    player._stop.set()
                return len(data)

            player._process = SimpleNamespace(stdin=SimpleNamespace(write=write))
            player._stream()
            self.assertFalse(player.error)
            self.assertEqual(len(chunks), 3)
            self.assertTrue(all(chunk == chunks[0] for chunk in chunks))
            self.assertEqual(list(array.array('h', chunks[0])), [500, -500, 1000, -1000])


if __name__ == '__main__':
    unittest.main()
