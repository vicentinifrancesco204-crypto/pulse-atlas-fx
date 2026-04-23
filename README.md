# Pulse Atlas FX

Web app FastAPI per leggere:

- solo EUR/USD e GBP/USD
- bias generale live
- bias intraday live
- intraday AI analysis live con liquidity targets del giorno
- home pulita con bias e AI analysis in evidenza
- cartelle cliccabili per live market, London playbook, storico e finestre future
- spike di volatilita gia avvenuti su 1m e 5m
- finestre future in cui potrebbero ripetersi scatti simili
- London playbook 09:00-10:00 Rome con range medio 30d e liquidity zones

## Avvio locale

```bash
python -m uvicorn app:app --host 0.0.0.0 --port 8000
```

Poi apri `http://127.0.0.1:8000`.

## Deploy

L'app e pronta per host Python come Render, Railway, Fly.io o Docker.

- comando start: `uvicorn app:app --host 0.0.0.0 --port $PORT`
- dipendenze: in `requirements.txt`
- container: `Dockerfile`
- health check: `/healthz`
- blueprint Render: `render.yaml`

## Feed usati

- prezzi forex live: Yahoo Finance chart feed
- calendario macro: Forex Factory weekly JSON

## Nota

Il catalogo futuro e probabilistico: segnala finestre in cui il contesto live rende plausibili nuovi spike, non direzione garantita.
