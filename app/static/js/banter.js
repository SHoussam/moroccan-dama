/**
 * Curated Franco-Darija banter & automatic Moroccan café callouts.
 * IDs match ALLOWED_TAUNT_IDS in app/realtime/messages.py.
 */
export const QUICK_TAUNTS = [
  {
    id: "hez_yeddik",
    short: "Hez yeddik! 🙌",
    bubble: "Hez yeddik a sahbi! 🙌",
  },
  {
    id: "chreb_atay",
    short: "Chreb atay 🫖",
    bubble: "Chreb atay w fekker mzyan! 🫖",
  },
  {
    id: "kul_wla_nkul",
    short: "Kul wla nkul! 😋",
    bubble: "Kul wla nkul—3andek l'makla! 😋",
  },
  {
    id: "fin_ghadi_7ejra",
    short: "Fin ghadi?! 🪨",
    bubble: "Fin ghadi b had l'7ejra?! 😂",
  },
  {
    id: "bouchona_dama",
    short: "Qleb l'bouchona! 👑",
    bubble: "Qleb l'bouchona—wllat Dama! 👑",
  },
  {
    id: "m3allem",
    short: "L'm3allem 🧠",
    bubble: "Hadi dama d l'm3allem! 🧠",
  },
  {
    id: "3ti_lkhater",
    short: "3ti l'khater 😎",
    bubble: "Bchwia 3lik, 3ti l'khater! 😎",
  },
  {
    id: "ach_had_l3eb",
    short: "Ach had l3eb?! 😭",
    bubble: "Wili ach had l3eb a khoya?! 😭",
  },
];

const TAUNT_BY_ID = new Map(QUICK_TAUNTS.map((t) => [t.id, t]));

export function getTauntById(tauntId) {
  return TAUNT_BY_ID.get(tauntId) || null;
}

/**
 * Derive an automatic Moroccan café reaction line on notable board events.
 * Returns null on ordinary quiet moves so banter stays punchy and never noisy.
 */
export function getAutoCafeReaction({ prevGame, nextGame, myColor }) {
  if (!nextGame) return null;

  const prevStatus = prevGame?.status;
  const lastMove = nextGame.last_move;

  if (nextGame.status === "finished" && prevStatus !== "finished") {
    const iWon = nextGame.winner === myColor;
    if (nextGame.finish_reason === "resignation") {
      return iWon
        ? "Hreb men l'tabla! Rb7ti a l'm3allem! 🏆"
        : "Safi hzina l'yed—ara chi revanche! 🫖";
    }
    return iWon
      ? "Safi salina! Jma3 l'bouchonat w l'7jer—rb7ti! 🏆"
      : "Ma3lich! Ara chi berrad d'atay w n3awdouha! 🫖";
  }

  if (prevGame && nextGame.revision > prevGame.revision && lastMove) {
    const capCount = lastMove.captured ? lastMove.captured.length : 0;
    const moverColor = lastMove.by || "white";

    if (lastMove.promoted) {
      return moverColor === "white"
        ? "Qleb l'bouchona! Wllat Dama—triq mftou7a! 👑"
        : "Rekkeb l'7ejra! Wllat Dama—triq mftou7a! 👑";
    }

    if (capCount >= 2) {
      return `Wili wili! Jma3 kolchi (${capCount} f deqqa)! 🔥`;
    }

    if (capCount === 1) {
      return moverColor === "white"
        ? "Bss7a! Taret l'7ejra men l'tabla! 💥"
        : "Bss7a! Taret l'bouchona men l'tabla! 💥";
    }
  }

  if (
    nextGame.status === "active" &&
    nextGame.current_turn === myColor &&
    nextGame.mandatory_capture &&
    (!prevGame || prevGame.revision !== nextGame.revision)
  ) {
    return "3andek l'makla! Kul qbel ma yakluk! ⚡";
  }

  return null;
}
