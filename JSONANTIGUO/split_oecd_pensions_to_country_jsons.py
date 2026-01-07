# split_oecd_pensions_to_country_jsons.py
# -*- coding: utf-8 -*-

import os
import json
import re
import unicodedata
from typing import Any, Dict, List, Optional, Tuple

# ============================================================
# CONFIG: edita aquí tus rutas (Windows/Linux/macOS)
# ============================================================
INPUT_DIR = r"/mnt/data"                 # carpeta donde está el JSON merged
INPUT_FILENAME = "oecd_pensions_merged.json"

OUTPUT_DIR = r"/mnt/data/oecd_countries" # carpeta destino (se crea si no existe)

# Si quieres también un índice con todos los países generados:
WRITE_INDEX_FILE = True
INDEX_FILENAME = "_index.json"
# ============================================================


def sanitize_filename(name: str) -> str:
    """
    Convierte 'España' -> 'Espana', elimina caracteres raros y espacios.
    """
    name = name.strip()
    name = unicodedata.normalize("NFKD", name)
    name = name.encode("ascii", "ignore").decode("ascii")
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", name)
    name = re.sub(r"_+", "_", name).strip("_")
    return name or "country"


def safe_num(x: Any) -> Optional[float]:
    try:
        v = float(x)
        if v != v or v in (float("inf"), float("-inf")):
            return None
        return v
    except Exception:
        return None


def pick_latest(observations: List[Dict[str, Any]], predicate) -> Optional[Dict[str, Any]]:
    """
    Devuelve la observación con 'period.date' más reciente (string ISO) que cumpla predicate.
    """
    hits = [o for o in observations if predicate(o)]
    if not hits:
        return None
    hits.sort(key=lambda o: (o.get("period", {}) or {}).get("date", ""), reverse=True)
    return hits[0]


def sum_contribution_rates(observations: List[Dict[str, Any]]) -> Optional[float]:
    """
    Suma métricas que empiecen por 'contribution_rate_'.
    """
    vals = []
    for o in observations:
        m = o.get("metric")
        if isinstance(m, str) and m.startswith("contribution_rate_"):
            v = safe_num(o.get("value"))
            if v is not None:
                vals.append(v)
    if not vals:
        return None
    return float(sum(vals))


def to_millions(people: Optional[float]) -> Optional[float]:
    if people is None:
        return None
    return people / 1_000_000.0


def resolve_country_metrics(country_entry: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extrae últimos valores de: P (pensioners_people), C (contributors_*_people), rho, tau y k.
    """
    obs = country_entry.get("observations") or []
    if not isinstance(obs, list):
        obs = []

    p_obs = pick_latest(obs, lambda o: o.get("metric") == "pensioners_people")
    P_people = safe_num(p_obs.get("value")) if p_obs else None

    c_obs = pick_latest(
        obs,
        lambda o: o.get("metric") in (
            "contributors_employed_people",
            "contributors_affiliates_people",
            "contributors_affiliated_people",
        ),
    )
    C_people = safe_num(c_obs.get("value")) if c_obs else None

    rho_obs = pick_latest(obs, lambda o: o.get("metric") == "replacement_rate_gross_full_career")
    rho = safe_num(rho_obs.get("value")) if rho_obs else None

    tau = sum_contribution_rates(obs)
    k = (tau / rho) if (tau is not None and rho is not None and rho > 0) else None

    out = {
        "C_people": C_people,
        "P_people": P_people,
        "C_m": to_millions(C_people) if C_people is not None else None,
        "P_m": to_millions(P_people) if P_people is not None else None,
        "rho": rho,
        "tau": tau,
        "k": k,
        "latest": {
            "C": c_obs,
            "P": p_obs,
            "rho": rho_obs,
            "tau_components": [
                o for o in obs
                if isinstance(o.get("metric"), str) and o.get("metric").startswith("contribution_rate_")
            ],
        },
    }
    return out


def main() -> None:
    in_path = os.path.join(INPUT_DIR, INPUT_FILENAME)
    if not os.path.isfile(in_path):
        raise FileNotFoundError(f"No existe el archivo de entrada: {in_path}")

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    with open(in_path, "r", encoding="utf-8") as f:
        merged = json.load(f)

    countries = merged.get("countries") or []
    if not isinstance(countries, list):
        raise ValueError("El JSON no contiene una lista válida en la clave 'countries'.")

    index = {
        "input_file": in_path,
        "output_dir": OUTPUT_DIR,
        "countries": [],
    }

    for c in countries:
        country = (c.get("country") or {})
        name = country.get("name") or "—"
        iso2 = country.get("iso2") or None

        metrics = resolve_country_metrics(c)

        # Estructura pensada para que luego puedas cargarla desde el simulador
        country_json = {
            "schema_version": "country_sim_inputs_v1",
            "country": {
                "name": name,
                "iso2": iso2,
            },
            "inputs": {
                # Directamente desde tu merged:
                "rho": metrics["rho"],
                "tau": metrics["tau"],
                "k": metrics["k"],
                "C_people": metrics["C_people"],
                "P_people": metrics["P_people"],
                "C_m": metrics["C_m"],
                "P_m": metrics["P_m"],

                # FALTAN en tu merged: los dejamos a null para rellenar luego
                "u": None,               # paro (fracción: 0.10 = 10%)
                "pop_growth": None,      # crecimiento anual (fracción: 0.003 = 0.30%)
                "aging_pp": None,        # envejecimiento anual en pp (fracción: 0.002 = 0.20 pp)

                # Defaults del simulador (puedes cambiarlos):
                "years": 80,
            },
            "latest_observations_used": {
                "C": metrics["latest"]["C"],
                "P": metrics["latest"]["P"],
                "rho": metrics["latest"]["rho"],
                "tau_components": metrics["latest"]["tau_components"],
            },
            # Incluimos también las observaciones originales por trazabilidad (opcional pero útil)
            "observations": c.get("observations") or [],
            "source": {
                "merged_schema_version": merged.get("schema_version"),
                "generated_from": merged.get("generated_from"),
            },
            "missing_fields": ["u", "pop_growth", "aging_pp"],
        }

        base = iso2 if iso2 else sanitize_filename(name)
        fname = f"{base}.json"
        out_path = os.path.join(OUTPUT_DIR, fname)

        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(country_json, f, ensure_ascii=False, indent=2)

        index["countries"].append({
            "name": name,
            "iso2": iso2,
            "file": fname,
            "has_core_pension_inputs": all(
                metrics[k] is not None for k in ("rho", "tau", "k", "C_people", "P_people")
            ),
        })

    # orden estable por nombre
    index["countries"].sort(key=lambda x: (x["name"] or "").lower())

    if WRITE_INDEX_FILE:
        idx_path = os.path.join(OUTPUT_DIR, INDEX_FILENAME)
        with open(idx_path, "w", encoding="utf-8") as f:
            json.dump(index, f, ensure_ascii=False, indent=2)

    print(f"OK: generados {len(index['countries'])} archivos en: {OUTPUT_DIR}")
    if WRITE_INDEX_FILE:
        print(f"Índice: {os.path.join(OUTPUT_DIR, INDEX_FILENAME)}")


if __name__ == "__main__":
    main()
