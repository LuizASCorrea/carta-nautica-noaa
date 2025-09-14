# Carta Náutica NOAA 🌊

Mapa interativo em Leaflet que mostra todas as boias do NOAA/NDBC,
com backend Flask que atua como proxy para dados públicos do NOAA.

## Rodar localmente

### Backend
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install flask requests
python noaa_backend.py
