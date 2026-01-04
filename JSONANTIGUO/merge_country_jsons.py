#!/usr/bin/env python3
# merge_country_jsons.py

import json
import sys
from pathlib import Path
from datetime import datetime, timezone


def load_json(path: Path) -> dict:
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(f"JSON inválido en {path.name}: {e}") from e


def extract_iso2(obj: dict, filename: str) -> str:
    try:
        iso2 = obj["country"]["iso2"]
    except Exception:
        raise ValueError(
            f"Falta country.iso2 en {filename}. "
            "El script espera la estructura: obj['country']['iso2']"
        )

    if not isinstance(iso2, str) or not iso2.strip():
        raise ValueError(f"country.iso2 vacío o no-string en {filename}")

    return iso2.strip().upper()


def merge_jsons(
    input_dir: Path,
    output_mode: str = "map",     # "map" o "list"
    recursive: bool = False,      # buscar en subcarpetas
    overwrite: bool = False,      # si ISO2 duplicado, sobrescribe (solo mode=map)
) -> dict:
    pattern = "**/*.json" if recursive else "*.json"
    files = sorted([p for p in input_dir.glob(pattern) if p.is_file()])

    if not files:
        raise ValueError(f"No se encontraron .json en: {input_dir}")

    generated_at = datetime.now(timezone.utc).isoformat()

    if output_mode == "map":
        countries_map = {}

        for fp in files:
            obj = load_json(fp)
            iso2 = extract_iso2(obj, fp.name)

            obj.setdefault("source", {})
            if isinstance(obj["source"], dict):
                obj["source"].setdefault("input_file", fp.name)
            else:
                obj["_input_file"] = fp.name

            if iso2 in countries_map and not overwrite:
                raise ValueError(
                    f"ISO2 duplicado '{iso2}'. Aparece de nuevo en {fp.name}. "
                    "Activa overwrite=True para permitir que el último archivo prevalezca."
                )

            countries_map[iso2] = obj

        return {
            "schema_version": "country_sim_inputs_bundle_v1",
            "generated_at_utc": generated_at,
            "mode": "map",
            "countries": countries_map,
            "stats": {
                "input_dir": str(input_dir),
                "files_merged": len(files),
                "unique_countries": len(countries_map),
                "recursive": recursive,
                "overwrite": overwrite,
            },
        }

    if output_mode == "list":
        countries_list = []

        for fp in files:
            obj = load_json(fp)

            obj.setdefault("source", {})
            if isinstance(obj["source"], dict):
                obj["source"].setdefault("input_file", fp.name)
            else:
                obj["_input_file"] = fp.name

            countries_list.append(obj)

        return {
            "schema_version": "country_sim_inputs_bundle_v1",
            "generated_at_utc": generated_at,
            "mode": "list",
            "countries": countries_list,
            "stats": {
                "input_dir": str(input_dir),
                "files_merged": len(files),
                "items": len(countries_list),
                "recursive": recursive,
            },
        }

    raise ValueError("output_mode debe ser 'map' o 'list'")


def main():
    # =========================
    # INPUTS (rutas fijas)
    # =========================
    input_dir = Path("/Users/paulmuseck/Desktop/pensiones-simulador/JSONANTIGUO/filtrado").expanduser().resolve()
    output_file = Path("/Users/paulmuseck/Desktop/pensiones-simulador/merged_countries.json").expanduser().resolve()

    output_mode = "map"
    recursive = False
    overwrite = False

    # =========================
    # Validaciones
    # =========================
    if not input_dir.exists() or not input_dir.is_dir():
        print(f"Error: la carpeta de entrada no existe o no es carpeta: {input_dir}", file=sys.stderr)
        sys.exit(2)

    if output_file.suffix.lower() != ".json":
        print(f"Error: el archivo de salida debe terminar en .json: {output_file}", file=sys.stderr)
        sys.exit(2)

    # =========================
    # Proceso
    # =========================
    try:
        merged = merge_jsons(
            input_dir=input_dir,
            output_mode=output_mode,
            recursive=recursive,
            overwrite=overwrite,
        )
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    output_file.parent.mkdir(parents=True, exist_ok=True)
    with output_file.open("w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2, sort_keys=True)

    print("OK: JSON unificado generado en:")
    print(f"  {output_file}")
    print("Stats:")
    for k, v in merged.get("stats", {}).items():
        print(f"  - {k}: {v}")


if __name__ == "__main__":
    main()
