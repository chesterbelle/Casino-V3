# Casino-V3 Roadmap 🗺️⚡

Este documento existe para **preservar el contexto a largo plazo** y asegurar que el desarrollo no pierda el rumbo debido a límites de memoria en las sesiones de IA.

---

## ✅ Completado Recientemente (Status actual)
- **Fase 300**: HFT Latency Optimization (5.4ms T0-T2).
- **Fase 400**: Footprint Scalping Pipeline (Ingesta de Ticks y sensores Live).
- **Fase 500**: Project Supersonic Stabilization (OCOs atómicos, $0.00 Error Leakage, validado 150 min).

---

## 🚀 Siguiente Paso Inmediato: Fase 600 - Footprint Scalping Optimization

El objetivo es aprovechar el motor de ejecución HFT recién estabilizado para reaccionar a la micro-estructura del OrderBook con los sensores de Footprint.

### 1. Ajuste de Estrategias y Jugadores (`config/strategies.py`, `players/adaptive.py`)
- Apagar estrategias lentas (ej. `QuickScalper`, `MACD`).
- Activar única y exclusivamente la estrategia **`FootprintScalper`**.
- Implementar en el Player la capacidad de leer metadatos de intensidad del Footprint para ajustar dinámicamente el tamaño del TP (Take Profit).

### 2. Afinar Sensores de Microestructura (`sensors/footprint/`)
- Módulo **`imbalance.py`**: Añadir metadatos ricos (`avg_ratio`, `total_imbalance_volume`). Inyectar el flag `fast_track=True` para que el `Aggregator` se salte los delays estáticos y dispare la señal en menos de 5ms.
- Módulo **`absorption.py`**: Añadir indicador de `absorption_intensity`. También con `fast_track=True`.

### 3. Validación de Estrategia
- Correr el bot en `MULTI` mode.
- Analizar `human.log` para confirmar que los "Footprint Triggers" son dominantes y generan *micro-scalps* ganadores usando el motor supersónico.

---

## 🔮 Fases Futuras (Ideas en backlog)
- **Fase 700**: Machine Learning Layer - Predicción de volatilidad a corto plazo usando los deltas del Footprint.
- **Fase 800**: Integración de Hyperliquid (DEX) usando la misma arquitectura HFT.
