# Casino-V3 ROADMAP: De la Infraestructura al Alpha 🗺️💎

Este roadmap define el camino hacia la rentabilidad institucional mediante una **Ingeniería de Validación Continua**. Abandonamos el concepto de "Fases" cronológicas en favor de **Capas de Certificación**.

---

## 🏛️ CAPA DE HIERRO: Infraestructura de Grado Institucional
**ESTADO: [COMPLETADA] (v5.2.0-parity-certified)**
La armadura del bot. Nuestra prioridad fue asegurar que el bot no pierda dinero por errores de código.

- [x] **Paridad Mecánica 1:1**: Lograda el 2026-04-09. Demo y Backtest son idénticos.
- [x] **Resiliencia del Historian**: Eliminación del 'Silent Skip'. Trazabilidad total de trades.
- [x] **Pipeline HFT (T0-T2 < 50ms)**: Latencia ultra-baja en la toma de decisiones.
- [x] **Atomic OCO Brackets**: Gestión perfecta de órdenes vinculadas (TP/SL).

---

## 💎 CAPA DE CRISTAL: Validación del Alpha
**ESTADO: [ENFOQUE ACTUAL]**
La espada del bot. El objetivo es auditar la lógica de trading para asegurar que el bot gane dinero de forma orgánica.

- [ ] **Auditoría de Estrategia (Quick Scalping)**: Probar la lógica central contra los Golden Datasets.
- [ ] **Búsqueda del Edge Positivo**:
    - Objetivo: Win Rate ≥ 55% | Profit Factor ≥ 1.2.
- [ ] **Análisis MAE / MFE**: Optimización de TP y SL basada en el recorrido real del precio.
- [ ] **Refinamiento de Micro-Exits**: Mejorar la salida ante señales de absorción o secado de liquidez.

---

## ⚔️ CAPA DE ACERO: Resiliencia y Escalado
**ESTADO: [A FUTURO]**
El escudo del bot. Proteger el capital una vez que el Alpha ha sido verificado.

- [ ] **Continuous Certification Pipeline**: Integración de todos los workflows en un sistema de auto-auditoría.
- [ ] **PortfolioGuard V2**: Fusibles por latencia, volatilidad y rachas de pérdida.
- [ ] **Exploración DEX (Hyperliquid)**: Migrar el motor a entornos con menor riesgo de contraparte.

---
> **MANTRA DE ESTA SESIÓN:** No más ingeniería de infraestructura. Solo validación de Alpha.
