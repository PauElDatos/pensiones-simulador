#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# python3 report_missing.py --json merged_countries.json --oecd-csv "OECD.ELS.SAE,DSD_POPULATION@DF_POP_HIST,1.0+.POP.PS._T..H.csv" --show-ok

import argparse
import csv
import json
import math
from collections import Counter, defaultdict
from typing import Any, Dict, List, Tuple, Optional


DEFAULT_REQUIRED_INPUTS = [
    "C_m", "C_people",
    "P_m", "P_people",
    "rho", "tau", "u",
    "pop_growth", "aging_pp",
    "k", "years",
]

# Edades OCDE (18 bins) como en tu JS (PYR_AGE_ORDER_OECD)
DEFAULT_REQUIRED_AGES = [
    "Y_LE4","Y5T9","Y10T14","Y15T19","Y20T24","Y25T29","Y30T34","Y35T39","Y40T44","Y45T49",
    "Y50T54","Y55T59","Y60T64","Y65T69","Y70T74","Y75T79","Y80T84","Y_GE85"
]

# Mapa ISO2 -> ISO3 (los 38 de tu simulador)
ISO2_TO_ISO3 = {
    "AT":"AUT","AU":"AUS","BE":"BEL","CA":"CAN","CH":"CHE","CL":"CHL","CO":"COL","CR":"CRI","CZ":"CZE",
    "DE":"DEU","DK":"DNK","EE":"EST","ES":"ESP","FI":"FIN","FR":"FRA","GB":"GBR","GR":"GRC","HU":"HUN",
    "IE":"IRL","IL":"ISR","IS":"ISL","IT":"ITA","JP":"JPN","KR":"KOR","LT":"LTU","LU":"LUX","LV":"LVA",
    "MX":"MEX","NL":"NLD","NO":"NOR","NZ":"NZL","PL":"POL","PT":"PRT","SE":"SWE","SI":"SVN","SK":"SVK",
    "TR":"TUR","US":"USA"
}


def is_missing_value(v: Any) -> bool:
    """Considera missing: None, NaN (float), y strings vacías."""
    if v is None:
        return True
    if isinstance(v, float) and math.isnan(v):
        return True
    if isinstance(v, str) and v.strip() == "":
        return True
    return False


def load_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def analyze_country(
    iso2: str,
    entry: Dict[str, Any],
    required_inputs: List[str],
) -> Tuple[str, str, List[str], List[str]]:
    name = ((entry.get("country") or {}).get("name") or iso2)

    declared_missing = entry.get("missing_fields") or []
    if isinstance(declared_missing, str):
        declared_missing = [declared_missing]

    inputs = entry.get("inputs") or {}
    missing_inputs = []
    for k in required_inputs:
        if k not in inputs or is_missing_value(inputs.get(k)):
            missing_inputs.append(k)

    return iso2, name, sorted(set(declared_missing)), sorted(set(missing_inputs))


def _safe_int(s: str) -> Optional[int]:
    try:
        return int(s)
    except Exception:
        return None


def load_oecd_population_csv(
    path: str,
    required_ages: List[str],
) -> Dict[str, Any]:
    """
    Carga el CSV OCDE (SDMX-CSV) y construye un índice mínimo:
      by_iso3[iso3][year][sex][age] = float(value)

    Solo guarda las edades requeridas (required_ages) para validación.
    """
    required_cols = {"REF_AREA", "SEX", "AGE", "TIME_PERIOD", "OBS_VALUE"}

    by_iso3: Dict[str, Dict[str, Dict[str, Dict[str, float]]]] = {}
    years_by_iso3 = defaultdict(set)  # iso3 -> {year}
    sexes_by_iso3 = defaultdict(set)  # iso3 -> {sex}

    required_ages_set = set(required_ages)

    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        r = csv.DictReader(f)

        if not r.fieldnames:
            raise ValueError("CSV sin cabecera (fieldnames vacíos).")

        missing_cols = [c for c in required_cols if c not in set(r.fieldnames)]
        if missing_cols:
            raise ValueError(f"CSV: faltan columnas requeridas: {', '.join(missing_cols)}")

        for row in r:
            iso3 = (row.get("REF_AREA") or "").strip()
            sex  = (row.get("SEX") or "").strip()
            age  = (row.get("AGE") or "").strip()
            year = (row.get("TIME_PERIOD") or "").strip()
            val_s = (row.get("OBS_VALUE") or "").strip()

            if not iso3 or not year or not sex or not age:
                continue

            years_by_iso3[iso3].add(year)
            sexes_by_iso3[iso3].add(sex)

            if age not in required_ages_set:
                continue

            try:
                v = float(val_s)
            except Exception:
                v = float("nan")

            by_iso3.setdefault(iso3, {}).setdefault(year, {}).setdefault(sex, {})[age] = v

    return {
        "by_iso3": by_iso3,
        "years_by_iso3": dict(years_by_iso3),
        "sexes_by_iso3": dict(sexes_by_iso3),
        "required_ages": required_ages,
    }


def check_oecd_csv_for_iso3(
    iso3: str,
    oecd_idx: Dict[str, Any],
) -> Tuple[bool, Optional[str], List[str]]:
    """
    Valida si el CSV tiene datos suficientes para construir pirámide en el último año:
      OK si:
        - existe _T con todas las edades requeridas, o
        - existen _M y _F con todas las edades requeridas (para sumar).
    """
    by_iso3 = oecd_idx.get("by_iso3") or {}
    years_by = oecd_idx.get("years_by_iso3") or {}
    required_ages = oecd_idx.get("required_ages") or []
    req = list(required_ages)

    years = years_by.get(iso3) or set()
    if not years:
        return False, None, ["sin_filas_iso3"]

    # Elegir último año (si todos son int, por int; si no, por string)
    years_list = list(years)
    years_int = [(y, _safe_int(y)) for y in years_list]
    if all(v is not None for _, v in years_int):
        latest_year = max(years_int, key=lambda t: t[1])[0]
    else:
        latest_year = max(years_list)

    year_block = (by_iso3.get(iso3) or {}).get(latest_year) or {}

    def has_all_ages(sex_code: str) -> Tuple[bool, List[str]]:
        ages_map = year_block.get(sex_code) or {}
        missing = []
        for a in req:
            if a not in ages_map:
                missing.append(a)
            else:
                v = ages_map.get(a)
                if v is None or (isinstance(v, float) and math.isnan(v)):
                    missing.append(a)
        return (len(missing) == 0), missing

    # Preferimos _T si está
    ok_T, miss_T = has_all_ages("_T")
    if ok_T:
        return True, latest_year, []

    # Alternativa: _M + _F completos
    ok_M, miss_M = has_all_ages("_M")
    ok_F, miss_F = has_all_ages("_F")
    if ok_M and ok_F:
        return True, latest_year, []

    # Si no cumple, construir issues
    issues = []

    if "_T" not in year_block:
        issues.append("falta_sex_T")
    else:
        if miss_T:
            issues.append("faltan_edades_T:" + "|".join(miss_T))

    if "_M" not in year_block:
        issues.append("falta_sex_M")
    else:
        if miss_M:
            issues.append("faltan_edades_M:" + "|".join(miss_M))

    if "_F" not in year_block:
        issues.append("falta_sex_F")
    else:
        if miss_F:
            issues.append("faltan_edades_F:" + "|".join(miss_F))

    return False, latest_year, issues


def issue_key(issue: str) -> str:
    """Para frecuencias: 'faltan_edades_T:...' -> 'faltan_edades_T'."""
    return issue.split(":", 1)[0].strip()


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Reporte de datos faltantes por país en merged_countries.json (+ opcional chequeo CSV OCDE)."
    )
    ap.add_argument(
        "--json",
        default="merged_countries.json",
        help="Ruta al JSON (por defecto: ./merged_countries.json)",
    )
    ap.add_argument(
        "--required-inputs",
        default=",".join(DEFAULT_REQUIRED_INPUTS),
        help="Lista CSV de claves requeridas dentro de 'inputs'",
    )
    ap.add_argument(
        "--show-ok",
        action="store_true",
        help="También muestra países sin faltantes",
    )
    ap.add_argument(
        "--oecd-csv",
        default=None,
        help="Ruta al CSV OCDE de población (SDMX-CSV). Si se indica, valida si hay bins para la pirámide.",
    )
    ap.add_argument(
        "--required-ages",
        default=",".join(DEFAULT_REQUIRED_AGES),
        help="Lista CSV de AGE codes requeridos para pirámide (por defecto: los 18 bins OCDE).",
    )
    args = ap.parse_args()

    required_inputs = [x.strip() for x in args.required_inputs.split(",") if x.strip()]
    required_ages = [x.strip() for x in args.required_ages.split(",") if x.strip()]

    # Cargar JSON
    data = load_json(args.json)
    countries = data.get("countries")
    if not isinstance(countries, dict):
        raise SystemExit("Estructura inesperada: no existe el objeto 'countries' o no es un dict.")

    # Cargar CSV OCDE si procede
    oecd_idx = None
    if args.oecd_csv:
        try:
            oecd_idx = load_oecd_population_csv(args.oecd_csv, required_ages=required_ages)
        except Exception as e:
            raise SystemExit(f"Error cargando CSV OCDE '{args.oecd_csv}': {e}")

    total = 0
    with_issues = 0

    freq_declared = Counter()
    freq_inputs = Counter()
    freq_csv = Counter()

    rows = []

    for iso2, entry in countries.items():
        total += 1
        if not isinstance(entry, dict):
            continue

        iso2 = (iso2 or "").strip().upper()
        iso2, name, declared_missing, missing_inputs = analyze_country(
            iso2=iso2, entry=entry, required_inputs=required_inputs
        )

        for k in declared_missing:
            freq_declared[k] += 1
        for k in missing_inputs:
            freq_inputs[k] += 1

        # CSV check (si activo)
        csv_issues: List[str] = []
        csv_year: Optional[str] = None
        iso3 = None

        if oecd_idx is not None:
            # Intentar sacar iso3 del JSON si existiera; si no, por mapa ISO2->ISO3
            iso3 = ((entry.get("country") or {}).get("iso3") or ISO2_TO_ISO3.get(iso2))
            if not iso3:
                csv_issues = ["no_iso3_mapping"]
            else:
                ok, csv_year, issues = check_oecd_csv_for_iso3(iso3, oecd_idx)
                if not ok:
                    csv_issues = issues

            for it in csv_issues:
                freq_csv[issue_key(it)] += 1

        has_issues = bool(declared_missing or missing_inputs or csv_issues)
        if has_issues:
            with_issues += 1

        if has_issues or args.show_ok:
            rows.append((iso2, name, declared_missing, missing_inputs, iso3, csv_year, csv_issues))

    # Orden: primero los que tienen más faltantes, luego ISO
    def row_score(r):
        # r = (iso2, name, declared_missing, missing_inputs, iso3, csv_year, csv_issues)
        return -(len(r[2]) + len(r[3]) + len(r[6]))

    rows.sort(key=lambda r: (row_score(r), r[0]))

    print("=" * 80)
    print(f"Países analizados: {total}")
    print(f"Países con faltantes (JSON/inputs/CSV): {with_issues}")
    if oecd_idx is None:
        print("Chequeo CSV OCDE: INACTIVO (usa --oecd-csv ...)")
    else:
        print(f"Chequeo CSV OCDE: ACTIVO ({args.oecd_csv})")
    print("=" * 80)

    if not rows:
        print("No hay países para mostrar (¿JSON vacío?).")
        return 0

    for iso2, name, declared_missing, missing_inputs, iso3, csv_year, csv_issues in rows:
        if not declared_missing and not missing_inputs and not csv_issues and not args.show_ok:
            continue

        print(f"\n[{iso2}] {name}")

        if declared_missing:
            print(f"  missing_fields (JSON): {', '.join(declared_missing)}")
        else:
            print("  missing_fields (JSON): —")

        if missing_inputs:
            print(f"  inputs faltantes/None (validados): {', '.join(missing_inputs)}")
        else:
            print("  inputs faltantes/None (validados): —")

        if oecd_idx is not None:
            if csv_issues:
                iso3_txt = iso3 or "—"
                year_txt = csv_year or "—"
                # Formato más legible (separa faltan_edades_* con lista de ages)
                pretty = []
                for it in csv_issues:
                    if ":" in it:
                        k, v = it.split(":", 1)
                        pretty.append(f"{k} -> {v.replace('|', ', ')}")
                    else:
                        pretty.append(it)
                print(f"  CSV OCDE: FALTAN datos ({iso3_txt} / {year_txt}): {', '.join(pretty)}")
            else:
                iso3_txt = iso3 or "—"
                year_txt = csv_year or "—"
                # Si está OK, normalmente se resolverá por _T, o por _M+_F
                print(f"  CSV OCDE: OK ({iso3_txt} / {year_txt})")

    # Resumen de frecuencia
    print("\n" + "=" * 80)
    print("Frecuencia de campos faltantes (missing_fields del JSON):")
    if freq_declared:
        for k, c in freq_declared.most_common():
            print(f"  - {k}: {c}")
    else:
        print("  (ninguno)")

    print("\nFrecuencia de claves faltantes en inputs (validación adicional):")
    if freq_inputs:
        for k, c in freq_inputs.most_common():
            print(f"  - {k}: {c}")
    else:
        print("  (ninguno)")

    if oecd_idx is not None:
        print("\nFrecuencia de problemas en CSV OCDE:")
        if freq_csv:
            for k, c in freq_csv.most_common():
                print(f"  - {k}: {c}")
        else:
            print("  (ninguno)")

    print("=" * 80)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
