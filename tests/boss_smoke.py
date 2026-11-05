"""Opt-in real Tk windows and sockets for the co-op boss fight: python -m tests.boss_smoke."""
import tkinter as tk

from src.client.client_ui import ClientWindow
from tests.gui_smoke import check_choices, drain, free_port, layout, pump

root = tk.Tk()
errors = []
root.report_callback_exception = lambda *args: errors.append(args)


app = ClientWindow(root, nickname="Joji", port=free_port())
app.audio.muted = True
for geometry in ("960x700", "1280x800"):
    root.geometry(geometry)
    app.show_multiplayer()
    drain(root)
    layout(root, app)
    check_choices(root, app.container)
app.play_mode_var.set("boss")
drain(root)
app._multiplayer_next("host")
assert app.current_screen == "host" and app.play_mode == "boss"
layout(root, app)
app.connect()
pump(root, lambda: app.current_screen == "lobby")

friend_root = tk.Toplevel(root)
friend_root.geometry("1280x800+40+40")
friend = ClientWindow(friend_root, nickname="Ally")
friend.audio.muted = True
friend.show_multiplayer()
friend.play_mode_var.set("boss")
friend._multiplayer_next("join")
pump(root, lambda: friend.servers and not friend.connect_button.instate(["disabled"]))
friend.connect()
pump(root, lambda: app.current_screen == friend.current_screen == "lobby"
     and len(app.players) == len(friend.players) == 2)
assert app.start_lobby_button.instate(["disabled"])
friend.toggle_lobby_ready()
pump(root, lambda: app.start_lobby_button.instate(["!disabled"]))
app.start_lobby_match()
pump(root, lambda: app.current_screen == friend.current_screen == "boss_game")
assert friend.play_mode == "boss"

boss = app.boss_state
pump(root, lambda: boss.phase == "show" and boss.shown >= 3, 8)
pump(root, lambda: boss.phase == "show" and boss.shown == len(boss.notes[boss.me]), 8)
mine = list(boss.notes[boss.me])
theirs = list(friend.boss_state.notes[friend.boss_state.me])
pump(root, lambda: boss.phase == friend.boss_state.phase == "repeat", 8)
assert boss.notes == {} and boss.can_play
wrong = "e5" if mine[1] != "e5" else "c4"
for note in (mine[0], wrong):
    app.press_color(note)
for note in theirs[:2]:
    friend.press_color(note)
pump(root, lambda: len(boss.marks.get(boss.me, [])) == 2 and len(boss.marks.get(friend.player_id, [])) == 2)
for note in mine[2:]:
    app.press_color(note)
for note in theirs[2:]:
    friend.press_color(note)
pump(root, lambda: boss.phase == "result")
assert boss.team_damage == len(mine) - 1 + len(theirs), boss.team_damage
assert boss.hp_lost[boss.me] == 1

# Host FORCE RESET: the fight restarts at phrase 1 with full HP, same connections.
assert "reset" in app.board.actions and "reset" not in friend.board.actions
app.board.actions["reset"]()
pump(root, lambda: app.boss_state.phrase == friend.boss_state.phrase == 1
     and app.boss_state.boss_hp == app.boss_state.boss_max, 8)
boss = app.boss_state
assert "restarted" in app.boss_state.status and "restarted" in friend.boss_state.status
pump(root, lambda: boss.phase == "show" and boss.shown == len(boss.notes[boss.me]), 8)
pump(root, lambda: boss.phase == friend.boss_state.phase == "repeat", 8)
for player in (app, friend):
    for note in app.local_game.server.game.phrases[player.player_id]:
        player.press_color(note)
pump(root, lambda: boss.phase == "result")

# Jump ahead: leave the boss on 2 HP and finish it in the next phrase.
server = app.local_game.server
with server.lock:
    server.game.boss_hp = 2
pump(root, lambda: boss.phase == "repeat" and boss.phrase == 2, 10)
mine = server.game.phrases[app.player_id]
for note in mine[:2]:
    app.press_color(note)
pump(root, lambda: app.current_screen == friend.current_screen == "results", 8)
assert app.result_texts[0] == "VICTORY"
app.request_rematch()
friend.request_rematch()
pump(root, lambda: app.current_screen == "boss_game" and boss is not app.boss_state and app.boss_state.phase == "show", 8)
friend.force_exit()
pump(root, lambda: app.current_screen == "results", 8)
assert app.result_texts[0] == "DEFEAT"
friend.close()
app.close()
assert not errors, errors
print("Boss fight GUI smoke test passed.")
