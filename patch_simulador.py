#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations
import re
from pathlib import Path

CSS_APPEND = r"""
/* ==========================================================
   DESPLEGABLES: indicador visual (flecha)
   ========================================================== */
.oecd-details > summary.oecd-btn,
.caption-details > summary.caption-toggle{
  position: relative;
  padding-right: 44px; /* espacio para la flecha */
}

.oecd-details > summary.oecd-btn::after,
.caption-details > summary.caption-toggle::after{
  content: "▾";
  position: absolute;
  right: 14px;
  top: 50%;
  transform: translateY(-50%);
  font-size: calc(16px * var(--fontScale));
  opacity: 0.92;
  pointer-events: none;
}

.oecd-details[open] > summary.oecd-btn::after,
.caption-details[open] > summary.caption-toggle::after{
  transform: translateY(-50%) rotate(180deg);
}

/* ==========================================================
   UI: títulos/subtítulos de tarjetas ligeramente mayores
   (además del escalado de SVG)
   ========================================================== */
.chart-card .ch .cttl{
  font-size: calc(16px * var(--fontScale));
}
.chart-card .ch .csub{
  font-size: calc(14px * var(--fontScale));
}

/* Número “hero” algo mayor */
.cp-ratio-hero .big{
  font-size: calc(28px * var(--fontScale));
}
""".strip("\n")

FS_REPLACEMENT = r"""const getChartFontScale = () => parseFloat(CSS('--chartFontScale')) || 1;

  const fs = (px) => (px * getFontScale() * getChartFontScale()).toFixed(2);
  const fsTick = (px) => (px * getFontScale() * getChartFontScale()).toFixed(2);
  const fsAxisLabel = (px) => (px * getFontScale() * getChartFontScale() * getAxisLabelFontScale()).toFixed(2);"""

TIME_LEGEND_REPLACEMENT = r"""function renderTimeLegendHorizontal(svg, yTop){
    const items = [
      { label: "Menores (<18)", fill: COLORS.minors, op: "0.35" },
      { label: "Cotizantes efectivos", fill: COLORS.workers, op: "0.50" },
      { label: "Desempleados", fill: COLORS.noncot, op: "0.55" },
      { label: "Pensionistas", fill: COLORS.retired, op: "0.50" }
    ];

    const g = svgEl('g', { "opacity":"0.95" });

    const box = 16;
    const gap = 10;
    const rowH = 28;

    const startY = yTop;

    items.forEach((it, i) => {
      const yy = startY + i * rowH;

      g.appendChild(svgEl('rect', {
        x: 0, y: yy,
        width: box, height: box,
        fill: it.fill,
        "fill-opacity": it.op,
        stroke: COLORS.text,
        "stroke-width":"1",
        "stroke-opacity":"0.20",
        rx:"3", ry:"3"
      }));

      const t = svgEl('text', {
        x: box + gap,
        y: yy + box - 3,
        fill: COLORS.text,
        "font-size": fsTick(14),
        "font-family":"Arial, sans-serif",
        "text-anchor":"start",
        "opacity":"0.92"
      });
      t.textContent = it.label;
      g.appendChild(t);
    });

    svg.appendChild(g);

    // Centrado horizontal
    try{
      const bb = g.getBBox();
      const tx = (1000 - bb.width) / 2 - bb.x;
      g.setAttribute("transform", `translate(${tx.toFixed(2)} 0)`);
    }catch(e){}
  }"""

def ensure_insert_once(text: str, needle: str, insert: str) -> str:
    if insert in text:
        return text
    idx = text.find(needle)
    if idx < 0:
        raise ValueError(f"No se encontró el punto de inserción: {needle!r}")
    return text[:idx] + insert + text[idx:]


def main() -> None:
    in_path = Path("simulador.html")  # cambia aquí si tu archivo se llama distinto
    if not in_path.exists():
        raise SystemExit(
            f"No encuentro {in_path.name}. Pon este script en la misma carpeta o cambia in_path."
        )

    html = in_path.read_text(encoding="utf-8")

    # ----------------------------------------------------------
    # 1) CSS variables: --chartFontScale
    # ----------------------------------------------------------
    html = html.replace(
        "--fontScale: 1.12;",
        "--fontScale: 1.12;\n      --chartFontScale: 1.45;",
        1
    )

    html = html.replace(
        "--fontScale: 1.06;",
        "--fontScale: 1.06;\n        --chartFontScale: 1.35;",
        1
    )

    # ----------------------------------------------------------
    # 2) Append CSS block before </style> if not present
    # ----------------------------------------------------------
    if CSS_APPEND not in html:
        html = ensure_insert_once(
            html,
            "\n  </style>",
            "\n\n" + CSS_APPEND + "\n"
        )

    # ----------------------------------------------------------
    # 3) Replace fs helpers block
    # ----------------------------------------------------------
    fs_block_old = (
        "  const fs = (px) => (px * getFontScale()).toFixed(2);\n"
        "  const fsTick = (px) => (px * getFontScale()).toFixed(2);\n"
        "  const fsAxisLabel = (px) => (px * getFontScale() * getAxisLabelFontScale()).toFixed(2);\n"
    )
    if fs_block_old not in html:
        raise SystemExit("No encuentro el bloque fs/fsTick/fsAxisLabel original. El HTML no coincide con el esperado.")
    html = html.replace(fs_block_old, "  " + FS_REPLACEMENT + "\n", 1)

    # ----------------------------------------------------------
    # 4) Replace renderTimeLegendHorizontal()
    # ----------------------------------------------------------
    m = re.search(r"function renderTimeLegendHorizontal\(\s*svg\s*,\s*y\s*\)\s*\{[\s\S]*?\n  \}", html)
    if not m:
        raise SystemExit("No encuentro la función renderTimeLegendHorizontal(svg, y){...}.")
    html = html[:m.start()] + TIME_LEGEND_REPLACEMENT + html[m.end():]

    # ----------------------------------------------------------
    # 5) renderTimeChart(): pad bottom 140 -> 190
    # ----------------------------------------------------------
    html = html.replace(
        "    const pad = {l: 90, r: 30, t: 24, b: 140};",
        "    const pad = {l: 90, r: 30, t: 24, b: 190};",
        1
    )

    # ----------------------------------------------------------
    # 6) Tick labels Y: +26 -> +34 (en ambas gráficas)
    # ----------------------------------------------------------
    html = html.replace("y: pad.t + innerH + 26,", "y: pad.t + innerH + 34,")

    # ----------------------------------------------------------
    # 7) renderTimeChart(): bloque eje X + leyenda (evitar solape)
    # ----------------------------------------------------------
    time_old_block = (
        "    const xAxisLabelY = Math.min(H - 44, pad.t + innerH + getAxisLabelGap());\n"
        "    svg.appendChild(svgEl('text',{\n"
        "      x: pad.l + innerW/2, y: xAxisLabelY,\n"
        "      fill: COLORS.text, \"font-size\": fsAxisLabel(14), \"font-family\":\"Arial, sans-serif\",\n"
        "      \"text-anchor\":\"middle\", \"opacity\":\"0.95\"\n"
        "    })).textContent = \"Años / turnos\";\n\n"
        "    const legendY = Math.min(H - 16, xAxisLabelY + 30);\n"
        "    renderTimeLegendHorizontal(svg, legendY);\n"
    )
    time_new_block = (
        "    const xAxisLabelY = pad.t + innerH + 68;\n"
        "    svg.appendChild(svgEl('text',{\n"
        "      x: pad.l + innerW/2, y: xAxisLabelY,\n"
        "      fill: COLORS.text, \"font-size\": fsAxisLabel(14), \"font-family\":\"Arial, sans-serif\",\n"
        "      \"text-anchor\":\"middle\", \"opacity\":\"0.95\"\n"
        "    })).textContent = \"Años / turnos\";\n\n"
        "    // Leyenda claramente por debajo del label del eje X (sin solape)\n"
        "    const legendTop = xAxisLabelY + 18;\n"
        "    renderTimeLegendHorizontal(svg, legendTop);\n"
    )
    if time_old_block not in html:
        raise SystemExit("No encuentro el bloque original de eje X + leyenda en renderTimeChart().")
    html = html.replace(time_old_block, time_new_block, 1)

    # ----------------------------------------------------------
    # 8) renderCPChartSim(): pad bottom 70 -> 130
    # ----------------------------------------------------------
    html = html.replace(
        "    const pad = {l: 90, r: 30, t: 26, b: 70};",
        "    const pad = {l: 90, r: 30, t: 26, b: 130};",
        1
    )

    # ----------------------------------------------------------
    # 9) renderCPChartSim(): bloque label eje X
    # ----------------------------------------------------------
    cp_old_block = (
        "    const xAxisLabelY = Math.min(H - 16, pad.t + innerH + getAxisLabelGap());\n"
        "    svg.appendChild(svgEl('text',{\n"
        "      x: pad.l + innerW/2, y: xAxisLabelY,\n"
        "      fill: COLORS.text, \"font-size\": fsAxisLabel(14),\n"
        "      \"font-family\":\"Arial, sans-serif\",\n"
        "      \"text-anchor\":\"middle\", \"opacity\":\"0.95\"\n"
        "    })).textContent = \"Cotizantes (millones)\";\n"
    )
    cp_new_block = (
        "    const xAxisLabelY = pad.t + innerH + 68;\n"
        "    svg.appendChild(svgEl('text',{\n"
        "      x: pad.l + innerW/2, y: xAxisLabelY,\n"
        "      fill: COLORS.text, \"font-size\": fsAxisLabel(14),\n"
        "      \"font-family\":\"Arial, sans-serif\",\n"
        "      \"text-anchor\":\"middle\", \"opacity\":\"0.95\"\n"
        "    })).textContent = \"Cotizantes (millones)\";\n"
    )
    if cp_old_block not in html:
        raise SystemExit("No encuentro el bloque original del label X en renderCPChartSim().")
    html = html.replace(cp_old_block, cp_new_block, 1)

    out_path = in_path.with_name(in_path.stem + "_MOD.html")
    out_path.write_text(html, encoding="utf-8")

    print(f"OK: generado {out_path.name} con todas las modificaciones.")


if __name__ == "__main__":
    main()
