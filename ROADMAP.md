# Casino-V3 Roadmap 🗺️⚡

Este documento existe para **preservar el contexto a largo plazo** y asegurar que el desarrollo no pierda el rumbo debido a límites de memoria en las sesiones de IA.

---

## ✅ Completado Recientemente (Status actual)
- **Fase 300**: HFT Latency Optimization (5.4ms T0-T2).
- **Fase 400**: Footprint Scalping Pipeline (Ingesta de Ticks y sensores Live).
- **Fase 500**: Project Supersonic Stabilization (OCOs atómicos, $0.00 Error Leakage, validado 150 min).
- **Fase 600**: Footprint Scalping Optimization (Dale & Dalton Integration).
   - Implementado *Value Area* (VAH/VAL/POC) usando la regla del 70% de James Dalton (`core/market_profile.py`).
   - Sensores `imbalance.py` y `absorption.py` enriquecidos con métricas de intensidad y densidad de *Volume Clusters* (Trader Dale).
   - TP y SL dinámicos y contextuales integrados en el `AdaptivePlayer` basados en Market Profile.
   - **(NUEVO)** Validación en vivo exitosa: Motores HFT, Airlock, y OCO brackets ejecutando órdenes `fast_track` en base al Footprint sn errores.

---

## 🚀 Siguiente Paso Inmediato: Fase Continua 650 (Footprint Strategy Tuning)

El objetivo primario **NO ES AÑADIR NUEVAS FUNCIONALIDADES**, sino hacer que el bot **GANE DINERO**. La infraestructura de ejecución (Fases 100-500) ya es robusta y sin latencia. Hemos implementado la lógica base del Footprint (PCA, divergencia delta, *unfinished business* y *DOM Wall confirmation*). Ahora entramos en el ciclo iterativo de ajuste y backtesting hacia la rentabilidad real.

**No abandonaremos esta fase hasta tener una estrategia con Edge Positivo (Win Rate > 55% / Profit Factor > 1.2).**

### Roadmap Iterativo de Rentabilidad:
1. **[EN PROCESO] Recolección de Data & Forward-Testing (Demo)**
   - Corriendo el Validation Pipeline y preparándonos para forward testing en vivo.
   - Extraer estadísticas puras de los "Volume Clusters" y "Stacked Imbalances".
2. **Refinamiento de Filtros de Entrada**
   - Cruzar las señales de Imbalance con el VAH/VAL. (Ejemplo: Solo tomar longs de Imbalance si ocurren *dentro* del Value Area cruzando el POC hacia arriba).
   - Ajustar los parámetros sensibles (`min_cluster_density`, umbrales de delta).
3. **Auditoría de Exits (Shadow SL / Dynamic TP)**
   - Revisar si el High-Frequency Breakeven nos está sacando de los trades ganadores demasiado pronto.
   - Estudiar el recorrido máximo del precio (MFE) vs la pérdida máxima (MAE) por cada trade para afinar el % de TP/SL.
4. **Validación de la Hipótesis del Trader Dale**
   - Confirmar si la rotación del "Order Book Flow" seguida de una absorción realmente precede a expansiones del precio de al menos 3-5 ticks, lo cual es vital para el HFT local.

---

## 🔮 Fases Futuras (Post-Rentabilidad)
- **Fase 700**: Machine Learning Layer - Una vez que tengamos un baseline rentable, usar ML para predecir cuándo la estrategia tradicional de Footprint va a fallar (Filtro de régimen de mercado).
- **Fase 800**: Hyperliquid (DEX) - Ya con un modelo de negocio rentable, migrar la capa de ejecución (Fase 100-500) a Web3 para reducir el riesgo de contraparte de Binance.
