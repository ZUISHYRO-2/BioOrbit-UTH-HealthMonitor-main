"""
BioOrbit-UTH Health Monitor - Pipeline de Telemetría Biomédica
Procesamiento de datos fisiológicos de astronautas en misiones de larga duración.
Basado en métricas de NASA Open Science Data Repository (OSDR) y Life Sciences Portal (LSDA).
"""

import pandas as pd
import numpy as np

TELEMETRY_COLUMNS = frozenset({
    "timestamp",
    "crew_id",
    "heart_rate_bpm",
    "hrv_rmssd_ms",
    "spo2_pct",
    "systolic_bp_mmhg",
    "diastolic_bp_mmhg",
    "body_temp_c",
    "radiation_rate_usv_h",
    "cabin_co2_ppm",
    "sleep_efficiency_pct",
})


def has_telemetry_schema(filepath: str) -> bool:
    """Indica si el CSV contiene las columnas esperadas de telemetría."""
    columns = pd.read_csv(filepath, nrows=0).columns
    return TELEMETRY_COLUMNS.issubset(columns)


def load_telemetry(filepath: str) -> pd.DataFrame:
    """Carga y parsea el archivo de telemetría de tripulación."""
    df = pd.read_csv(filepath)
    missing_columns = TELEMETRY_COLUMNS.difference(df.columns)
    if missing_columns:
        missing = ", ".join(sorted(missing_columns))
        raise ValueError(f"El archivo '{filepath}' no es telemetría válida; faltan columnas: {missing}")
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    return df

def calculate_health_scores(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calcula índices fisiológicos compuestos:
    - Cardiovascular Stress Index (CSI)_
    - Autonomic Recovery Index (ARI basado en HRV)
    - Environmental Hazard Score (EHS basado en CO2 y radiación)
    - Composite Astronaut Risk Level (Normal, Alerta, Crítico)
    """
    df = df.copy()
    
    # 1. Cardiovascular Stress (relación FC y SpO2)
    # Rango normal: FC entre 60 y 90, SpO2 >= 96
    hr_penalty = np.maximum(0, (df["heart_rate_bpm"] - 90) / 10) + np.maximum(0, (60 - df["heart_rate_bpm"]) / 10)
    spo2_penalty = np.maximum(0, (96 - df["spo2_pct"]) * 2)
    df["cardiovascular_stress_index"] = (hr_penalty + spo2_penalty).round(2)
    
    # 2. Autonomic Recovery (basado en RMSSD de HRV)
    # RMSSD > 40 ms indica buena recuperación autonómica; < 25 ms estrés fisiológico severo
    df["autonomic_fatigue_index"] = np.where(
        df["hrv_rmssd_ms"] < 25, "Alta Fatiga",
        np.where(df["hrv_rmssd_ms"] < 40, "Fatiga Moderada", "Óptimo")
    )
    
    # 3. Environmental Hazard Score
    # CO2 normal cabina ISS: 2500-3500 ppm; Radiación normal: 15-25 uSv/h
    co2_risk = np.maximum(0, (df["cabin_co2_ppm"] - 4000) / 500)
    rad_risk = np.maximum(0, (df["radiation_rate_usv_h"] - 35) / 10)
    df["environmental_risk_score"] = (co2_risk + rad_risk).round(2)
    
    # 4. Nivel de Alerta Compuesto
    conditions = [
        (df["cardiovascular_stress_index"] > 4.0) | (df["environmental_risk_score"] > 3.0) | (df["spo2_pct"] < 93.0),
        (df["cardiovascular_stress_index"] > 2.0) | (df["environmental_risk_score"] > 1.5) | (df["hrv_rmssd_ms"] < 25.0)
    ]
    choices = ["CRÍTICO", "PRECAUCIÓN"]
    df["alert_level"] = np.select(conditions, choices, default="NORMAL")
    
    return df

def generate_crew_summary(df: pd.DataFrame) -> dict:
    """Genera métricas consolidadas para el reporte de cabina."""
    summary = {}
    for crew_id, group in df.groupby("crew_id"):
        # Horas que representa cada registro de ESTE astronauta (los registros de la tripulación se intercalan)
        dt_h = group["timestamp"].diff().dt.total_seconds().div(3600)
        dt_h = dt_h.fillna(dt_h.median())
        summary[crew_id] = {
            "registros_totales": len(group),
            "fc_promedio": round(group["heart_rate_bpm"].mean(), 1),
            "spo2_promedio": round(group["spo2_pct"].mean(), 1),
            "hrv_promedio": round(group["hrv_rmssd_ms"].mean(), 1),
            "alertas_criticas": int((group["alert_level"] == "CRÍTICO").sum()),
            "alertas_precaucion": int((group["alert_level"] == "PRECAUCIÓN").sum()),
            "dosis_acumulada_radiacion_usv": round((group["radiation_rate_usv_h"] * dt_h).sum(), 1)
        }
    return summary

if __name__ == "__main__":
    import sys
    data_file = "data/sample_astronaut_telemetry.csv"
    if len(sys.argv) > 1:
        data_file = sys.argv[1]
    print(f"[BioOrbit Pipeline] Procesando telemetría desde: {data_file}")
    telemetry = load_telemetry(data_file)
    processed = calculate_health_scores(telemetry)
    summary = generate_crew_summary(processed)
    print("\n=== RESUMEN DE SALUD DE TRIPULACIÓN ===")
    for crew, stats in summary.items():
        print(f"Astronauta {crew}:")
        for k, v in stats.items():
            print(f"  - {k}: {v}")
    print("\n[BioOrbit Pipeline] Procesamiento completado con éxito.")