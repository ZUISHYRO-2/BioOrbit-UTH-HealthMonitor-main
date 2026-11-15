"""NASA DONKI space-weather events and local research-dataset imports."""

from __future__ import annotations

import csv
import os
from datetime import date
from typing import Any, BinaryIO, Dict, List, Optional

import pandas as pd
import requests

DONKI_SEP_URL = "https://api.nasa.gov/DONKI/SEP"
REQUEST_TIMEOUT = (3.05, 15.0)


def parse_sep_events(payload: Any) -> List[Dict[str, str]]:
    """Validate and normalize NASA DONKI solar energetic particle events."""
    if not isinstance(payload, list):
        raise ValueError("La respuesta NASA SEP debe ser una lista de eventos.")

    events = []
    for item in payload:
        if not isinstance(item, dict):
            raise ValueError("La respuesta NASA SEP contiene un evento inválido.")
        event_id = item.get("sepID")
        event_time = item.get("eventTime")
        if not isinstance(event_id, str) or not isinstance(event_time, str):
            raise ValueError("Un evento NASA SEP no incluye sepID o eventTime.")

        instruments = item.get("instruments") or []
        if not isinstance(instruments, list):
            raise ValueError(f"El campo instruments no es válido en {event_id}.")
        instrument_names = [
            instrument["displayName"]
            for instrument in instruments
            if isinstance(instrument, dict) and isinstance(instrument.get("displayName"), str)
        ]
        events.append({
            "ID": event_id,
            "Fecha UTC": event_time,
            "Instrumentos": ", ".join(instrument_names) or "No especificado",
            "Ficha NASA": str(item.get("link") or ""),
        })

    return sorted(events, key=lambda event: event["Fecha UTC"], reverse=True)


def fetch_sep_events(
    start_date: str,
    end_date: str,
    api_key: Optional[str] = None,
) -> List[Dict[str, str]]:
    """Fetch NASA DONKI solar energetic particle events for an inclusive date range."""
    try:
        start = date.fromisoformat(start_date)
        end = date.fromisoformat(end_date)
    except (TypeError, ValueError) as exc:
        raise ValueError("Las fechas deben tener el formato YYYY-MM-DD.") from exc
    if start > end:
        raise ValueError("La fecha inicial no puede ser posterior a la fecha final.")

    key = api_key or os.getenv("NASA_API_KEY") or "DEMO_KEY"
    response = requests.get(
        DONKI_SEP_URL,
        params={"startDate": start.isoformat(), "endDate": end.isoformat(), "api_key": key},
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    return parse_sep_events(response.json())


def read_reference_dataset(file: BinaryIO) -> pd.DataFrame:
    """Read an uploaded comma- or tab-delimited research dataset for inspection."""
    try:
        dataset = pd.read_csv(file, sep=None, engine="python")
    except (csv.Error, pd.errors.ParserError, pd.errors.EmptyDataError, UnicodeDecodeError, ValueError) as exc:
        raise ValueError("No se pudo leer el archivo. Sube un CSV o TSV válido.") from exc

    if dataset.empty or len(dataset.columns) == 0:
        raise ValueError("El archivo no contiene filas de datos.")
    return dataset
