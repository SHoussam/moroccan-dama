import { createStreetPieceSvg } from "./pieces.js";

function coordKey([r, c]) {
  return `${r},${c}`;
}

function sameCoord(a, b) {
  return Boolean(a && b && a[0] === b[0] && a[1] === b[1]);
}

function prefersReducedMotion() {
  return Boolean(
    window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches
  );
}

export class BoardController {
  constructor({
    container,
    onCommitMove,
    onSelectionChange,
    onIllegalHint,
    onSoundEvent,
  }) {
    this.container = container;
    this.onCommitMove = onCommitMove;
    this.onSelectionChange = onSelectionChange;
    this.onIllegalHint = onIllegalHint;
    this.onSoundEvent = onSoundEvent;

    this.gameState = null;
    this.perspective = "white";
    this.selectedOrigin = null;
    this.partialLandings = [];
    this._animTimers = [];
  }

  _clearAnimTimers() {
    for (const id of this._animTimers) {
      window.clearTimeout(id);
    }
    this._animTimers = [];
  }

  resetSelection() {
    this.selectedOrigin = null;
    this.partialLandings = [];
    this.onSelectionChange?.({
      selectedOrigin: null,
      partialLandings: [],
    });
  }

  undoStep() {
    if (this.partialLandings.length > 0) {
      this.partialLandings.pop();
    } else {
      this.selectedOrigin = null;
    }
    this.onSelectionChange?.({
      selectedOrigin: this.selectedOrigin,
      partialLandings: [...this.partialLandings],
    });
    this.render();
  }

  update(gameState, perspective) {
    const prevState = this.gameState;
    const nextPerspective = perspective === "black" ? "black" : "white";
    const revAdvanced =
      Boolean(prevState) &&
      gameState.revision === prevState.revision + 1 &&
      Boolean(gameState.last_move) &&
      this.perspective === nextPerspective;
    const revChanged = !prevState || prevState.revision !== gameState.revision;

    this.gameState = gameState;
    this.perspective = nextPerspective;

    if (
      revChanged ||
      gameState.status !== "active" ||
      gameState.current_turn !== this.perspective
    ) {
      this.resetSelection();
    }

    this._clearAnimTimers();
    this.render();

    if (revAdvanced && gameState.last_move) {
      this._animateLastMove(prevState, gameState.last_move, gameState);
    }
  }

  _isMyTurn() {
    return (
      Boolean(this.gameState) &&
      this.gameState.status === "active" &&
      this.gameState.current_turn === this.perspective
    );
  }

  _matchingMoves() {
    if (!this.gameState || !this.selectedOrigin) return [];
    const legal = this.gameState.legal_moves || [];
    return legal.filter((m) => {
      if (!sameCoord(m.from, this.selectedOrigin)) return false;
      if (m.landings.length < this.partialLandings.length) return false;
      for (let i = 0; i < this.partialLandings.length; i += 1) {
        if (!sameCoord(m.landings[i], this.partialLandings[i])) return false;
      }
      return true;
    });
  }

  _handleSquareActivate(r, c) {
    if (!this._isMyTurn()) return;

    const legalMoves = this.gameState.legal_moves || [];
    const movableOrigins = new Set(legalMoves.map((m) => coordKey(m.from)));
    const clickedCoord = [r, c];
    const clickedKey = coordKey(clickedCoord);

    if (this.selectedOrigin) {
      const candidates = this._matchingMoves();
      const stepIndex = this.partialLandings.length;
      const matchingNext = candidates.filter(
        (m) => m.landings[stepIndex] && sameCoord(m.landings[stepIndex], clickedCoord)
      );

      if (matchingNext.length > 0) {
        const nextLandings = [...this.partialLandings, clickedCoord];
        const exactComplete = matchingNext.find(
          (m) => m.landings.length === nextLandings.length
        );
        const hasLonger = matchingNext.some(
          (m) => m.landings.length > nextLandings.length
        );

        if (exactComplete && !hasLonger) {
          const origin = this.selectedOrigin;
          this.resetSelection();
          this.render();
          this.onCommitMove?.(origin, nextLandings);
          return;
        }

        this.partialLandings = nextLandings;
        this.onSoundEvent?.({ type: "select", color: this.perspective });
        this.onSelectionChange?.({
          selectedOrigin: this.selectedOrigin,
          partialLandings: [...this.partialLandings],
        });
        this.render();
        return;
      }

      // Clicking selected origin again deselects when no steps taken
      if (this.partialLandings.length === 0 && sameCoord(this.selectedOrigin, clickedCoord)) {
        this.resetSelection();
        this.render();
        return;
      }

      // Allow switching directly to another movable piece
      if (movableOrigins.has(clickedKey)) {
        this.selectedOrigin = clickedCoord;
        this.partialLandings = [];
        this.onSoundEvent?.({ type: "select", color: this.perspective });
        this.onSelectionChange?.({
          selectedOrigin: this.selectedOrigin,
          partialLandings: [],
        });
        this.render();
        return;
      }

      if (this.partialLandings.length === 0) {
        this.resetSelection();
        this.render();
      }
      return;
    }

    if (movableOrigins.has(clickedKey)) {
      this.selectedOrigin = clickedCoord;
      this.partialLandings = [];
      this.onSoundEvent?.({ type: "select", color: this.perspective });
      this.onSelectionChange?.({
        selectedOrigin: this.selectedOrigin,
        partialLandings: [],
      });
      this.render();
      return;
    }

    const piece = this.gameState.board[r][c];
    if (piece && piece.color === this.perspective && this.gameState.mandatory_capture) {
      this.onSoundEvent?.({ type: "illegal" });
      this.onIllegalHint?.("Mandatory capture: select a highlighted piece that can jump.");
    }
  }

  _handleBoardKeyDown(event, r, c) {
    const dir = this.perspective === "black" ? -1 : 1;
    let nr = r;
    let nc = c;
    if (event.key === "ArrowUp") {
      nr -= dir;
    } else if (event.key === "ArrowDown") {
      nr += dir;
    } else if (event.key === "ArrowLeft") {
      nc -= dir;
    } else if (event.key === "ArrowRight") {
      nc += dir;
    } else if (event.key === "Escape") {
      this.resetSelection();
      this.render();
      return;
    } else {
      return;
    }

    event.preventDefault();
    nr = Math.max(0, Math.min(7, nr));
    nc = Math.max(0, Math.min(7, nc));
    const target = this.container.querySelector(`[data-coord="${nr},${nc}"]`);
    target?.focus();
  }

  _visualGridPos([r, c]) {
    if (this.perspective === "black") {
      return [7 - r, 7 - c];
    }
    return [r, c];
  }

  _animateLastMove(prevState, lastMove, nextState) {
    const landings = lastMove.landings || [];
    if (landings.length === 0) return;

    const captured = lastMove.captured || [];
    const moverColor = lastMove.by || "white";
    const isCapture = captured.length > 0;

    // Trigger immediate audio when reduced motion is enabled
    if (prefersReducedMotion() || typeof Element.prototype.animate !== "function") {
      if (lastMove.promoted) {
        this.onSoundEvent?.({ type: "promote", color: moverColor });
      } else if (isCapture) {
        this.onSoundEvent?.({ type: "capture", color: moverColor, hopIndex: captured.length - 1 });
      } else {
        this.onSoundEvent?.({ type: "move", color: moverColor });
      }
      return;
    }

    const sqSize = (this.container?.clientWidth || 320) / 8;
    const finalCoord = landings[landings.length - 1];
    const destSquare = this.container.querySelector(`[data-coord="${coordKey(finalCoord)}"]`);
    const destPieceEl = destSquare?.querySelector(".piece");
    if (!destSquare || !destPieceEl) return;

    const [finalVr, finalVc] = this._visualGridPos(finalCoord);
    const waypoints = [lastMove.from, ...landings];
    const hopCount = waypoints.length - 1;
    const hopDuration = isCapture ? 175 : 195;
    const totalMoveDuration = hopCount * hopDuration;

    destSquare.classList.add("is-animating-dest");

    // Build smooth multi-hop arc or single tabletop slide keyframes (transform only!)
    const keyframes = [];
    for (let i = 0; i < waypoints.length; i += 1) {
      const [vr, vc] = this._visualGridPos(waypoints[i]);
      const dx = (vc - finalVc) * sqSize;
      const dy = (vr - finalVr) * sqSize;
      const offset = i / hopCount;

      keyframes.push({
        transform: `translate(${dx.toFixed(1)}px, ${dy.toFixed(1)}px) scale(1)`,
        offset,
      });

      if (i < hopCount) {
        const [nvr, nvc] = this._visualGridPos(waypoints[i + 1]);
        const midDx = ((vc + nvc) / 2 - finalVc) * sqSize;
        const midDy = ((vr + nvr) / 2 - finalVr) * sqSize - sqSize * (isCapture ? 0.22 : 0.1);
        const midScale = isCapture ? 1.14 : 1.07;
        keyframes.push({
          transform: `translate(${midDx.toFixed(1)}px, ${midDy.toFixed(1)}px) scale(${midScale})`,
          offset: (i + 0.48) / hopCount,
        });
      }
    }

    const moveAnim = destPieceEl.animate(keyframes, {
      duration: totalMoveDuration,
      easing: isCapture ? "cubic-bezier(0.25, 0.9, 0.35, 1)" : "cubic-bezier(0.22, 1, 0.36, 1)",
    });

    if (!isCapture && !lastMove.promoted) {
      this.onSoundEvent?.({ type: "move", color: moverColor });
    }

    // Spawn transient captured ghosts so each jumped rock/bottle-cap pops & sweeps away as crossed
    captured.forEach((capCoord, idx) => {
      const prevPiece = prevState?.board?.[capCoord[0]]?.[capCoord[1]];
      const capSq = this.container.querySelector(`[data-coord="${coordKey(capCoord)}"]`);
      if (!prevPiece || !capSq) return;

      const ghost = document.createElement("span");
      ghost.className = `piece piece-${prevPiece.color} captured-ghost${
        prevPiece.rank === "king" ? " piece-king" : ""
      }`;
      ghost.appendChild(createStreetPieceSvg(prevPiece));
      capSq.appendChild(ghost);

      const impactDelay = Math.round(idx * hopDuration + hopDuration * 0.46);
      const timerId = window.setTimeout(() => {
        this.onSoundEvent?.({ type: "capture", color: moverColor, hopIndex: idx });
        const tossX = (idx % 2 === 0 ? 1 : -1) * sqSize * 0.18;
        const popAnim = ghost.animate(
          [
            { transform: "translate(0px, 0px) scale(1) rotate(0deg)", opacity: 1 },
            {
              transform: `translate(${(tossX * 0.5).toFixed(1)}px, ${(-sqSize * 0.2).toFixed(
                1
              )}px) scale(1.12) rotate(${idx % 2 === 0 ? 12 : -12}deg)`,
              opacity: 0.92,
              offset: 0.35,
            },
            {
              transform: `translate(${tossX.toFixed(1)}px, ${(sqSize * 0.1).toFixed(
                1
              )}px) scale(0.86) rotate(${idx % 2 === 0 ? 22 : -22}deg)`,
              opacity: 0,
            },
          ],
          {
            duration: 210,
            easing: "cubic-bezier(0.4, 0, 1, 1)",
            fill: "forwards",
          }
        );
        popAnim.onfinish = () => ghost.remove();
      }, impactDelay);
      this._animTimers.push(timerId);
    });

    moveAnim.onfinish = () => {
      destSquare.classList.remove("is-animating-dest");

      if (lastMove.promoted) {
        this.onSoundEvent?.({ type: "promote", color: moverColor });
        destPieceEl.animate(
          [
            { transform: "scale(1)" },
            { transform: "scaleX(0.28) scaleY(1.16)", offset: 0.38 },
            { transform: "scale(1.13)", offset: 0.72 },
            { transform: "scale(1)" },
          ],
          {
            duration: 320,
            easing: "cubic-bezier(0.34, 1.4, 0.64, 1)",
          }
        );
      }

      if (nextState.status === "finished" && nextState.winner) {
        this._celebrateWinnerPieces(nextState.winner);
      }
    };
  }

  _celebrateWinnerPieces(winnerColor) {
    if (prefersReducedMotion() || typeof Element.prototype.animate !== "function") return;
    const winners = this.container.querySelectorAll(`.piece-${winnerColor}:not(.captured-ghost)`);
    winners.forEach((el, idx) => {
      const delay = Math.min(idx * 28, 220);
      el.animate(
        [
          { transform: "translateY(0px) scale(1)" },
          { transform: "translateY(-5px) scale(1.08)", offset: 0.45 },
          { transform: "translateY(0px) scale(1)" },
        ],
        {
          duration: 340,
          delay,
          easing: "cubic-bezier(0.22, 1, 0.36, 1)",
        }
      );
    });
  }

  render() {
    this.container.replaceChildren();
    if (!this.gameState) return;

    const isMyTurn = this._isMyTurn();
    const legalMoves = isMyTurn ? this.gameState.legal_moves || [] : [];
    const movableOrigins = new Set(legalMoves.map((m) => coordKey(m.from)));

    const nextStepTargets = new Map();
    if (isMyTurn && this.selectedOrigin) {
      const candidates = this._matchingMoves();
      const idx = this.partialLandings.length;
      for (const m of candidates) {
        const stepCoord = m.landings[idx];
        if (stepCoord) {
          nextStepTargets.set(coordKey(stepCoord), {
            isCapture: Boolean(m.is_capture),
          });
        }
      }
    }

    const stepIndices = new Map();
    this.partialLandings.forEach((coord, index) => {
      stepIndices.set(coordKey(coord), index + 1);
    });

    const lastMoveSquares = new Set();
    if (this.gameState.last_move) {
      lastMoveSquares.add(coordKey(this.gameState.last_move.from));
      const landings = this.gameState.last_move.landings || [];
      if (landings.length > 0) {
        lastMoveSquares.add(coordKey(landings[landings.length - 1]));
      }
    }

    const rows =
      this.perspective === "black"
        ? [7, 6, 5, 4, 3, 2, 1, 0]
        : [0, 1, 2, 3, 4, 5, 6, 7];
    const cols =
      this.perspective === "black"
        ? [7, 6, 5, 4, 3, 2, 1, 0]
        : [0, 1, 2, 3, 4, 5, 6, 7];

    for (const r of rows) {
      for (const c of cols) {
        const playable = (r + c) % 2 === 1;
        const key = `${r},${c}`;
        const piece = this.gameState.board[r][c];

        if (!playable) {
          const lightSq = document.createElement("div");
          lightSq.className = "board-sq sq-light";
          lightSq.dataset.coord = key;
          lightSq.setAttribute("role", "gridcell");
          lightSq.setAttribute("tabindex", "-1");
          lightSq.setAttribute("aria-label", `Row ${r + 1}, column ${c + 1}, non-playable`);
          this.container.appendChild(lightSq);
          continue;
        }

        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "board-sq sq-dark";
        btn.dataset.coord = key;
        btn.dataset.row = String(r);
        btn.dataset.col = String(c);

        if (lastMoveSquares.has(key)) {
          btn.classList.add("is-last-move");
        }

        const isSelected = sameCoord(this.selectedOrigin, [r, c]);
        if (isSelected) {
          btn.classList.add("is-selected");
          btn.setAttribute("aria-pressed", "true");
        }

        if (isMyTurn && !this.selectedOrigin && movableOrigins.has(key)) {
          btn.classList.add("is-movable-origin");
        }

        const labelParts = [`Row ${r + 1}, column ${c + 1}`];
        if (piece) {
          const materialName = piece.color === "white" ? "bottle cap (light)" : "street rock (dark)";
          const rankName = piece.rank === "king" ? "Dama king" : "piece";
          labelParts.push(`${materialName} ${rankName}`);
          if (isMyTurn && movableOrigins.has(key)) {
            labelParts.push("movable");
          }

          const pieceEl = document.createElement("span");
          pieceEl.className = `piece piece-${piece.color}${
            piece.rank === "king" ? " piece-king" : ""
          }`;
          pieceEl.dataset.pieceId = piece.id || "";
          pieceEl.appendChild(createStreetPieceSvg(piece));
          btn.appendChild(pieceEl);
        } else {
          labelParts.push("empty");
        }

        if (stepIndices.has(key)) {
          const stepNum = stepIndices.get(key);
          const badge = document.createElement("span");
          badge.className = "step-badge";
          badge.textContent = String(stepNum);
          btn.appendChild(badge);
          labelParts.push(`selected jump step ${stepNum}`);
        } else if (nextStepTargets.has(key)) {
          const info = nextStepTargets.get(key);
          const marker = document.createElement("span");
          marker.className = `dest-marker ${
            info.isCapture ? "dest-capture" : "dest-quiet"
          }`;
          btn.appendChild(marker);
          btn.classList.add("is-legal-target");
          labelParts.push(
            info.isCapture ? "legal capture landing" : "legal move destination"
          );
        }

        btn.setAttribute("aria-label", labelParts.join(", "));
        btn.addEventListener("click", () => this._handleSquareActivate(r, c));
        btn.addEventListener("keydown", (e) => this._handleBoardKeyDown(e, r, c));

        this.container.appendChild(btn);
      }
    }
  }
}
