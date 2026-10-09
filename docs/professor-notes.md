# Dup Me 4.0 — professor presentation notes

Keep this document open during the demo. All implementation facts below refer to **v4.0**, not the older v2/v3 folders. See [RUN_AND_TEST.md](../RUN_AND_TEST.md) for exact run steps.

## Opening explanation

“Dup Me is a two-player piano memory game using a client-server architecture and Python sockets. One computer hosts the server and a player; another computer runs only a player client. TCP carries the game messages. UDP helps clients find the host automatically. The server controls the timers, roles, scores, reset and rematch, so both screens share the same game state. We also have an adaptive rule-based AI opponent for single-computer practice.”

## Network and implementation questions

| Professor may ask | Our answer | Where to show it |
|---|---|---|
| What language? | Python 3.10+; tested here with Python 3.12. | `play.py`, `src/` |
| What GUI? | Tkinter and a custom Canvas piano/room. | `src/client/client_ui.py`, `pixel_ui.py` |
| What kind of application? | Native desktop network game; it does not run in a web browser. | Running game windows |
| What architecture? | Central client-server model. Both players connect directly to the server. | `docs/architecture.md` |
| TCP or UDP? | **Both, for different purposes: TCP for gameplay; UDP for nearby discovery.** All notes, scores, turns, rematch/reset notifications and heartbeats use TCP. | `server.py`, `network_client.py`, `discovery.py` |
| Why TCP for the game? | Notes must arrive in order without silently losing a move. TCP provides an ordered reliable byte stream; our framing reconstructs messages from that stream. A disconnected connection still requires recovery. | `src/common/protocol.py` |
| Why UDP for discovery? | A client can broadcast a small discovery request before it knows the server's IP. Lost discovery requests are retried. No game score depends on a UDP packet. | `discover_servers()` |
| Game port? | Default **TCP 55000** on the host. It is an application choice, not a registered Dup Me service. | `src/common/config.py` |
| Discovery port? | **UDP 55001** on the host. Client discovery uses a temporary OS-assigned source port. | `src/common/discovery.py` |
| Client port? | Each TCP client gets an OS-assigned ephemeral source port. Its destination is the server's TCP port. | Operating system socket connection |
| Solo AI port? | A private OS-assigned TCP port, obtained by binding port `0`; both clients connect to `127.0.0.1`. Solo does not advertise on UDP. | `src/client/local_game.py` |
| What is our server IP? | The host computer's current **LAN IPv4 address**, shown in the server dashboard/discovered game. It depends on today's network; we do not hard-code a guessed address in these notes. | Server dashboard |
| What is `0.0.0.0`? | A server listening address meaning all local IPv4 interfaces. It is not an address another computer should connect to. | `SERVER_BIND_HOST` |
| What is `127.0.0.1`? | Loopback: this same computer. A host's local client and solo mode can use it. B cannot use it to reach A. | `LocalGame`, connection-file fallback |
| What is a public IP? | An address for internet routing. It is not needed for two devices communicating on the same local network. We do not provide automatic public internet hosting. | Explain scope |
| IPv4 or IPv6? | The server and discovery sockets are IPv4 (`AF_INET`). | Socket creation |
| DNS? | No required domain name or external DNS service. Discovery uses the UDP reply's source IP. Connection files contain host addresses. An advanced hostname override uses OS name resolution. | `networking.py`, launcher arguments |
| Do players enter IP/port? | No. START discovers the host, or the player loads a file saved by the host. An optional developer CLI override exists, but is not needed for normal play. | Join screen |
| Can multiple nearby hosts be found? | Yes, clients select from discovered hosts on the LAN. Only one responder can own UDP 55001 per host machine; an additional host instance uses a connection file. | Nearby game selector |
| What is discovery information? | Game name, unique server ID, app/version, TCP port, registered player count, configured rounds and the request nonce. The UDP reply source supplies the IP. | `discovery_info()` |
| What is the nonce for? | It associates a response with the current search, rejecting stale/unrelated replies. It is not cryptographic authentication. | `discovery.py` |
| Does a connection file require internet? | No. It is a small JSON file that can be copied over USB. The client tries its addresses and verifies the server's app/version with ping/pong. | Save/Load Connection File |
| How does the server accept clients? | It creates an IPv4 TCP socket, binds, listens and accepts. Separate receive/send workers serve each connection. | `DupMeServer.start()`, `_accept_loop()` |
| Server type? | Custom threaded, authoritative TCP game server. It uses Python's `socket` directly, not Flask, HTTP, WebSocket or a cloud game server. | `src/server/server.py` |
| Dedicated or hosted? | Host and play runs server threads beside the local GUI in one process. Alternatively `server.py` runs a separate server process and `play.py` runs the local client. Both use real TCP connections. | [Separate-process run steps](../RUN_AND_TEST.md#4-alternative-visibly-separate-server-program) |
| How many players? | One active two-player match per server. Additional registered clients wait in the lobby. The server bounds total socket sessions at 16. It is not a multi-room service. | Player selection and session limit |
| Are clients peer-to-peer? | No. A player's move goes to the server, which validates it and sends updates to the players. The laptop-to-laptop network is local, but application messages follow client-server paths. | Architecture diagram |
| Message format? | UTF-8 JSON object prefixed by a four-byte unsigned big-endian payload length. Maximum payload 64 KiB. | `src/common/protocol.py` |
| Why length-prefix JSON? | TCP can split one send into multiple receives or combine several sends. The receiver reads exactly four header bytes, then exactly the declared payload. | `_receive_exact()` |
| What gets sent when pressing a key? | A `pattern_step` or `repeat_step` object containing a note ID and current `turn_id`. The legacy field is named `color`, but now holds note IDs such as `c4` or `fs4`. | Protocol notes |
| Is sound streamed? | No. Only note IDs travel over the network; each client synthesizes and plays its own audio locally. Instrument selection is local. | `src/client/sound.py` |
| How is the GUI kept responsive? | Network tasks run on workers; queues deliver events to Tk's main thread, polled about every 40 ms. Tk widgets are updated on the GUI thread. | `ClientWindow._poll_events()` |
| Who owns the game state? | The server owns roles, patterns, deadlines, points, votes and transitions. Clients display state and submit intended moves. | `GameEngine`, `DupMeServer` |
| How is concurrent access protected? | A re-entrant lock protects server game/session state. Bounded outgoing queues prevent a slow peer from blocking the game controller. | `server.py`, `client_session.py` |
| Why `time.monotonic()`? | Elapsed-time deadlines should not depend on a wall-clock adjustment. | Server controller |
| How do we reject late/invalid input? | Server checks registered session, current phase token, role, note ID, capacity and deadline. A client cannot supply its own score. | `_pattern_step_locked()`, `_repeat_step_locked()` |
| Why a turn token? | Each phase has a fresh ID. A delayed move from the old turn is rejected, even if it arrives after a role change/reset. Missing tokens are rejected too. | `_send_round_start_locked()` |
| How are users identified? | Each connection gets a random player ID; users choose a non-empty nickname up to 20 characters. Duplicate nicknames are rejected case-insensitively. | `ClientSession`, `validation.py` |
| What is the online count? | The number of successfully registered players, including waiting players. Diagnostic pings and connections still awaiting nickname registration are not displayed as players. | Server count/list |
| What if someone disconnects? | The active match is cancelled, scores clear, membership updates and remaining players return to the lobby. Rejoining creates a new connection; old scores are not restored. | `disconnect()` |
| What if Wi-Fi disappears without a clean close? | Clients send heartbeat pings every 3 seconds. Approximately 15 seconds without incoming traffic triggers timeout; checks/scheduling can add a little delay. The user can restore the network and reconnect. | `test_heartbeat.py` |
| Is it encrypted/authenticated? | No TLS or user accounts. This is a trusted-LAN classroom game with nickname identification, input validation and version checks. | Honest scope statement |
| Database/storage? | Match state is in memory. Only a user-requested connection JSON or CSV report is saved; there is no database or permanent leaderboard. | Export code |
| Dependencies? | Python standard library. Tk must be available. Audio uses local OS playback support (`afplay`, `winsound` or `aplay`). No AI API key. | `requirements.txt`, `sound.py` |
| Does it use cellular data? | Game packets stay between clients/server on the shared local network; there is no game cloud backend. The phone still operates its hotspot according to its OS/carrier settings. | Hotspot test guide |
| Will any hotspot work? | Only if both computers can communicate over that hotspot. Discovery needs UDP broadcast; TCP still must be reachable. A file helps when only discovery is blocked. Actual hardware must be tested. | [Hotspot instructions](../RUN_AND_TEST.md#5-does-it-work-on-a-cellular-hotspot) |
| What if computers use separate networks? | This release does not provide NAT traversal, port forwarding setup, VPN provisioning or relay servers. Use a shared LAN for the required demo. | Project scope |

Python's socket documentation explains the IPv4 address/port interface and OS-dependent networking behavior. [Python socket documentation](https://docs.python.org/3/library/socket.html)

## Game questions

| Question | Answer |
|---|---|
| What is the basic loop? | Random creator → create for 10 seconds → opponent repeats within 20 seconds → swap roles → repeat for round two → results → both vote for rematch. |
| How many keys? | 17 chromatic notes C4–E5. White keys `Z X C V B N M , . /`; black keys `S D G H J L ;`. Both keyboard and mouse are supported. |
| Does holding a key create many notes? | A pressed-key/release guard stops keyboard auto-repeat from flooding moves. |
| How many rounds? | Standard is exactly 2. Extended mode offers 4/6/8/10/12; the host selects it separately. |
| Can I submit more than 20 creation notes? | No. Both client and server enforce the cap. The creation timer still runs for the full 10 seconds. |
| Does repetition always last 20 seconds? | It is a 20-second allowance. If all positions have been answered, the server can finish early. |
| What if the creator does nothing? | The empty pattern stays empty and yields zero points. The server does not invent a note on the creator's behalf. |
| Exactly how is scoring calculated? | Compare expected and actual notes at each index. One point for equality; zero for a wrong or missing position. Correct note in the wrong position does not earn a point. |
| Example? | Expected `C4 D4 E4`, answered `C4 E4 E4` → positions 1 and 3 correct → 2 points. |
| Can you undo a live move? | No. Undo/clear belong to offline practice only. |
| When can the opponent see the pattern? | During creation; it is cleared from the client board during repetition. The server reveals it again with the completed round result. |
| Is the hidden pattern cryptographically secret? | No. A modified client could remember the pattern it already received. Server-side scoring blocks score forgery, but this is not a competitive anti-cheat system. |
| Result labels? | Explicit WIN or LOST; ties show DRAW. Both final scores and REMATCH appear. |
| What starts a rematch? | Votes from both active players. Duplicate votes do not count twice. Previous winner starts; draw chooses randomly. Scores start from zero. |
| What does Reset do? | Clears game data, scores, votes and prior winner, keeps connected users and selected mode/round count, then immediately starts a fresh match if two players remain. |
| What does report export do? | Saves expected/actual notes and correctness per position, plus final scores, to a CSV chosen by the user. The detailed review is only available after a match. |

## AI explanation

| Topic | Accurate explanation |
|---|---|
| Feature name | Adaptive DupBot opponent |
| AI type | Explainable rule-based adaptive game AI; no trained neural model, LLM, or remote API |
| Does it use the network? | Yes. It uses the same `NetworkClient`, version handshake and TCP move messages as a human. It does not read the server's private memory. |
| Creator behavior | Generates a pattern; easier level restricts the note palette and shortens the sequence. |
| Repeater behavior | Remembers broadcast pattern events, then simulates imperfect recall using difficulty-dependent accuracy. |
| What is observed? | Human positional accuracy and the last three bot match results. Missed notes and longest pattern are recorded for explanation. |
| When does difficulty change? | After a match, before later play/rematches. Strong human accuracy (at least 85%) or repeated bot losses can raise the level; accuracy below 60% or repeated bot wins can lower it. Strong-human rule has precedence if signals conflict. |
| Easy | Creates 3–5 notes; simulated recall accuracy 60–70%; 0.75-second inter-note delay. |
| Medium | Creates 5–8 notes; accuracy 75–85%; 0.50-second delay. |
| Hard | Creates 8–12 notes; accuracy 90–100%; 0.30-second delay. |
| Does it train/save a model? | No. Adaptation is in-memory for the bot session. Restarting starts from the selected level. |
| How do we prove it? | Run Play with AI and show terminal explanations; `tests/test_ai.py` verifies increasing/decreasing difficulty, and integration tests complete AI matches/rematches through TCP. |
| What should we not claim? | Do not call it deep learning, an LLM, or a trained predictive model. The professor decides whether this satisfies their AI category. |

## A short demo script

1. Show **two physical computers**. Explain that A runs the server plus player and B runs only a player.
2. Start a standard match through discovery. Show **Welcome**, names and **Online clients: 2**.
3. Creator enters a short memorable sequence. Show the opponent can watch it during the full creation countdown.
4. Repeater intentionally makes one wrong move; explain positional scoring. Show roles switch in round two.
5. Show WIN/LOST and both scores. Open the completed-match review if useful.
6. Click REMATCH on one computer first; show it waiting. Click the second; show the previous winner creating first.
7. Earn a point, then press **RESTART MATCH** on A's dashboard. Show scores clear and round one restarts.
8. If time allows, show AI play, instrument selection, extended mode and the report export as extras.

For a progress presentation: “The identified fundamental gaps are implemented. Sixty-one automated tests and a two-client GUI test passed locally. We are validating the actual two-computer network setup and collecting feedback on extras and design.” Once you really finish the physical checklist, replace the last sentence with your actual test result; do not claim a test you have not run.
