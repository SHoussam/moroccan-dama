const SVG_NS = "http://www.w3.org/2000/svg";

function coordKey([r, c]) {
  return `${r},${c}`;
}

function sameCoord(a, b) {
  return Boolean(a && b && a[0] === b[0] && a[1] === b[1]);
}

function createCrownSvg() {
  const svg = document.createElementNS(SVG_NS, "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("aria-hidden", "true");
  svg.classList.add("crown-icon");

  const path = document.createElementNS(SVG_NS, "path");
  path.setAttribute(
    "d",
    "M3 18h18v2H3v-2zm0-2L5.5 7l4.5 4 2-5 2 5 4.5-4L21 16H3z"
  );
  svg.appendChild(path);
  return svg;
}

export class BoardController {
  constructor({ container, onCommitMove, onSelectionChange, onIllegalHint }) {
    this.container = container;
    this.onCommitMove = onCommitMove;
    this.onSelectionChange = onSelectionChange;
    this.onIllegalHint = onIllegalHint;

    this.gameState = null;
    this.perspective = "white";
    this.selectedOrigin = null;
    this.partialLandings = [];
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
    const revChanged = !this.gameState || this.gameState.revision !== gameState.revision;
    this.gameState = gameState;
    this.perspective = perspective === "black" ? "black" : "white";
    if (revChanged || gameState.status !== "active" || gameState.current_turn !== this.perspective) {
      this.resetSelection();
    }
    this.render();
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
      this.onSelectionChange?.({
        selectedOrigin: this.selectedOrigin,
        partialLandings: [],
      });
      this.render();
      return;
    }

    const piece = this.gameState.board[r][c];
    if (piece && piece.color === this.perspective && this.gameState.mandatory_capture) {
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
          const colorName = piece.color === "white" ? "light" : "dark";
          const rankName = piece.rank === "king" ? "king" : "man";
          labelParts.push(`${colorName} ${rankName}`);
          if (isMyTurn && movableOrigins.has(key)) {
            labelParts.push("movable");
          }

          const pieceEl = document.createElement("span");
          pieceEl.className = `piece piece-${piece.color}${
            piece.rank === "king" ? " piece-king" : ""
          }`;
          if (piece.rank === "king") {
            pieceEl.appendChild(createCrownSvg());
          }
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
