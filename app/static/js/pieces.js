const SVG_NS = "http://www.w3.org/2000/svg";
let nextSvgInstanceId = 1;

function svgEl(tag, attrs = {}) {
  const el = document.createElementNS(SVG_NS, tag);
  for (const [k, v] of Object.entries(attrs)) {
    el.setAttribute(k, String(v));
  }
  return el;
}

function hashSeed(idStr = "p1") {
  let h = 2166136261;
  const s = String(idStr);
  for (let i = 0; i < s.length; i += 1) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

function buildBottleCapSkirtPath(cx, cy, baseR, amp, teeth = 21, steps = 126) {
  const pts = [];
  for (let i = 0; i <= steps; i += 1) {
    const theta = (i / steps) * Math.PI * 2;
    const r = baseR + amp * Math.cos(teeth * theta);
    const x = cx + r * Math.cos(theta);
    const y = cy + r * Math.sin(theta);
    pts.push(`${i === 0 ? "M" : "L"}${x.toFixed(2)},${y.toFixed(2)}`);
  }
  pts.push("Z");
  return pts.join(" ");
}

const CAP_OUTER_PATH = buildBottleCapSkirtPath(50, 50, 44.2, 3.1, 21, 126);
const CAP_INNER_TEETH_PATH = buildBottleCapSkirtPath(50, 50, 39.2, 2.2, 21, 126);

function buildPebblePath(seed, cx = 50, cy = 50, baseRx = 41.5, baseRy = 39.0) {
  const anchors = 10;
  const pts = [];
  let s = seed || 1;
  const nextRand = () => {
    s = (Math.imul(s, 1664525) + 1013904223) >>> 0;
    return s / 4294967296;
  };

  const phaseA = nextRand() * Math.PI * 2;
  const phaseB = nextRand() * Math.PI * 2;

  for (let i = 0; i < anchors; i += 1) {
    const angle = (i / anchors) * Math.PI * 2;
    const wobble =
      1 +
      0.065 * Math.sin(2 * angle + phaseA) +
      0.05 * Math.cos(3 * angle + phaseB) +
      (nextRand() - 0.5) * 0.05;
    const rx = baseRx * wobble;
    const ry = baseRy * wobble;
    pts.push([cx + rx * Math.cos(angle), cy + ry * Math.sin(angle)]);
  }

  const d = [];
  for (let i = 0; i < anchors; i += 1) {
    const p0 = pts[i];
    const p1 = pts[(i + 1) % anchors];
    const midX = (p0[0] + p1[0]) / 2;
    const midY = (p0[1] + p1[1]) / 2;
    if (i === 0) {
      const prev = pts[anchors - 1];
      const startX = (prev[0] + p0[0]) / 2;
      const startY = (prev[1] + p0[1]) / 2;
      d.push(`M${startX.toFixed(2)},${startY.toFixed(2)}`);
    }
    d.push(`Q${p0[0].toFixed(2)},${p0[1].toFixed(2)} ${midX.toFixed(2)},${midY.toFixed(2)}`);
  }
  d.push("Z");
  return d.join(" ");
}

function appendCrownGlyph(parent, { cx = 50, cy = 51, scale = 1, fill = "#e0a526", stroke = "#4a2e05" } = {}) {
  const g = svgEl("g", {
    transform: `translate(${cx}, ${cy}) scale(${scale}) translate(-12, -12)`,
  });
  g.appendChild(
    svgEl("path", {
      d: "M3.5 18h17v2.2h-17V18zm-.3-2.1L5.8 7.2l4.1 3.9L12 5.6l2.1 5.5 4.1-3.9 2.6 8.7H3.2z",
      fill,
      stroke,
      "stroke-width": "1.15",
      "stroke-linejoin": "round",
    })
  );
  parent.appendChild(g);
}

/**
 * Create an inline SVG representing a Moroccan street Dama piece:
 * - "white" (Light side) -> Crimped metal soda bottle cap ("Bouchona")
 *   When promoted to "king" -> Flipped upside-down bottle cap showing inner cork seal + Dama crown!
 * - "black" (Dark side)  -> Smooth organic street rock / pebble ("7ejra")
 *   When promoted to "king" -> Double-stacked stone cairn marked with chalk-gold Dama crown!
 */
export function createStreetPieceSvg(piece) {
  const svg = svgEl("svg", {
    viewBox: "0 0 100 100",
    "aria-hidden": "true",
    class: "piece-svg",
  });

  const uid = `${piece.id || piece.color}-${piece.rank}-${nextSvgInstanceId}`;
  nextSvgInstanceId += 1;
  const defs = svgEl("defs");

  if (piece.color === "white") {
    // Metal skirt gradient
    const metalGrad = svgEl("linearGradient", {
      id: `cap-metal-${uid}`,
      x1: "15%",
      y1: "10%",
      x2: "85%",
      y2: "90%",
    });
    metalGrad.appendChild(svgEl("stop", { offset: "0%", "stop-color": "#f3eee2" }));
    metalGrad.appendChild(svgEl("stop", { offset: "48%", "stop-color": "#c7beae" }));
    metalGrad.appendChild(svgEl("stop", { offset: "100%", "stop-color": "#7b7162" }));
    defs.appendChild(metalGrad);

    if (piece.rank === "man") {
      // Top-down vintage Moroccan soda cap dome
      const domeGrad = svgEl("radialGradient", {
        id: `cap-dome-${uid}`,
        cx: "36%",
        cy: "32%",
        r: "66%",
      });
      domeGrad.appendChild(svgEl("stop", { offset: "0%", "stop-color": "#fffdf6" }));
      domeGrad.appendChild(svgEl("stop", { offset: "58%", "stop-color": "#f6e4bc" }));
      domeGrad.appendChild(svgEl("stop", { offset: "100%", "stop-color": "#d5b271" }));
      defs.appendChild(domeGrad);
      svg.appendChild(defs);

      // Crimped 21-tooth metal outer rim
      svg.appendChild(
        svgEl("path", {
          d: CAP_OUTER_PATH,
          fill: `url(#cap-metal-${uid})`,
          stroke: "#4b4135",
          "stroke-width": "2.1",
        })
      );

      // Crimp fold ticks around the skirt
      const ticks = svgEl("g", { stroke: "#5c5143", "stroke-width": "1.35", "stroke-linecap": "round" });
      for (let i = 0; i < 21; i += 1) {
        const th = (i / 21) * Math.PI * 2;
        const x1 = 50 + 37.2 * Math.cos(th);
        const y1 = 50 + 37.2 * Math.sin(th);
        const x2 = 50 + 46.2 * Math.cos(th);
        const y2 = 50 + 46.2 * Math.sin(th);
        ticks.appendChild(svgEl("line", { x1: x1.toFixed(1), y1: y1.toFixed(1), x2: x2.toFixed(1), y2: y2.toFixed(1) }));
      }
      svg.appendChild(ticks);

      // Enameled cap top dome
      svg.appendChild(
        svgEl("circle", {
          cx: "50",
          cy: "50",
          r: "36.5",
          fill: `url(#cap-dome-${uid})`,
          stroke: "#8f6f3c",
          "stroke-width": "1.8",
        })
      );

      // Classic vintage soda red-terracotta accent ring
      svg.appendChild(
        svgEl("circle", {
          cx: "50",
          cy: "50",
          r: "27.5",
          fill: "none",
          stroke: "#b83a28",
          "stroke-width": "3.2",
          opacity: "0.86",
        })
      );

      // Center embossed Moroccan soda emblem dot/wave
      svg.appendChild(
        svgEl("path", {
          d: "M35 51 C41 45, 46 55, 50 49 C54 44, 59 54, 65 48",
          fill: "none",
          stroke: "#b83a28",
          "stroke-width": "2.6",
          "stroke-linecap": "round",
          opacity: "0.82",
        })
      );

      // Specular top-left enamel highlight
      svg.appendChild(
        svgEl("path", {
          d: "M27 37 A26 26 0 0 1 64 25",
          fill: "none",
          stroke: "rgba(255,255,255,0.78)",
          "stroke-width": "3.2",
          "stroke-linecap": "round",
        })
      );
    } else {
      // KING ("Dama"): Flipped upside-down bottle cap showing inner metal well, cork seal & crown!
      const wellGrad = svgEl("radialGradient", {
        id: `cap-well-${uid}`,
        cx: "55%",
        cy: "58%",
        r: "62%",
      });
      wellGrad.appendChild(svgEl("stop", { offset: "0%", "stop-color": "#fff6da" }));
      wellGrad.appendChild(svgEl("stop", { offset: "68%", "stop-color": "#e3c585" }));
      wellGrad.appendChild(svgEl("stop", { offset: "100%", "stop-color": "#9b7a3f" }));
      defs.appendChild(wellGrad);
      svg.appendChild(defs);

      // Outer crimped rim (golden-tin crowned tint)
      svg.appendChild(
        svgEl("path", {
          d: CAP_OUTER_PATH,
          fill: `url(#cap-metal-${uid})`,
          stroke: "#9a6c18",
          "stroke-width": "2.4",
        })
      );

      // Upward-curling inner crimped teeth of flipped cap
      svg.appendChild(
        svgEl("path", {
          d: CAP_INNER_TEETH_PATH,
          fill: "#6c6152",
          stroke: "#463d32",
          "stroke-width": "1.2",
        })
      );

      // Inner cork / rubber seal gasket ring + recessed metal dish
      svg.appendChild(
        svgEl("circle", {
          cx: "50",
          cy: "50",
          r: "33.5",
          fill: `url(#cap-well-${uid})`,
          stroke: "#b87a24",
          "stroke-width": "4.2",
        })
      );
      svg.appendChild(
        svgEl("circle", {
          cx: "50",
          cy: "50",
          r: "29.2",
          fill: "none",
          stroke: "#7d5418",
          "stroke-width": "1.1",
          "stroke-dasharray": "4 3",
        })
      );

      appendCrownGlyph(svg, {
        cx: 50,
        cy: 50.5,
        scale: 1.55,
        fill: "#d99216",
        stroke: "#4a2c04",
      });
    }
    return svg;
  }

  // DARK SIDE ("black") -> Smooth street rock / pebble ("7ejra")
  const seed = hashSeed(piece.id || "b1");
  const stoneGrad = svgEl("radialGradient", {
    id: `rock-grad-${uid}`,
    cx: "34%",
    cy: "28%",
    r: "70%",
  });
  stoneGrad.appendChild(svgEl("stop", { offset: "0%", "stop-color": "#5d544c" }));
  stoneGrad.appendChild(svgEl("stop", { offset: "48%", "stop-color": "#332d29" }));
  stoneGrad.appendChild(svgEl("stop", { offset: "100%", "stop-color": "#181412" }));
  defs.appendChild(stoneGrad);

  const topStoneGrad = svgEl("radialGradient", {
    id: `rock-top-${uid}`,
    cx: "35%",
    cy: "30%",
    r: "68%",
  });
  topStoneGrad.appendChild(svgEl("stop", { offset: "0%", "stop-color": "#8e8175" }));
  topStoneGrad.appendChild(svgEl("stop", { offset: "58%", "stop-color": "#4d453e" }));
  topStoneGrad.appendChild(svgEl("stop", { offset: "100%", "stop-color": "#241e1b" }));
  defs.appendChild(topStoneGrad);
  svg.appendChild(defs);

  const mainRockPath = buildPebblePath(seed, 50, 51, 43.0, 40.2);
  svg.appendChild(
    svgEl("path", {
      d: mainRockPath,
      fill: `url(#rock-grad-${uid})`,
      stroke: piece.rank === "king" ? "#d49d35" : "#110e0c",
      "stroke-width": piece.rank === "king" ? "2.6" : "2.2",
    })
  );

  // Subtle mineral speckles & stone facet crease
  const sp1x = 34 + (seed % 11);
  const sp1y = 36 + ((seed >> 4) % 9);
  const sp2x = 60 + ((seed >> 8) % 9);
  const sp2y = 58 + ((seed >> 12) % 9);
  svg.appendChild(
    svgEl("circle", { cx: sp1x, cy: sp1y, r: "2.1", fill: "#8b7f73", opacity: "0.45" })
  );
  svg.appendChild(
    svgEl("circle", { cx: sp2x, cy: sp2y, r: "1.7", fill: "#9e9183", opacity: "0.38" })
  );
  svg.appendChild(
    svgEl("path", {
      d: "M27 38 Q42 26 63 32",
      fill: "none",
      stroke: "rgba(255,248,235,0.22)",
      "stroke-width": "2.6",
      "stroke-linecap": "round",
    })
  );

  if (piece.rank === "king") {
    // Stacked smaller pebble on top + gold/chalk Dama crown!
    const upperPath = buildPebblePath(seed ^ 0x9e3779b9, 50, 47, 29.5, 27.5);
    // Drop shadow of stacked stone onto base stone
    svg.appendChild(
      svgEl("ellipse", {
        cx: "51",
        cy: "52.5",
        rx: "29",
        ry: "26.5",
        fill: "rgba(0,0,0,0.48)",
      })
    );
    svg.appendChild(
      svgEl("path", {
        d: upperPath,
        fill: `url(#rock-top-${uid})`,
        stroke: "#e2ab3b",
        "stroke-width": "2.1",
      })
    );
    appendCrownGlyph(svg, {
      cx: 50,
      cy: 47.5,
      scale: 1.38,
      fill: "#f5be49",
      stroke: "#231604",
    });
  }

  return svg;
}

/**
 * Populate a mini badge element (player bar / turn disc) with a mini bottle cap or pebble SVG.
 */
export function renderMiniPieceBadge(el, color) {
  if (!el) return;
  const key = color === "black" ? "black" : "white";
  if (el.dataset.renderedPieceColor === key && el.childElementCount > 0) {
    return;
  }
  el.dataset.renderedPieceColor = key;
  el.replaceChildren(
    createStreetPieceSvg({
      id: key === "white" ? "mini-cap" : "mini-rock",
      color: key,
      rank: "man",
    })
  );
}
