# Moroccan Dama — Private Online Multiplayer

A small, mobile-first web game for two friends to play Moroccan Dama (الضامة) online. One player creates a private room and shares a link or room code with the other player. Both players open the same room from their own devices and play in real time.

> **Product principle:** build the game first. No accounts, public matchmaking, leaderboards, ads, chat, AI opponent, or unnecessary platform features.

---

## 1. Product goal

Build a responsive website that lets exactly two people play a private Dama match over the internet. It must work on desktop browsers, Android browsers, and iPhone browsers.

### Main user journey

1. Player A opens the website.
2. Player A enters a display name and selects **Create private game**.
3. The server creates a room and returns a shareable invitation URL and short room code.
4. Player A shares the URL or code with Player B (WhatsApp, Messenger, etc.). Sharing itself is handled by the browser's native share feature where available, with a copy-link fallback.
5. Player B opens the URL or enters the code, chooses a display name, and joins the room.
6. Once both players are connected, the match starts.
7. Both browsers receive every accepted move in real time.
8. The game ends when a player wins or resigns. Both players can request a rematch.

### MVP scope

**Must have**

- Create a private room.
- Join a room through an invite link or room code.
- Exactly two player slots; reject a third player.
- Assign one side/color to each player.
- Real-time state synchronization using WebSockets.
- Server-authoritative game rules and move validation.
- Responsive, touch-friendly 8×8 game board.
- Selection, legal-move hints, captures, multi-captures, king promotion, turn indicator, captured-piece counts, and win state.
- Reconnection after a temporary network interruption or page refresh.
- Resign and request a rematch.
- Clear waiting-room, connection, error, and game-over states.
- Basic automated tests for the rules engine and room/multiplayer behavior.

**Do not build in the MVP**

- User accounts, passwords, profiles, or OAuth.
- Public room browser, lobby, matchmaking, or spectators.
- Chat, voice, video, friends, notifications, or social feed.
- AI/bot opponent or difficulty levels.
- Rankings, ratings, tournaments, statistics, or persistent match history.
- Payments, ads, or analytics trackers.
- Database-backed persistence unless a concrete requirement appears. The MVP may keep rooms in memory and clearly document that active rooms disappear when the server restarts.

---

## 2. Game rules and variant handling

The game is intended to be **Moroccan Dama**, not International Draughts. Do not accidentally implement the 10×10 International Draughts rules or the standard American Checkers rules.

### Baseline rules for the first implementation

Use the following as the initial rules profile. Keep rules in a dedicated engine/module rather than embedding them in UI code.

| Rule | Initial behavior |
|---|---|
| Board | 8×8, with pieces on the 32 playable dark squares |
| Starting pieces | 12 men per player, occupying the three nearest rows of playable squares |
| First turn | Light/white side starts |
| Men — normal move | One square diagonally forward to an empty playable square |
| Men — capture | Jump an adjacent opposing man diagonally forward into the empty square immediately beyond it; men do not capture backward |
| Kings / Dama | A promoted piece becomes a flying king: it may move any unobstructed distance diagonally in any direction |
| King capture | A flying king can capture an opposing piece along a diagonal and land on a legal empty square beyond it; implement this as a complete legal capture sequence, not as separate unvalidated UI steps |
| Mandatory capture | If at least one capture is available, a non-capturing move is illegal |
| Multiple captures | A capture turn continues for as long as another capture is available with the same piece |
| Maximum capture | When more than one complete capture sequence is available, prefer/require a sequence that captures the greatest number of pieces |
| Equal capture count | Initial profile: do not add a king-count tie-break; equal-length maximum-capture sequences remain legal. Keep this configurable because some Moroccan implementations describe an additional preference for capturing Damas/kings |
| Captured pieces | Track captured pieces accurately and prevent the same piece from being captured twice in a single sequence. Prefer removing captured pieces from the board when the complete turn is committed, while treating them as unavailable to further jumps in that sequence |
| Promotion | Promote a man when it reaches the far row. If it reaches the far row during a multi-capture, stop the sequence and crown it; the new king cannot continue capturing until the next turn in the initial profile |
| Win | A player wins when the opponent has no pieces left or has no legal move |

### Important: confirm the local rule variant

Published descriptions are not perfectly consistent. A 2005 Moroccan newspaper description supports the 8×8 board, forward diagonal men, long-range diagonal Dama, and mandatory capture, but does not specify every modern tournament detail. More recent rule implementations agree on maximum capture but disagree on whether equal-length captures must prefer capturing kings/Damas. Some local groups may also use the **نفخ** penalty (removing a piece that ignored a mandatory capture).

Therefore:

- Put variant choices in a single `RulesConfig`/configuration object.
- Do not spread rule constants across the frontend and backend.
- Make the maximum-capture requirement explicit and test it.
- Keep the king-capture tie-break configurable (`none` or `prefer_kings`); use `none` initially.
- Keep the optional `نفخ` rule disabled in the MVP. Do not silently apply it.
- Record any later rule change in this section and add/adjust tests.
- Before calling the rules “official”, compare them with the actual rules used by the two players. If the player reports a difference, update the rules profile and tests rather than arguing from a website.

### Rules research references

These references are useful starting points, not a claim that every Moroccan household or region uses identical rules:

- [Aujourd'hui Le Maroc — “Dames et pions !” (27 October 2005)](https://aujourdhui.ma/archives/dames-et-pions-94012): describes Moroccan Dama on an 8×8 board, diagonal men, long-range diagonal Dama, and mandatory captures.
- [Checkers Online — Moroccan Checkers rules](https://checkersonline.io/rules/moroccan-checkers/): describes 8×8, 12 pieces per player, forward-only men, mandatory maximum capture, flying kings, and no king-count tie-break.
- [Google Play — Dama by TechFlare](https://play.google.com/store/apps/details?id=com.techflare.damamarocaine): describes 8×8, 12 pieces, mandatory maximum capture, and a preference for capturing Damas when capture counts tie. This differs from the previous rules reference and is why the tie-break must be configurable.

---

## 3. Recommended technology

Keep the stack intentionally simple and easy to run.

### Backend

- Python 3.12+
- FastAPI for HTTP endpoints and static-file hosting
- WebSockets for real-time room updates
- Pydantic for request/message validation
- In-memory room registry for the first version
- Pytest for automated tests

### Frontend

- HTML5
- CSS3
- Vanilla JavaScript (ES modules)
- No frontend framework is required for this MVP
- Use CSS Grid or a semantic board-rendering approach for the 8×8 board

### Deployment

- One Python web service serves both the API and frontend.
- Use Uvicorn in development and behind a production reverse proxy in deployment.
- Production must use HTTPS and secure WebSockets (`wss://`).
- The reverse proxy must forward WebSocket upgrade headers and must not buffer WebSocket connections.
- Do not introduce Docker, Redis, PostgreSQL, or a multi-service architecture unless needed by an actual requirement. A Dockerfile can be added after the app works locally.

---

## 4. Architecture

### Core principle: server is authoritative

The browser is responsible for rendering and collecting input. The backend owns the true game state and validates every move.

Never trust a client-supplied board state, turn, piece ownership, capture list, or winner. A client sends an attempted move; the server validates it against the current state and rules engine, applies it once, increments the game revision, and broadcasts the resulting authoritative state to both players.

### Suggested layers

1. **Rules engine** — pure game logic, with no FastAPI, WebSocket, or browser dependencies.
2. **Game/session service** — creates rooms, assigns seats, stores room state, handles player tokens, reconnects, rematches, and room expiry.
3. **Transport layer** — REST endpoints for room creation/joining and WebSocket messages for live play.
4. **Frontend** — lobby, waiting room, board, status panels, and responsive interactions.

### Suggested project structure

Adapt this structure to the existing repository if one already exists. Inspect the repository before creating or moving files.

```text
moroccan-dama/
├── README.md
├── requirements.txt
├── .env.example
├── .gitignore
├── app/
│   ├── main.py                 # FastAPI app and static mounting
│   ├── api/
│   │   └── rooms.py            # create/join room endpoints
│   ├── realtime/
│   │   ├── websocket.py        # WebSocket lifecycle and message dispatch
│   │   └── messages.py         # message schemas / validation
│   ├── game/
│   │   ├── models.py           # board, pieces, moves, game state
│   │   ├── rules.py            # legal moves and capture generation
│   │   ├── engine.py           # apply move, promotion, win detection
│   │   └── config.py           # configurable Moroccan Dama rules
│   ├── rooms/
│   │   ├── manager.py          # in-memory room registry
│   │   └── models.py           # room/player/session models
│   └── static/
│       ├── index.html
│       ├── css/
│       │   └── styles.css
│       └── js/
│           ├── app.js
│           ├── api.js
│           ├── socket.js
│           ├── board.js
│           └── ui.js
└── tests/
    ├── test_setup.py
    ├── test_men_moves.py
    ├── test_captures.py
    ├── test_kings.py
    ├── test_promotion.py
    ├── test_victory.py
    ├── test_rooms.py
    └── test_websocket.py
```

---

## 5. Game state model

Use a representation that is easy to validate and serialize. Keep coordinates consistent everywhere: `row` and `col` are integers from `0` to `7`.

A piece should contain at least:

- `id`: unique piece identifier within a match.
- `color`: `white` or `black`.
- `rank`: `man` or `king`.

The authoritative game state should contain at least:

- `board`: 8×8 array, with `null` for empty squares and a piece representation for occupied squares.
- `current_turn`: `white` or `black`.
- `status`: `waiting`, `active`, `finished`.
- `winner`: `white`, `black`, or `null`.
- `finish_reason`: such as `no_pieces`, `no_legal_moves`, or `resignation`.
- `captured`: captured-piece counts by color (or enough data to derive them consistently).
- `move_number` and/or `revision`: monotonically increasing state version.
- `last_move`: enough information for the UI to highlight the previous move.
- `rules_config`: the rule profile used for this match.

A move should represent the **complete turn**, especially for multi-captures. For example:

```json
{
  "from": [5, 0],
  "landings": [[3, 2], [1, 4]]
}
```

The server must match the submitted path against the set of legal complete turns generated from the current state. Do not accept arbitrary intermediate steps that let a client stop a mandatory capture sequence early.

---

## 6. API and real-time protocol

Exact endpoint names may change during implementation, but keep the behavior below.

### HTTP endpoints

#### `POST /api/rooms`

Create a private room.

Request:

```json
{
  "player_name": "Houssam"
}
```

Response:

```json
{
  "room_code": "A7K9Q2",
  "invite_url": "/game/A7K9Q2",
  "player_token": "opaque-random-token",
  "player_color": "white",
  "room_status": "waiting"
}
```

#### `POST /api/rooms/{room_code}/join`

Join the room if it exists, has not expired, and has an available second player slot.

Request:

```json
{
  "player_name": "Friend"
}
```

Response includes the player's opaque token, assigned color, and current room/game state.

#### `GET /api/rooms/{room_code}`

Optional read-only endpoint for a room's public state. It must not expose player tokens.

### WebSocket endpoint

`/ws/{room_code}?token={player_token}`

The token identifies the seat. A room code alone must not authorize a player to make moves.

### Client-to-server messages

Use JSON messages with a `type` field. Validate all fields and reject unknown message types.

- `make_move`: includes the full turn path (`from` plus all `landings`) and the client's last known revision.
- `resign`: current player resigns.
- `request_rematch`: player requests a new match after the current one is finished.
- `ping`: optional application-level keepalive if needed.

### Server-to-client messages

- `room_state`: authoritative room and game snapshot.
- `player_joined`: the second player has joined; match is ready/started.
- `move_applied`: accepted move plus updated state/revision.
- `move_rejected`: safe error code and user-readable message.
- `player_disconnected`: opponent lost their live connection; they may reconnect.
- `player_reconnected`: opponent returned.
- `game_finished`: winner and finish reason.
- `rematch_status`: whether one or both players have requested a rematch.
- `error`: protocol or room-level error.

### Move concurrency and idempotency

- Each accepted state change increments `revision`.
- A move with a stale revision must be rejected and the latest state sent back.
- Process room mutations atomically (for example, one async lock per room) so simultaneous messages cannot both apply to the same turn.
- A rejected move must never partially modify the board.
- Broadcast the same authoritative committed state to both connected players.

---

## 7. Room lifecycle and reconnection

- Room codes should be short, uppercase, and hard to confuse (for example, exclude `0/O` and `1/I`).
- Generate player tokens using a cryptographically secure random generator. Store only what is needed in memory.
- A player may reconnect using the same token after refreshing the page or losing connection.
- On disconnect, keep the seat and current game state for a configurable grace period (initial suggestion: 2 minutes).
- Do not immediately award a win when a player disconnects. Show a reconnecting state and let them return.
- Expire waiting rooms after a configurable period (initial suggestion: 30 minutes).
- Expire abandoned finished rooms after a configurable period (initial suggestion: 30 minutes).
- Only the room creator and their invited second player can play. A third connection must be rejected as `room_full`.
- If a player opens the invite link on a device that already owns a seat, allow the token to reconnect rather than allocating a new seat.
- Document that in-memory rooms are lost if the backend process restarts. This is acceptable for MVP.

---

## 8. UI/UX requirements

### Visual direction

Create a polished, calm board-game interface. The board and pieces must be the visual focus. Avoid a generic admin dashboard appearance.

- Warm, restrained colors inspired by wood, cream, and dark game pieces.
- Strong contrast between playable squares and non-playable squares.
- Pieces should be easy to distinguish at a glance.
- Kings/Damas must have a clear crown or ring marker.
- Use subtle transitions for movement and captures; never delay the ability to play.
- Keep controls minimal and labels clear.
- Avoid unnecessary gradients, excessive glass effects, and decorative elements that reduce board clarity.

### Required screens/states

1. **Home screen**
   - Game title and one-line explanation.
   - Display-name field.
   - Create private game button.
   - Join by room-code form.
2. **Waiting room**
   - Room code and invite URL.
   - Copy invitation button.
   - Native share button when supported.
   - Clear “Waiting for your friend…” state.
3. **Game screen**
   - 8×8 board, sized to fit the available viewport.
   - Player names and side/color.
   - Current-turn indicator.
   - Captured-piece counts.
   - Legal destination highlighting after a piece is selected.
   - Clear indication when a capture is mandatory.
   - Last-move highlight.
   - Connection status for both players.
   - Resign control with confirmation.
4. **Game-over state**
   - Winner and reason.
   - Request rematch button.
   - Show when the opponent has/has not accepted the rematch.
   - Return to home option.

### Mobile-first behavior

- The board must fit without horizontal scrolling on common phone widths.
- Use tap-to-select and tap-to-move; do not require drag-and-drop.
- Make every square large enough for reliable touch interaction.
- Keep critical status visible without covering the board.
- Respect safe areas on iPhone (`env(safe-area-inset-*)`).
- Prevent accidental page scrolling while the player is interacting with the board, without disabling normal scrolling elsewhere.
- Test portrait layout first, then desktop and landscape.

### Accessibility

- Do not rely on color alone to communicate selection, legal moves, or mandatory captures.
- Provide visible focus states and keyboard navigation where practical.
- Give board squares accessible labels (for example, “row 3, column 5, white king”).
- Use buttons for actions and sensible ARIA labels for the board.
- Respect reduced-motion preferences.

---

## 9. Security and reliability

Even though this is a small private game, server-side validation is mandatory.

- Never trust the frontend to validate moves.
- Use unpredictable player tokens; do not use the room code as a player credential.
- Enforce exactly two seats per room.
- Validate room codes, player names, JSON size, coordinate ranges, and message types.
- Limit player-name length (suggested maximum: 20 characters) and strip control characters/unsafe markup.
- Escape display names when rendering them; do not inject them as HTML.
- Apply a modest message-size limit and basic rate limiting/throttling to prevent accidental flooding.
- Restrict production CORS/origins to the deployed site.
- Use HTTPS/WSS in production.
- Do not log player tokens or full sensitive connection URLs.
- Return clear errors without leaking internal stack traces.
- Handle stale messages, duplicate submissions, disconnects, and reconnect races safely.

---

## 10. Development setup

The agent should inspect the existing repository first and preserve any useful code. If this is a new repository, use the suggested structure above.

### Requirements

- Python 3.12 or newer
- A modern browser
- Git

### Local setup

```bash
python -m venv .venv

# Windows PowerShell
.venv\Scripts\Activate.ps1

# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000`.

Run the automated test suite:

```bash
# Windows PowerShell
.\.venv\Scripts\python.exe -m pytest -v

# macOS / Linux
.venv/bin/python -m pytest -v
```

### Docker

Build the image:

```bash
docker build -t moroccan-dama:latest .
```

Run the container locally on port `8000`:

```bash
docker run --rm -p 8000:8000 --name moroccan-dama moroccan-dama:latest
```

Run in production behind an HTTPS/WSS reverse proxy:

```bash
docker run -d --restart unless-stopped \
  -p 127.0.0.1:8000:8000 \
  -e APP_ENV=production \
  -e PUBLIC_BASE_URL=https://dama.example.com \
  -e ALLOWED_ORIGINS=https://dama.example.com \
  --name moroccan-dama \
  moroccan-dama:latest
```

### Production reverse proxy & deployment notes

1. **Single-process in-memory state (MVP limitation):**
   - Active rooms are stored in memory inside `RoomManager`. Run Uvicorn with **a single worker** (`--workers 1`) so HTTP room creation/joining and WebSocket connections share the same in-memory registry.
   - Restarting or redeploying the Python service clears active rooms.
2. **Uvicorn behind HTTPS reverse proxy:**
   ```bash
   APP_ENV=production \
   PUBLIC_BASE_URL=https://dama.example.com \
   ALLOWED_ORIGINS=https://dama.example.com \
   uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1 --proxy-headers
   ```
   Health check endpoint: `GET /healthz` returns `{"status": "ok"}`.
3. **Nginx WebSocket reverse-proxy snippet (`wss://` without buffering):**
   ```nginx
   location / {
       proxy_pass http://127.0.0.1:8000;
       proxy_http_version 1.1;
       proxy_set_header Host $host;
       proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
       proxy_set_header X-Forwarded-Proto $scheme;
       proxy_set_header Upgrade $http_upgrade;
       proxy_set_header Connection "upgrade";
       proxy_buffering off;
       proxy_read_timeout 3600s;
   }
   ```
   *(Caddy forwards WebSockets and terminates TLS automatically with `reverse_proxy 127.0.0.1:8000`.)*

### Environment variables

Provide a `.env.example` with documented settings. At minimum consider:

```env
APP_ENV=development
PUBLIC_BASE_URL=http://127.0.0.1:8000
ROOM_CODE_LENGTH=6
WAITING_ROOM_TTL_SECONDS=1800
DISCONNECT_GRACE_SECONDS=120
FINISHED_ROOM_TTL_SECONDS=1800
```

Do not commit secrets or real production environment files.

---

## 11. Testing strategy

The rules engine must be testable without a running web server. Use small explicit board fixtures so every rule can be verified independently.

### Rules-engine tests

- Initial board has exactly 12 pieces per side on valid playable squares.
- Men can move one diagonal square forward when empty.
- Men cannot move backward or move into an occupied square.
- Men cannot capture backward.
- A mandatory capture prevents an ordinary move.
- A legal capture removes exactly the captured enemy piece after the turn is committed.
- Multi-capture sequences must continue until no further capture is possible.
- The same captured piece cannot be captured twice in one sequence.
- Maximum-capture selection rejects shorter capture sequences when a longer one exists.
- Equal-length sequences are handled according to the configured king tie-break.
- Kings can move multiple empty squares diagonally and cannot jump over friendly pieces.
- King captures obey the configured landing-square rule and cannot pass through blockers.
- Promotion occurs on the far row.
- Promotion during a capture sequence obeys the configured stop/continue behavior.
- The opponent loses when all pieces are captured or they have no legal move.
- A malformed or illegal move leaves the state unchanged.

### Multiplayer tests

- Creating a room returns a room code and a valid creator token.
- A second player can join and receives the opposite side.
- A third player cannot join.
- A room cannot be joined after expiry.
- Only a player's own token can control that seat.
- A move from the wrong player is rejected.
- A stale revision is rejected and the current state is returned.
- One accepted move is broadcast to both players exactly once.
- A disconnect preserves the seat during the grace period.
- A reconnect with the same token restores the seat.
- Resignation produces the correct winner.
- Rematch starts only after both players request it.

### Manual end-to-end checks

Use two separate browsers or devices, not two tabs sharing the same local state.

1. Open the site on a desktop browser and create a room.
2. Open the invitation link on an Android or iPhone browser.
3. Confirm that both clients see the same board and opposite player colors.
4. Play ordinary moves and captures; confirm updates appear on both devices without refresh.
5. Test a mandatory capture and a multi-capture.
6. Refresh one browser and confirm the same player can reconnect.
7. Temporarily disable one device's network, reconnect, and confirm the match can continue.
8. Try to join from a third browser and confirm it is rejected.
9. Finish a game by capture and another by resignation.
10. Request a rematch from both sides.
11. Repeat on narrow phone screens in portrait orientation.

---

## 12. Implementation plan

Work in small, verifiable phases. Do not build the whole application in one untested change.

### Phase 1 — Inspect and plan

- Inspect the existing repository, conventions, and available tooling.
- Identify whether any code already exists and avoid overwriting it.
- Write a short implementation plan and list any assumptions.
- Confirm the rules profile is centralized and configurable.

### Phase 2 — Pure rules engine

- Implement board setup, pieces, legal move generation, complete capture-sequence generation, move application, promotion, and win detection.
- Add the rules-engine tests before integrating networking.
- Make the full test suite pass.

### Phase 3 — Room and session management

- Implement room creation, joining, seat assignment, player tokens, room expiry, disconnect grace periods, and rematch state.
- Add unit tests for room lifecycle and authorization.

### Phase 4 — API and WebSockets

- Implement REST endpoints and WebSocket protocol.
- Make backend validation authoritative.
- Add revision checks and atomic room updates.
- Add WebSocket integration tests.

### Phase 5 — Frontend

- Implement home, waiting room, board, and game-over states.
- Connect the UI to the REST/WebSocket API.
- Make the board responsive and touch-first.
- Add loading, error, disconnected, and reconnecting states.

### Phase 6 — End-to-end verification

- Run the full test suite.
- Test two real browsers/devices.
- Fix synchronization, reconnect, mobile layout, and rule-engine issues.
- Document known limitations and the exact rules profile implemented.

### Phase 7 — Deployment readiness

- Add production configuration and health endpoint.
- Verify HTTPS/WSS behind the chosen reverse proxy.
- Document deployment and restart behavior.
- Do not claim the app is production-ready until two-device multiplayer has been tested on the deployed URL.

---

## 13. Definition of done

The MVP is complete only when all of these are true:

- [x] A user can create a private room without creating an account.
- [x] A friend can join from a different device using a link or code.
- [x] Only two players can occupy a room.
- [x] Both players see the same authoritative board state in real time.
- [x] Illegal moves are rejected by the server.
- [x] The implemented Moroccan Dama rules are documented and covered by automated tests.
- [x] Captures, multi-captures, flying kings, promotion, and win detection work.
- [x] Refreshing or briefly disconnecting does not immediately destroy a player's seat.
- [x] Resignation and mutually accepted rematch work.
- [x] The game is usable on Android, iPhone, and desktop browsers.
- [x] The test suite passes.
- [x] Setup, configuration, limitations, and deployment instructions are documented.

### Implemented rules profile & variant notes

Centralized in `app/game/config.py` (`RulesConfig`):

- `board_size = 8` (32 playable dark squares where `(row + col) % 2 == 1`; 12 men per side; `white` moves first).
- `mandatory_capture = True` (non-capturing moves are illegal whenever any capture exists).
- `maximum_capture = True` (complete turn sequences must capture the maximum possible number of pieces).
- `equal_capture_tiebreak = "none"` (configurable to `"prefer_kings"` if players prefer prioritizing Dama captures on equal counts).
- `king_flying_moves = True` and `king_capture_landing = "any_beyond"` (flying kings move and land at any unobstructed diagonal distance; configurable to `"adjacent_only"`).
- `promote_mid_capture_stops_turn = True` (a man reaching the far row during a capture crowns immediately and ends the turn; configurable to `False`).
- `captured_pieces_block_during_sequence = True` (captured pieces cannot be jumped twice and act as hurdles until the complete turn is committed).
- `huffing_enabled = False` (`نفخ` rule disabled in MVP).

---

## 14. Instructions to the coding agent

Treat this README as the product and engineering specification.

1. Start by inspecting the repository. Do not assume it is empty and do not overwrite existing work without understanding it.
2. Implement the MVP only. Do not add accounts, a database, chat, AI, rankings, or unrelated features.
3. Keep the rules engine pure, isolated, configurable, and thoroughly tested.
4. Treat the backend as the single source of truth for all game state and legal moves.
5. Use complete-turn validation for multi-captures; the client must never be able to stop a required capture sequence early.
6. Build mobile-first, with tap interactions rather than drag-only interactions.
7. Work phase by phase. After each phase, run tests and fix failures before proceeding.
8. Do not hide uncertainty about rule differences. Document the chosen configuration and any rule that still needs confirmation.
9. Do not claim that multiplayer works until it has been tested between two separate browser sessions/devices.
10. At completion, report: architecture, implemented features, rules profile, files changed, commands to run, tests executed and results, deployment steps, and remaining limitations.

**Expected result:** a simple, polished private online Moroccan Dama game that two friends can open on their own phones or computers and play together through an invitation link.
