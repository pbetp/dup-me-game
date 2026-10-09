# Protocol — Dup Me 4.0

## TCP framing

Each message is a four-byte unsigned network-order (big-endian) payload length followed by one UTF-8 JSON object. Maximum payload: 64 KiB. The receiver loops until the exact header/payload lengths are read; one `recv` is not assumed to equal one message.

| Type | Direction | Purpose |
|---|---|---|
| `join` | Client → server | Register nickname and version `4.0` |
| `welcome` | Server → client | Confirm ID, nickname, version, total rounds |
| `player_list` | Server → clients | Registered users and match membership |
| `match_start` | Server → active players | Players/scores, first creator and total rounds |
| `round_start` | Server → active players | Phase, roles, duration, fresh turn ID, count, scores |
| `pattern_step` | Creator → server | Note ID and turn ID |
| `pattern_update` | Server → active players | Accepted creation note, length and round |
| `repeat_step` | Repeater → server | Answer note and turn ID |
| `repeat_feedback` | Server → active players | Position correctness, answered count and scores |
| `timer_update` | Server → active players | Remaining integer seconds |
| `round_result` | Server → active players | Original pattern, answers, points, repeater and scores |
| `match_result` | Server → player | Win/loss/draw, winner ID and both scores |
| `rematch_vote` | Player → server | Vote once for a rematch |
| `rematch_status` | Server → active players | Votes received/needed |
| `game_reset` | Server → clients | Cancel current game and return to lobby |
| `player_left` | Server → clients | Membership/disconnect notice |
| `error` | Server → client | Rejected action and explanation |
| `ping` / `pong` | Client ↔ server | App/version diagnostic and periodic heartbeat |

Example (JSON body, before framing):

```json
{"type":"pattern_step","color":"fs4","turn_id":"CURRENT_PHASE_ID"}
```

The legacy `color` field holds one of these note IDs:
`c4 cs4 d4 ds4 e4 f4 fs4 g4 gs4 a4 as4 b4 c5 cs5 d5 ds5 e5`.

All moves require the current `turn_id`; missing/stale IDs are rejected. Server also checks role, phase, note validity, count and deadline. The client cannot set its score. Joining clients cannot override the host's `total_rounds`. Instrument choice is a local listening preference; audio bytes are never sent.

A diagnostic ping gets `pong` with `app: "Dup Me"` and `version: "4.0"` without becoming a registered player. Live clients ping every 3 seconds; approximately 15 seconds without traffic times out the connection. Unregistered sockets expire after 10 seconds. Outgoing queues are bounded (client 128, server session 256); a stalled peer is closed rather than blocking the controller.

## UDP discovery

LAN hosts listen on UDP 55001. Clients send a small JSON `dupme_discover` request with a random 32-character nonce to broadcast and loopback addresses, retrying during a roughly 1.5-second search. A `dupme_server` reply echoes the nonce and includes app, version, server ID, name, TCP port, registered-player count and round count. The client takes the IP from the reply's source, deduplicates by server ID, and prefers a LAN reply over loopback.

Discovery does not register a player or carry gameplay. It is a convenience on a trusted local network, not authentication. If UDP is blocked, the host can export a connection JSON file; loading it validates the shape/version, tries its addresses, and checks TCP ping/pong before offering the endpoint.
