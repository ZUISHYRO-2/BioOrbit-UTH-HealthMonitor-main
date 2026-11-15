"""
Genera data/demo_stress_arc.csv: telemetría SIMULADA de 4 astronautas. ASTRO-02 se deteriora
progresivamente (HRV y sueño a la baja, más alertas) para demostrar cómo reacciona el Compañero;
ASTRO-01 y ASTRO-03 están estables y ASTRO-04 tiene un desgaste leve.

NO son datos reales de la NASA: es un escenario sintético para demo.
Uso:  python src/generate_demo_data.py
"""

from pathlib import Path

import numpy as np
import pandas as pd

rng = np.random.default_rng(2026)
N = 100  # registros por astronauta (cada 30 min por astronauta, intercalados cada 15 min)
start = pd.Timestamp("2026-11-14 09:00:00")

rows = []
for k in range(2 * N):
    crew = "ASTRO-01" if k % 2 == 0 else "ASTRO-02"
    p = (k // 2) / (N - 1)                       # progreso 0 -> 1
    drift = p ** 1.5 if crew == "ASTRO-02" else 0.15 * p  # ASTRO-02 se deteriora, ASTRO-01 casi estable

    hrv = 52 - 34 * drift + rng.normal(0, 3)
    sleep = 90 - 32 * drift + rng.normal(0, 3)
    hr = 68 + 30 * drift + rng.normal(0, 3)
    spo2 = 98 - 4.5 * drift ** 2 + rng.normal(0, 0.4)
    co2 = 3000 + 1700 * drift + rng.normal(0, 150)
    rad = 20 + 14 * drift + rng.normal(0, 3)
    rows.append({
        "timestamp": start + pd.Timedelta(minutes=15 * k),
        "crew_id": crew,
        "heart_rate_bpm": round(float(np.clip(hr, 52, 120)), 1),
        "hrv_rmssd_ms": round(float(np.clip(hrv, 12, 80)), 1),
        "spo2_pct": round(float(np.clip(spo2, 90, 100)), 1),
        "systolic_bp_mmhg": int(np.clip(118 + 14 * drift + rng.normal(0, 4), 100, 160)),
        "diastolic_bp_mmhg": int(np.clip(76 + 8 * drift + rng.normal(0, 3), 60, 100)),
        "body_temp_c": round(float(36.6 + rng.normal(0, 0.15)), 2),
        "radiation_rate_usv_h": round(float(np.clip(rad, 8, 60)), 2),
        "cabin_co2_ppm": int(np.clip(co2, 2500, 6000)),
        "sleep_efficiency_pct": round(float(np.clip(sleep, 40, 99)), 1),
    })

# ASTRO-03 y ASTRO-04 (para ver a toda la tripulación en el centro de control).
# Usan su propio generador aleatorio: los registros de ASTRO-01 y ASTRO-02 no cambian.
rng2 = np.random.default_rng(2027)
PROFILES = {"ASTRO-03": (0.05, 0.9, 5), "ASTRO-04": (0.45, 1.2, 20)}  # (deterioro, curva, minuto de offset)
for crew, (amount, curve, offset) in PROFILES.items():
    for j in range(N):
        drift = amount * (j / (N - 1)) ** curve
        hrv = 50 - 34 * drift + rng2.normal(0, 3)
        sleep = 89 - 32 * drift + rng2.normal(0, 3)
        hr = 66 + 30 * drift + rng2.normal(0, 3)
        spo2 = 98 - 4.5 * drift ** 2 + rng2.normal(0, 0.4)
        co2 = 3000 + 1700 * drift + rng2.normal(0, 150)
        rad = 20 + 14 * drift + rng2.normal(0, 3)
        rows.append({
            "timestamp": start + pd.Timedelta(minutes=30 * j + offset),
            "crew_id": crew,
            "heart_rate_bpm": round(float(np.clip(hr, 52, 120)), 1),
            "hrv_rmssd_ms": round(float(np.clip(hrv, 12, 80)), 1),
            "spo2_pct": round(float(np.clip(spo2, 90, 100)), 1),
            "systolic_bp_mmhg": int(np.clip(118 + 14 * drift + rng2.normal(0, 4), 100, 160)),
            "diastolic_bp_mmhg": int(np.clip(76 + 8 * drift + rng2.normal(0, 3), 60, 100)),
            "body_temp_c": round(float(36.6 + rng2.normal(0, 0.15)), 2),
            "radiation_rate_usv_h": round(float(np.clip(rad, 8, 60)), 2),
            "cabin_co2_ppm": int(np.clip(co2, 2500, 6000)),
            "sleep_efficiency_pct": round(float(np.clip(sleep, 40, 99)), 1),
        })
rows.sort(key=lambda r: r["timestamp"])

out = Path(__file__).resolve().parent.parent / "data" / "demo_stress_arc.csv"
pd.DataFrame(rows).to_csv(out, index=False)
print(f"Escrito: {out} ({len(rows)} registros)")
