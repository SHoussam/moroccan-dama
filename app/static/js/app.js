import { ApiError, createRoom, getPublicRoom, joinRoom } from "./api.js";
import { SoundEngine } from "./audio.js";
import { getAutoCafeReaction, getTauntById } from "./banter.js";
import { BoardController } from "./board.js";
import { RoomSocket } from "./socket.js";
import { UIController } from "./ui.js";

const NAME_STORAGE_KEY = "dama_player_name";
const SEAT_PREFIX = "dama_seat_";

function getStoredName() {
  try {
    return localStorage.getItem(NAME_STORAGE_KEY) || "";
  } catch {
    return "";
  }
}

function saveStoredName(name) {
  try {
    localStorage.setItem(NAME_STORAGE_KEY, name);
  } catch {
    // Ignore storage quota / privacy errors
  }
}

function getStoredSeat(roomCode) {
  try {
    const raw = localStorage.getItem(`${SEAT_PREFIX}${roomCode.toUpperCase()}`);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

function saveStoredSeat(roomCode, token, playerName) {
  try {
    localStorage.setItem(
      `${SEAT_PREFIX}${roomCode.toUpperCase()}`,
      JSON.stringify({ token, playerName })
    );
  } catch {
    // Ignore storage errors
  }
}

function clearStoredSeat(roomCode) {
  try {
    localStorage.removeItem(`${SEAT_PREFIX}${roomCode.toUpperCase()}`);
  } catch {
    // Ignore
  }
}

function parseRoomCodeFromPath(pathname) {
  const match = /^\/game\/([A-Za-z0-9_-]+)\/?$/.exec(pathname);
  return match ? match[1].toUpperCase() : null;
}

class DamaApp {
  constructor() {
    this.ui = new UIController();
    this.sound = new SoundEngine();
    this.socket = null;
    this.currentSnapshot = null;
    this.activeRoomCode = null;

    this.ui.setSoundMuted(this.sound.isMuted());
    this.ui.initTauntBar((tauntId) => this._sendTaunt(tauntId));

    this.board = new BoardController({
      container: document.getElementById("dama-board"),
      onCommitMove: (fromCoord, landings) => this._commitMove(fromCoord, landings),
      onSelectionChange: (sel) => {
        if (sel.selectedOrigin) {
          this.ui.setGameError("");
        }
        this.ui.updateStepControls(sel);
      },
      onIllegalHint: (msg) => this.ui.setGameError(msg),
      onSoundEvent: (ev) => this._handleSoundEvent(ev),
    });

    this._bindEvents();
    this._bootFromLocation();
  }

  _handleSoundEvent(ev) {
    if (!ev) return;
    switch (ev.type) {
      case "select":
        this.sound.playSelect(ev.color);
        break;
      case "move":
        this.sound.playMove(ev.color);
        break;
      case "capture":
        this.sound.playCaptureHop(ev.color, ev.hopIndex || 0);
        break;
      case "promote":
        this.sound.playPromote(ev.color);
        break;
      case "illegal":
        this.sound.playIllegal();
        break;
      default:
        break;
    }
  }

  _sendTaunt(tauntId) {
    if (!this.socket) return false;
    const sent = this.socket.sendTaunt(tauntId);
    if (!sent) {
      this.ui.setGameError("Still reconnecting—try your taunt again in a moment.");
      return false;
    }
    return true;
  }

  _bindEvents() {
    const nameInput = document.getElementById("player-name-input");
    const savedName = getStoredName();
    if (savedName && nameInput) {
      nameInput.value = savedName;
    }

    document.getElementById("btn-sound-toggle")?.addEventListener("click", () => {
      const muted = this.sound.toggleMute();
      this.ui.setSoundMuted(muted);
    });

    document.getElementById("btn-create-room")?.addEventListener("click", () => {
      this._handleCreateRoom();
    });

    nameInput?.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        this._handleCreateRoom();
      }
    });

    document.getElementById("join-code-form")?.addEventListener("submit", (e) => {
      e.preventDefault();
      this._handleJoinByCode();
    });

    document.getElementById("invite-join-form")?.addEventListener("submit", (e) => {
      e.preventDefault();
      this._handleAcceptInvite();
    });

    document.getElementById("btn-copy-code")?.addEventListener("click", async () => {
      if (!this.activeRoomCode) return;
      await this._copyText(this.activeRoomCode, "Room code copied!");
    });

    document.getElementById("btn-copy-link")?.addEventListener("click", async () => {
      if (!this.activeRoomCode) return;
      const url = `${window.location.origin}/game/${this.activeRoomCode}`;
      await this._copyText(url, "Invitation link copied!");
    });

    document.getElementById("btn-share-native")?.addEventListener("click", async () => {
      if (!this.activeRoomCode) return;
      const url = `${window.location.origin}/game/${this.activeRoomCode}`;
      if (typeof navigator.share === "function") {
        try {
          await navigator.share({
            title: "Play Moroccan Dama with me",
            text: `Join my private Moroccan Dama match (Room ${this.activeRoomCode}):`,
            url,
          });
          return;
        } catch (err) {
          if (err && err.name === "AbortError") return;
        }
      }
      await this._copyText(url, "Invitation link copied!");
    });

    document.getElementById("btn-cancel-steps")?.addEventListener("click", () => {
      this.board.undoStep();
    });

    document.getElementById("btn-resign-confirm")?.addEventListener("click", () => {
      this.ui.resetResignConfirm();
      if (!this.socket?.sendResign()) {
        this.ui.setGameError("Still reconnecting—please try again in a moment.");
      }
    });

    document.getElementById("btn-rematch")?.addEventListener("click", () => {
      if (!this.socket?.sendRematchRequest()) {
        this.ui.setGameError("Connection unavailable—reconnecting…");
      }
    });

    const goHome = () => this._navigateHome();
    document.getElementById("btn-leave-waiting")?.addEventListener("click", goHome);
    document.getElementById("btn-gameover-home")?.addEventListener("click", goHome);
    document.getElementById("btn-invite-home")?.addEventListener("click", goHome);
    document.getElementById("btn-error-home")?.addEventListener("click", goHome);

    window.addEventListener("popstate", () => {
      this._bootFromLocation();
    });
  }

  async _copyText(text, successMsg) {
    try {
      await navigator.clipboard.writeText(text);
      this.ui.showToast(successMsg);
    } catch {
      const input = document.getElementById("waiting-invite-url");
      if (input) {
        input.focus();
        input.select();
      }
      this.ui.showToast("Select and copy the link above");
    }
  }

  _disconnectSocket() {
    if (this.socket) {
      this.socket.close();
      this.socket = null;
    }
    this.currentSnapshot = null;
    this.ui.setNetStatus({ connected: false, reconnecting: false });
  }

  _navigateHome() {
    this._disconnectSocket();
    this.activeRoomCode = null;
    if (window.location.pathname !== "/") {
      window.history.pushState({}, "", "/");
    }
    this.ui.setHomeError("");
    this.ui.showScreen("screen-home");
  }

  async _bootFromLocation() {
    this._disconnectSocket();
    const code = parseRoomCodeFromPath(window.location.pathname);
    if (!code) {
      this.activeRoomCode = null;
      this.ui.showScreen("screen-home");
      return;
    }

    this.activeRoomCode = code;
    const savedSeat = getStoredSeat(code);
    if (savedSeat && savedSeat.token) {
      try {
        const rejoined = await joinRoom(code, savedSeat.playerName || "", savedSeat.token);
        this._enterRoomSession(rejoined.room_code, rejoined.player_token, rejoined.snapshot);
        return;
      } catch (err) {
        if (err instanceof ApiError && (err.code === "room_not_found" || err.code === "room_expired")) {
          clearStoredSeat(code);
          this.ui.showRoomErrorScreen("Room Expired", err.message);
          return;
        }
        clearStoredSeat(code);
      }
    }

    // New visitor opening /game/{code}
    try {
      const publicSnap = await getPublicRoom(code);
      const bothFilled = Boolean(publicSnap.players?.white && publicSnap.players?.black);
      if (bothFilled) {
        this.ui.showRoomErrorScreen(
          "Room Full",
          "Two players are already in this private match."
        );
        return;
      }
      this.ui.showInvitePrompt(publicSnap, getStoredName());
    } catch (err) {
      const msg =
        err instanceof ApiError
          ? err.message
          : "Could not reach server to inspect this room.";
      this.ui.showRoomErrorScreen("Room Not Found", msg);
    }
  }

  async _handleCreateRoom() {
    const nameInput = document.getElementById("player-name-input");
    const btn = document.getElementById("btn-create-room");
    const name = (nameInput?.value || "").trim();
    if (!name) {
      this.ui.setHomeError("Please enter your display name first.");
      nameInput?.focus();
      return;
    }

    this.ui.setHomeError("");
    btn.disabled = true;
    try {
      const res = await createRoom(name);
      saveStoredName(name);
      saveStoredSeat(res.room_code, res.player_token, name);
      window.history.pushState({}, "", `/game/${res.room_code}`);
      this._enterRoomSession(res.room_code, res.player_token, res.snapshot);
    } catch (err) {
      this.ui.setHomeError(err.message || "Unable to create room.");
    } finally {
      btn.disabled = false;
    }
  }

  async _handleJoinByCode() {
    const nameInput = document.getElementById("player-name-input");
    const codeInput = document.getElementById("room-code-input");
    const btn = document.getElementById("btn-join-code");

    const name = (nameInput?.value || "").trim();
    const rawCode = (codeInput?.value || "").trim().toUpperCase();

    if (!rawCode) {
      this.ui.setHomeError("Please enter a room code to join.");
      codeInput?.focus();
      return;
    }

    const existingSeat = getStoredSeat(rawCode);
    if (!name && !existingSeat?.token) {
      this.ui.setHomeError("Please enter your display name above before joining.");
      nameInput?.focus();
      return;
    }

    this.ui.setHomeError("");
    btn.disabled = true;
    try {
      const res = await joinRoom(
        rawCode,
        name || existingSeat?.playerName || "",
        existingSeat?.token || null
      );
      if (name) saveStoredName(name);
      saveStoredSeat(res.room_code, res.player_token, name || existingSeat?.playerName || "");
      window.history.pushState({}, "", `/game/${res.room_code}`);
      this._enterRoomSession(res.room_code, res.player_token, res.snapshot);
    } catch (err) {
      this.ui.setHomeError(err.message || "Unable to join room.");
    } finally {
      btn.disabled = false;
    }
  }

  async _handleAcceptInvite() {
    if (!this.activeRoomCode) return;
    const input = document.getElementById("invite-name-input");
    const btn = document.getElementById("btn-accept-invite");
    const name = (input?.value || "").trim();

    if (!name) {
      this.ui.setInviteError("Please enter a display name.");
      input?.focus();
      return;
    }

    this.ui.setInviteError("");
    btn.disabled = true;
    try {
      const existingSeat = getStoredSeat(this.activeRoomCode);
      const res = await joinRoom(
        this.activeRoomCode,
        name,
        existingSeat?.token || null
      );
      saveStoredName(name);
      saveStoredSeat(res.room_code, res.player_token, name);
      this._enterRoomSession(res.room_code, res.player_token, res.snapshot);
    } catch (err) {
      this.ui.setInviteError(err.message || "Could not join this room.");
    } finally {
      btn.disabled = false;
    }
  }

  _enterRoomSession(roomCode, token, initialSnapshot) {
    this._disconnectSocket();
    this.activeRoomCode = roomCode;
    this._applyRoomSnapshot(initialSnapshot);

    this.socket = new RoomSocket({
      roomCode,
      token,
      onMessage: (msg) => this._handleSocketMessage(msg),
      onConnectionChange: (state) => this.ui.setNetStatus(state),
      onFatalClose: () => {
        clearStoredSeat(roomCode);
        this.ui.showRoomErrorScreen(
          "Session Ended",
          "This room is no longer available or your session expired."
        );
      },
    });
    this.socket.connect();
  }

  _commitMove(fromCoord, landings) {
    if (!this.currentSnapshot || !this.socket) return;
    const sent = this.socket.sendMove(
      fromCoord,
      landings,
      this.currentSnapshot.game.revision
    );
    if (!sent) {
      this.ui.setGameError("Reconnecting to server—please wait a moment and retry.");
      this.board.render();
    }
  }

  _handleSocketMessage(msg) {
    switch (msg.type) {
      case "room_state":
      case "player_joined":
      case "move_applied":
      case "game_finished":
        if (msg.type === "player_joined") {
          this.sound.playTaunt();
          this.ui.showToast("Your friend joined—Yallah bsmillah!");
        }
        if (msg.room) {
          this._applyRoomSnapshot(msg.room);
        }
        break;

      case "taunt_sent": {
        const taunt = getTauntById(msg.taunt_id);
        if (taunt) {
          this.sound.playTaunt();
          const myColor = this.currentSnapshot?.your_color || "white";
          const side = msg.from_color === myColor ? "self" : "opp";
          const sender = msg.sender_name || (side === "self" ? "You" : "Opponent");
          this.ui.showSpeechBubble(side, sender, taunt.bubble);
        }
        break;
      }

      case "player_disconnected":
        if (msg.room) {
          this._applyRoomSnapshot(msg.room);
        }
        break;

      case "player_reconnected":
        this.ui.showToast("Opponent reconnected");
        if (msg.room) {
          this._applyRoomSnapshot(msg.room);
        }
        break;

      case "rematch_status":
        if (msg.started) {
          this.sound.playTaunt();
          this.ui.showToast("Rematch started—sides swapped!");
        }
        if (msg.room) {
          this._applyRoomSnapshot(msg.room);
        }
        break;

      case "move_rejected":
        this.sound.playIllegal();
        this.ui.setGameError(msg.message || "Illegal move.");
        if (msg.room) {
          this._applyRoomSnapshot(msg.room);
        } else {
          this.board.resetSelection();
          this.board.render();
        }
        break;

      case "error":
        if (msg.code !== "taunt_cooldown") {
          this.sound.playIllegal();
          this.ui.setGameError(msg.message || "Protocol error.");
        }
        break;

      default:
        break;
    }
  }

  _applyRoomSnapshot(snapshot) {
    const prevSnapshot = this.currentSnapshot;
    const sameRoom = prevSnapshot && prevSnapshot.room_code === snapshot.room_code;
    const prevGame = sameRoom ? prevSnapshot.game : null;
    const myColor = snapshot.your_color || "white";

    this.currentSnapshot = snapshot;
    if (snapshot.game.status === "waiting") {
      this.ui.renderWaitingRoom(snapshot);
      return;
    }

    this.ui.renderGameRoom(snapshot);
    this.board.update(snapshot.game, myColor);

    if (prevGame) {
      const reaction = getAutoCafeReaction({
        prevGame,
        nextGame: snapshot.game,
        myColor,
      });
      if (reaction) {
        this.ui.showCafeCallout(reaction);
      }

      if (prevGame.status !== "finished" && snapshot.game.status === "finished") {
        const iWon = snapshot.game.winner === myColor;
        window.setTimeout(() => {
          this.sound.playWin(iWon);
        }, 240);
      }
    }
  }
}

window.addEventListener("DOMContentLoaded", () => {
  new DamaApp();
});
