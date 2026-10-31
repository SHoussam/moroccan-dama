import { QUICK_TAUNTS } from "./banter.js";
import { renderMiniPieceBadge } from "./pieces.js";

const SCREENS = [
  "screen-home",
  "screen-join-invite",
  "screen-waiting",
  "screen-game",
  "screen-room-error",
];

function byId(id) {
  return document.getElementById(id);
}

export class UIController {
  constructor() {
    this.toastContainer = byId("toast-container");
    this.netBanner = byId("net-banner");
    this.netBannerText = byId("net-banner-text");
    this.rulesModal = byId("rules-modal");
    this._bubbleTimers = { opp: null, self: null };
    this._calloutTimer = null;
    this._tauntCooldownTimer = null;

    this._renderBrandEmblems();
    this._bindStaticControls();
  }

  _renderBrandEmblems() {
    renderMiniPieceBadge(byId("home-emblem-light"), "white");
    renderMiniPieceBadge(byId("home-emblem-dark"), "black");
  }

  _bindStaticControls() {
    byId("btn-open-rules-home")?.addEventListener("click", () => this.openRules());
    byId("btn-open-rules-game")?.addEventListener("click", () => this.openRules());
    byId("btn-close-rules")?.addEventListener("click", () => this.closeRules());
    this.rulesModal?.addEventListener("click", (e) => {
      if (e.target === this.rulesModal) this.closeRules();
    });
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && !this.rulesModal.classList.contains("hidden")) {
        this.closeRules();
      }
    });

    // Inline two-step resign confirmation
    byId("btn-resign-init")?.addEventListener("click", () => {
      byId("btn-resign-init").classList.add("hidden");
      byId("resign-confirm-group").classList.remove("hidden");
    });

    byId("btn-resign-cancel")?.addEventListener("click", () => {
      this.resetResignConfirm();
    });
  }

  initTauntBar(onSendTaunt) {
    const bar = byId("taunt-bar");
    if (!bar) return;
    bar.replaceChildren();

    for (const item of QUICK_TAUNTS) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "taunt-chip";
      btn.dataset.tauntId = item.id;
      btn.textContent = item.short;
      btn.title = item.bubble;
      btn.addEventListener("click", () => {
        if (bar.classList.contains("is-cooling")) return;
        const sent = onSendTaunt?.(item.id);
        if (sent !== false) {
          this._startTauntCooldownUI(bar);
        }
      });
      bar.appendChild(btn);
    }
  }

  _startTauntCooldownUI(bar) {
    bar.classList.add("is-cooling");
    window.clearTimeout(this._tauntCooldownTimer);
    this._tauntCooldownTimer = window.setTimeout(() => {
      bar.classList.remove("is-cooling");
    }, 2050);
  }

  setSoundMuted(muted) {
    const btn = byId("btn-sound-toggle");
    const label = byId("sound-toggle-label");
    if (!btn || !label) return;
    btn.setAttribute("aria-pressed", muted ? "false" : "true");
    btn.setAttribute(
      "aria-label",
      muted ? "Unmute sound effects" : "Mute sound effects"
    );
    label.textContent = muted ? "🔇 Muted" : "🔊 Sound";
  }

  showSpeechBubble(side, senderName, text) {
    const key = side === "opp" ? "opp" : "self";
    const el = byId(key === "opp" ? "opp-speech-bubble" : "self-speech-bubble");
    if (!el) return;

    window.clearTimeout(this._bubbleTimers[key]);
    el.replaceChildren();

    const author = document.createElement("span");
    author.className = "speech-author";
    author.textContent = `${senderName}: `;

    const body = document.createElement("span");
    body.className = "speech-text";
    body.textContent = text;

    el.append(author, body);
    el.classList.remove("hidden", "is-exiting");
    // Trigger mounted state in next frame for smooth transition
    window.requestAnimationFrame(() => {
      el.classList.add("is-visible");
    });

    this._bubbleTimers[key] = window.setTimeout(() => {
      el.classList.remove("is-visible");
      el.classList.add("is-exiting");
      this._bubbleTimers[key] = window.setTimeout(() => {
        el.classList.add("hidden");
        el.classList.remove("is-exiting");
      }, 220);
    }, 3400);
  }

  showCafeCallout(text) {
    const el = byId("cafe-callout");
    if (!el || !text) return;

    window.clearTimeout(this._calloutTimer);
    el.textContent = text;
    el.classList.remove("hidden", "is-exiting");
    window.requestAnimationFrame(() => {
      el.classList.add("is-visible");
    });

    this._calloutTimer = window.setTimeout(() => {
      el.classList.remove("is-visible");
      el.classList.add("is-exiting");
      this._calloutTimer = window.setTimeout(() => {
        el.classList.add("hidden");
        el.classList.remove("is-exiting");
      }, 220);
    }, 3000);
  }

  clearTransientBanter() {
    for (const id of ["opp-speech-bubble", "self-speech-bubble", "cafe-callout"]) {
      const el = byId(id);
      if (el) {
        el.classList.add("hidden");
        el.classList.remove("is-visible", "is-exiting");
      }
    }
  }

  resetResignConfirm() {
    byId("btn-resign-init")?.classList.remove("hidden");
    byId("resign-confirm-group")?.classList.add("hidden");
  }

  openRules() {
    this.rulesModal?.classList.remove("hidden");
  }

  closeRules() {
    this.rulesModal?.classList.add("hidden");
  }

  showScreen(screenId) {
    for (const id of SCREENS) {
      const el = byId(id);
      if (el) {
        el.classList.toggle("hidden", id !== screenId);
      }
    }
    if (screenId !== "screen-game") {
      this.clearTransientBanter();
    }
    this.resetResignConfirm();
  }

  showToast(message, durationMs = 2400) {
    if (!this.toastContainer) return;
    const toast = document.createElement("div");
    toast.className = "toast";
    toast.textContent = message;
    this.toastContainer.appendChild(toast);
    window.setTimeout(() => {
      toast.remove();
    }, durationMs);
  }

  setNetStatus({ connected, reconnecting }) {
    if (!this.netBanner) return;
    if (reconnecting) {
      this.netBannerText.textContent = "Connection lost — reconnecting…";
      this.netBanner.classList.remove("hidden");
    } else {
      this.netBanner.classList.add("hidden");
    }

    const selfDot = byId("self-conn-badge");
    if (selfDot) {
      selfDot.className = `conn-dot ${connected ? "conn-online" : "conn-offline"}`;
      selfDot.title = connected ? "Connected" : "Reconnecting";
    }
  }

  setHomeError(msg) {
    const el = byId("home-error");
    if (!el) return;
    if (!msg) {
      el.classList.add("hidden");
      el.textContent = "";
    } else {
      el.textContent = msg;
      el.classList.remove("hidden");
    }
  }

  setInviteError(msg) {
    const el = byId("invite-error");
    if (!el) return;
    if (!msg) {
      el.classList.add("hidden");
      el.textContent = "";
    } else {
      el.textContent = msg;
      el.classList.remove("hidden");
    }
  }

  setGameError(msg) {
    const el = byId("game-error");
    if (!el) return;
    if (!msg) {
      el.classList.add("hidden");
      el.textContent = "";
    } else {
      el.textContent = msg;
      el.classList.remove("hidden");
      window.clearTimeout(this._gameErrTimer);
      this._gameErrTimer = window.setTimeout(() => {
        el.classList.add("hidden");
      }, 4200);
    }
  }

  showRoomErrorScreen(title, message) {
    byId("room-error-title").textContent = title;
    byId("room-error-message").textContent = message;
    this.showScreen("screen-room-error");
  }

  showInvitePrompt(roomSnapshot, savedName) {
    const host = roomSnapshot.players?.white || roomSnapshot.players?.black;
    const hostText = byId("invite-host-text");
    hostText.textContent = host
      ? `${host.name} invited you to play in room ${roomSnapshot.room_code}.`
      : `Join private match in room ${roomSnapshot.room_code}.`;
    const input = byId("invite-name-input");
    if (savedName && !input.value) {
      input.value = savedName;
    }
    this.setInviteError("");
    this.showScreen("screen-join-invite");
    input?.focus();
  }

  renderWaitingRoom(roomSnapshot) {
    this.showScreen("screen-waiting");
    const fullInviteUrl = `${window.location.origin}/game/${roomSnapshot.room_code}`;
    byId("waiting-room-code").textContent = roomSnapshot.room_code;
    byId("waiting-invite-url").value = fullInviteUrl;

    const myColor = roomSnapshot.your_color || "white";
    byId("waiting-seat-info").textContent =
      myColor === "white"
        ? "Playing as Bottle Caps (moves first)"
        : "Playing as Street Rocks";

    const shareBtn = byId("btn-share-native");
    if (typeof navigator.share === "function") {
      shareBtn.classList.remove("hidden");
    } else {
      shareBtn.classList.add("hidden");
    }
  }

  updateStepControls({ selectedOrigin, partialLandings }) {
    const wrap = byId("step-controls");
    const prompt = byId("step-prompt");
    if (!selectedOrigin || partialLandings.length === 0) {
      wrap.classList.add("hidden");
      return;
    }
    prompt.textContent = `Jump ${partialLandings.length} selected — tap next landing`;
    wrap.classList.remove("hidden");
  }

  renderGameRoom(roomSnapshot) {
    this.showScreen("screen-game");
    const game = roomSnapshot.game;
    const myColor = roomSnapshot.your_color || "white";
    const oppColor = myColor === "white" ? "black" : "white";

    const me = roomSnapshot.players?.[myColor];
    const opp = roomSnapshot.players?.[oppColor];

    // Opponent bar
    const oppBadge = byId("opp-piece-badge");
    oppBadge.className = `piece-mini piece-${oppColor}`;
    renderMiniPieceBadge(oppBadge, oppColor);

    byId("opp-name").textContent = opp ? opp.name : "Opponent";
    const oppOnline = Boolean(opp && opp.connected);
    const oppDot = byId("opp-conn-badge");
    oppDot.className = `conn-dot ${oppOnline ? "conn-online" : "conn-offline"}`;
    oppDot.title = oppOnline ? "Connected" : "Disconnected";
    byId("opp-status-sub").textContent = oppOnline
      ? oppColor === "white"
        ? "Bottle Caps • Online"
        : "Street Rocks • Online"
      : "Reconnecting…";

    // Captured counts: pieces captured BY a player = captured pieces of the opposite color
    byId("opp-captured-count").textContent = String(game.captured?.[myColor] ?? 0);
    byId("self-captured-count").textContent = String(game.captured?.[oppColor] ?? 0);

    // Self bar
    const selfBadge = byId("self-piece-badge");
    selfBadge.className = `piece-mini piece-${myColor}`;
    renderMiniPieceBadge(selfBadge, myColor);

    byId("self-name").textContent = me ? me.name : "You";
    byId("game-room-code").textContent = roomSnapshot.room_code;

    // Opponent disconnect banner during active game
    const oppAlert = byId("opp-disconnect-alert");
    if (opp && !opp.connected && game.status === "active") {
      oppAlert.textContent = `${opp.name} lost connection — holding their seat to reconnect.`;
      oppAlert.classList.remove("hidden");
    } else {
      oppAlert.classList.add("hidden");
    }

    // Turn & Mandatory Capture strip
    const turnBanner = byId("turn-banner");
    const turnDisc = byId("turn-disc");
    const turnText = byId("turn-text");
    const mandatoryBadge = byId("mandatory-badge");
    const resignWrap = byId("resign-wrap");
    const gameoverPanel = byId("gameover-panel");

    turnDisc.className = `turn-disc piece-${game.current_turn}`;
    renderMiniPieceBadge(turnDisc, game.current_turn);

    if (game.status === "active") {
      gameoverPanel.classList.add("hidden");
      resignWrap.classList.remove("hidden");

      const isMyTurn = game.current_turn === myColor;
      turnBanner.classList.toggle("is-my-turn", isMyTurn);
      turnText.textContent = isMyTurn
        ? "Your turn"
        : `${opp ? opp.name : "Opponent"}'s turn`;

      if (game.mandatory_capture) {
        mandatoryBadge.classList.remove("hidden");
      } else {
        mandatoryBadge.classList.add("hidden");
      }
    } else if (game.status === "finished") {
      mandatoryBadge.classList.add("hidden");
      byId("step-controls").classList.add("hidden");
      resignWrap.classList.add("hidden");
      turnBanner.classList.remove("is-my-turn");
      turnText.textContent = "Match ended";

      gameoverPanel.classList.remove("hidden");
      const iWon = game.winner === myColor;
      const winnerPlayer = game.winner ? roomSnapshot.players?.[game.winner] : null;
      byId("gameover-title").textContent = iWon
        ? "You won!"
        : `${winnerPlayer ? winnerPlayer.name : "Opponent"} won`;

      const reasonMap = {
        no_pieces: "All opposing pieces were swept off the board.",
        no_legal_moves: "No legal moves remaining.",
        resignation: iWon
          ? `${opp ? opp.name : "Opponent"} resigned the match.`
          : "You resigned the match.",
      };
      byId("gameover-reason").textContent =
        reasonMap[game.finish_reason] || "Match complete.";

      const requestedBy = roomSnapshot.rematch_requested_by || [];
      const iRequested = requestedBy.includes(myColor);
      const oppRequested = requestedBy.includes(oppColor);
      const rematchBtn = byId("btn-rematch");
      const rematchNote = byId("rematch-status-text");

      if (iRequested && !oppRequested) {
        rematchBtn.disabled = true;
        rematchBtn.textContent = "Rematch requested…";
        rematchNote.textContent = `Waiting for ${opp ? opp.name : "your friend"} to accept.`;
      } else if (!iRequested && oppRequested) {
        rematchBtn.disabled = false;
        rematchBtn.textContent = "Accept rematch";
        rematchNote.textContent = `${opp ? opp.name : "Your friend"} wants a rematch!`;
      } else {
        rematchBtn.disabled = false;
        rematchBtn.textContent = "Request rematch";
        rematchNote.textContent = "";
      }
    }
  }
}
