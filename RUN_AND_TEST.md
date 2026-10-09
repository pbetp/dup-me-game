# Dup Me 4.0 — run and test guide

## 1. Prepare both computers

1. Extract `dup-me-rubric-ready.zip` into a new folder on each computer. Use the same release on both. Do not mix these files with an older copy.
2. Use Python 3.10+ with Tkinter. Open a terminal in the extracted `dup-me-rubric` folder. On macOS, type `python3 --version`; on Windows, `py -3 --version`.
3. Confirm Tkinter opens a small window with `python3 -m tkinter` (Windows: `py -3 -m tkinter`), then close it. Python documents this as a quick installation check. [Python Tkinter documentation](https://docs.python.org/3/library/tkinter.html)
4. Run `python3 play.py` (Windows: `py -3 play.py`). Alternatively, open the whole folder in PyCharm/VS Code, select a local Python interpreter and run `play.py`. No pip installation is needed. Do not run from inside the ZIP.
5. Permit incoming connections for this Python/game on the private demonstration network if the operating system asks. Hosting needs TCP 55000 and discovery needs UDP 55001. Keep firewall protection enabled; allow only the required application/ports.

Python installers: [python.org downloads](https://www.python.org/downloads/). On Linux, Tk may be a separate distribution package (`python3-tk` on Debian/Ubuntu); audio also needs `aplay`. Windows and Linux execution have not been physically tested in this environment.

## 2. One computer with AI

1. Run `play.py`.
2. On the main menu, select **SINGLE PLAYER**.
3. Enter your nickname and choose the starting AI level. (Instrument and volume are under **SETTINGS** on the main menu.)
4. Leave **2 STD** rounds selected for the rubric demonstration.
5. Press **START**. The program starts a private server, your client and DupBot. No separate server script or network address is needed.
6. Follow the role displayed on the board. Creator: play a few notes during the 10-second countdown. Repeater: watch first, then repeat when your 20-second turn begins.
7. Play both rounds. Check both scores and the result. Press **REMATCH**; the bot votes automatically.

AI play is useful for rehearsal and the AI feature demonstration. The fundamental two-computer requirement still needs two human clients on two physical computers.

## 3. Two physical computers — simplest setup

| Step | Computer A: host and player | Computer B: player only |
|---|---|---|
| Network | Connect to the same Wi-Fi or phone hotspot as B | Connect to the same Wi-Fi or hotspot as A |
| Open | Run `play.py` | Run `play.py` |
| Menu | **MULTIPLAYER** | **MULTIPLAYER** |
| Name | Enter one nickname | Enter a different nickname |
| Mode | **HOST A GAME** | **JOIN A GAME** (after A's lobby appears) |
| Rules | **2 STD** rounds | Follows the host |
| Start | Press **START HOSTING** | The game list fills automatically; select A's game and press **JOIN** |
| Connection | Lobby appears; open **SERVER DASHBOARD** — count should be 1 | Press **FIND GAMES** to search again if the list is empty |
| Joined | Dashboard count becomes 2; both names appear | Welcome and game appear; no IP/port entry |
| Play | Create/repeat as instructed | Create/repeat as instructed |

Keep A's main game window open throughout. Both clients communicate with the server; they do not send game messages directly to each other. Do **not** also run `server.py` while using **HOST A GAME**.

### If FIND GAMES finds nothing

1. On A, open the server dashboard and select **Save Connection File**. Save `dup-me-connection.json`.
2. Transfer that file to B using a USB drive or your usual file-transfer method.
3. On B, select **MULTIPLAYER → JOIN A GAME → LOAD FILE** and choose the file. Wait for “Host found,” then press **JOIN**.
4. Save a fresh file after changing networks or when A's IP changes. The file contains connection information, not executable code.

If TCP itself is blocked, a connection file cannot fix it. Check that A is still hosting, both computers are on the same network, Python has local network/firewall permission, and the network permits devices to communicate. Avoid guest networks with client isolation. Disable or reconfigure a VPN only if it is interfering with your own demonstration network.

## 4. Alternative: visibly separate server program

This is useful when the professor wants to see separate server and client programs/processes.

1. On A, run `python3 server.py` in one terminal. Leave the server dashboard open.
2. On A, run `python3 play.py` in another terminal. Select **MULTIPLAYER**, enter a nickname, then **JOIN A GAME → JOIN**.
3. On B, run `python3 play.py`. Select **MULTIPLAYER**, use a different nickname, then **JOIN A GAME → JOIN**.
4. Demonstrate the count/list/reset on A's separate server dashboard.

Windows substitutes `py -3` for `python3`. In this setup **both client windows select Join**, since `server.py` already owns the listening port. Do not use `--headless` for the rubric demo because it hides the required server UI.

## 5. Does it work on a cellular hotspot?

**It can, when both laptops join the same phone hotspot and the hotspot permits local device-to-device traffic.** The phone supplies the network; A still runs the server. The game does not contact an internet game service. Hotspot hardware, settings and firewall behavior determine whether local discovery and TCP are allowed; this release has not been tested on your actual phone.

For an iPhone, enable Personal Hotspot and allow the laptops to join, following [Apple's Personal Hotspot instructions](https://support.apple.com/en-us/111785). Those instructions establish hotspot access; they do not guarantee this game's peer-to-peer reachability. Test the actual two laptops beforehand. If UDP discovery is blocked but TCP is allowed, use the connection-file fallback. If all peer traffic is blocked, use a different shared Wi-Fi/router.

Two separate phone hotspots are two different networks. This release does not provide cloud relay, NAT traversal or automatic internet hosting. Keep the phone powered and prevent it from disabling the hotspot during the demo.

## 6. Automated verification

Run from the extracted folder, with no other Dup Me host using discovery port 55001:

```sh
python3 self_test.py
python3 -m tests.gui_smoke
```

Windows:

```powershell
py -3 self_test.py
py -3 -m tests.gui_smoke
```

Expected: the first reports **61 tests, OK**; the second prints **PASS** and closes its temporary windows. Some integration tests intentionally accelerate timers; separate checks verify the production 10/20-second configuration and that a full pattern keeps the creation deadline. The GUI test uses two client windows on one machine; it does not prove physical Wi-Fi/hotspot connectivity.

## 7. Physical demo acceptance checklist

Fill this in after testing the actual machines; these boxes are intentionally not pre-checked.

| Check | Expected evidence | Result |
|---|---|---|
| A hosts, B only runs client | Two physical computers connected | ☐ |
| No address typing | B joins through discovery or connection file | ☐ |
| Nicknames/welcome | Each screen welcomes the correct name | ☐ |
| Server membership | Count 2 and correct two names/addresses | ☐ |
| Creation | 10-second timer; opponent sees and hears notes | ☐ |
| Repetition | Pattern hidden; 20-second timer, or completion ends the turn | ☐ |
| Ordered scoring | Deliberately enter one wrong position; that position earns no point | ☐ |
| Round two | Roles swap; standard game ends after round two | ☐ |
| Results | Both names/scores and WIN/LOST (or DRAW); REMATCH button | ☐ |
| Both votes | One vote waits; second starts the rematch | ☐ |
| Winner starts | Previous winner is creator in rematch round one | ☐ |
| Restart | During a scored game, RESTART MATCH clears scores and round 1 starts again immediately | ☐ |
| End match | END MATCH shows results for both players, decided by current scores | ☐ |
| Exit | A player presses EXIT mid-match: they see LOST, the opponent sees WIN | ☐ |
| Disconnect | Close B; A returns to lobby and count falls to 1; rejoin works | ☐ |
| AI and extras | Rehearse solo, instrument change, extended mode, review/export | ☐ |
| Hotspot | Repeat the connection and full match on the actual phone, if using it | ☐ |

## 8. Common fixes

| Symptom | Action |
|---|---|
| `python3`/`py` not found | Install Python or choose the installed interpreter in your IDE. On some Windows systems use `python` instead of `py -3`. |
| Tkinter is missing | Install a Python distribution with Tk support; verify with `-m tkinter`. |
| “Could not host” / address already in use | Close the older host/server, or Join the existing host. Run only one host per machine on TCP 55000. |
| No host found | Start A first, use Find Games again, check UDP 55001, or load A's connection file. |
| Connection refused | The selected/saved server is no longer listening. Restart A and find it again. |
| Connection timeout | Check same network, incoming Python/TCP permission, VPN and device isolation. |
| Version mismatch | Extract the same v4.0 ZIP on both machines and restart both. |
| Nickname already connected | Use a different nickname or close the old client; stale connections expire. |
| Network stopped responding | Restore the network, return to Join, Find Games and reconnect. Scores from a cancelled match are cleared. |
| Notes are silent | Turn up system/game volume, unmute, use SET → TEST SOUND. Visual play still works without audio. |
| Display feels crowded | Maximize the window or use F11/Fn+F11; minimum client size is 960×700. |

## 9. Optional developer commands

Regular players do not need these. `--host` is an advanced preconfigured override, not a required input in the UI.

```sh
python3 play.py --mode solo --nickname Joji
python3 play.py --mode host --nickname Joji
python3 play.py --mode host --rounds 6
python3 server.py --port 55000
python3 check_connection.py HOST_LAN_IP --port 55000
```

The diagnostic `HOST_LAN_IP` is a placeholder shown in the dashboard; do not type that literal text. The check sends a ping, verifies Dup Me v4.0, and does not register a player. Stop command-line programs with Ctrl+C; close game windows normally.
