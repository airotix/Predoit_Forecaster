#!/usr/bin/env python3
"""
Generate a small, fully synthetic sample history CSV for Preduit.

Lets a fresh install run the pipeline end-to-end without the real 10-year file
(guards against the FileNotFoundError on first run). The data is anonymised and
deterministic (fixed seed), with enough monthly span for the pipeline to train.

Usage:
    python scripts/make_sample_data.py [output_csv]

Default output: backend-ai/data/raw/sample_history.csv
Point the app at it with:  FORECASTER_DATA_FILE=backend-ai/data/raw/sample_history.csv
"""

import csv
import os
import random
import sys
from datetime import date

# Must match preduit_engine.m1_data_preparation.EXPECTED_COLUMNS (49 columns).
COLUMNS = [
    "Famille_client", "Client", "Nom", "Adresse1", "Adresse2",
    "CP", "Ville", "Pays", "Secteur", "Localisation", "Magasin",
    "Piece", "Critere", "Reference_CDE", "Representant",
    "Date_Commande", "Gencod", "Reference", "Couleur", "Taille",
    "Designation", "Rayon", "Famille", "Theme", "Modele",
    "Matiere", "Fournisseur", "Saison", "Prix",
    "CDE_qte", "CDE_brut_ht", "CDE_remise_ht", "CDE_net_ht",
    "LIV_qte", "LIV_brut_ht", "LIV_remise_ht", "LIV_net_ht",
    "RELIQUAT_qte", "RELIQUAT_brut_ht", "RELIQUAT_remise_ht", "RELIQUAT_net_ht",
    "ANN_qte", "ANN_brut_ht", "ANN_remise_ht", "ANN_net_ht",
    "STOCK", "CDE_four", "CDE_four_date_liv", "CDE_four_qte",
]

CLIENTS = [
    ("101", "Boutique Alpha", "Détaillant", "75001", "Paris", "France", "Nord"),
    ("102", "Maison Beta", "Détaillant", "69002", "Lyon", "France", "Sud-Est"),
    ("103", "Concept Gamma", "Grossiste", "13001", "Marseille", "France", "Sud"),
    ("104", "Atelier Delta", "Détaillant", "1000", "Bruxelles", "Belgique", "Export"),
]

PRODUCTS = [
    # Reference, Designation, Rayon, Famille, Theme, Modele, Matiere, Fournisseur, prix
    ("CHEM-100", "Chemise Lin", "TEXTILE", "HAUTS", "PE", "REGULAR", "LIN", "FOURN-A", 79.0),
    ("PANT-200", "Pantalon Coton", "TEXTILE", "BAS", "PE", "SLIM", "COTON", "FOURN-B", 95.0),
    ("ROBE-300", "Robe Fluide", "TEXTILE", "ROBES", "PE", "MIDI", "VISCOSE", "FOURN-A", 120.0),
]
COLORS = ["BLANC", "NOIR"]
SIZES = ["S", "M", "L"]


def main() -> int:
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        "backend-ai", "data", "raw", "sample_history.csv"
    )
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    rng = random.Random(42)

    rows = []
    # ~30 months of history so SARIMA-eligible series exist.
    months = [(y, m) for y in (2023, 2024) for m in range(1, 13)] + \
             [(2025, m) for m in range(1, 7)]

    for (cli_id, nom, fam_cli, cp, ville, pays, secteur) in CLIENTS:
        for (ref, desig, rayon, famille, theme, modele, matiere, fourn, prix) in PRODUCTS:
            for couleur in COLORS:
                for taille in SIZES:
                    stock = rng.randint(0, 40)
                    for (yy, mm) in months:
                        # Seasonal-ish demand with noise; many zeros (realistic sparsity).
                        base = 3 + (2 if taille == "M" else 0) + (1 if couleur == "NOIR" else 0)
                        seasonal = 2 if mm in (2, 3, 9, 10) else 0
                        cde = max(0, int(rng.gauss(base + seasonal, 2)))
                        if cde == 0 and rng.random() < 0.5:
                            continue  # skip to keep the file small & sparse
                        liv = max(0, cde - rng.randint(0, 1))
                        reliquat = cde - liv
                        ann = 0
                        brut = round(cde * prix, 2)
                        net = round(liv * prix, 2)
                        row = {c: "" for c in COLUMNS}
                        row.update({
                            "Famille_client": fam_cli, "Client": cli_id, "Nom": nom,
                            "CP": cp, "Ville": ville, "Pays": pays, "Secteur": secteur,
                            "Magasin": "DEPOT", "Piece": "CDE",
                            "Critere": f"{'HIVER' if mm in (9,10,11,12,1) else 'PRINTEMPS'} {yy}",
                            "Reference_CDE": f"CDE-{cli_id}-{yy}{mm:02d}",
                            "Representant": "REP1",
                            "Date_Commande": date(yy, mm, 15).isoformat(),
                            "Gencod": "", "Reference": ref, "Couleur": couleur, "Taille": taille,
                            "Designation": desig, "Rayon": rayon, "Famille": famille,
                            "Theme": theme, "Modele": modele, "Matiere": matiere,
                            "Fournisseur": fourn, "Saison": f"{'FW' if mm>=7 else 'SS'}{yy}",
                            "Prix": prix,
                            "CDE_qte": cde, "CDE_brut_ht": brut, "CDE_remise_ht": 0, "CDE_net_ht": brut,
                            "LIV_qte": liv, "LIV_brut_ht": net, "LIV_remise_ht": 0, "LIV_net_ht": net,
                            "RELIQUAT_qte": reliquat, "RELIQUAT_brut_ht": round(reliquat*prix, 2),
                            "RELIQUAT_remise_ht": 0, "RELIQUAT_net_ht": round(reliquat*prix, 2),
                            "ANN_qte": ann, "ANN_brut_ht": 0, "ANN_remise_ht": 0, "ANN_net_ht": 0,
                            "STOCK": stock, "CDE_four": "", "CDE_four_date_liv": "", "CDE_four_qte": 0,
                        })
                        rows.append(row)

    with open(out, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {len(rows)} rows to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
