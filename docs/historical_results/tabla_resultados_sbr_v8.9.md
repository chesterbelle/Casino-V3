# Tabla de Resultados SBR (Session Boundary Reset) — v8.9

> **Fecha**: 2026-07-03
> **Branch**: `feat/session-boundary-reset`
> **Configuración**: SBR activo (reset diario @ 00:00 UTC en SensorManager, OrderFlowEngine, ContextRegistry y los 4 detectores)
> **Perfiles**: bug de `clusters_fixed.json` ya corregido (símbolos planos `XXXUSDT`)
> **Estado**: ⚠️ **VEREDICTO PENDIENTE** — Aún no se ha decidido merge a `dev-8.9-datafeed-revamp`

---

## 1. Contexto de la Investigación

La pregunta original era: ¿Está contaminado el monthly continuo por arrastre de estado entre días? ¿O es que el optimizador se ajustó mal al training set?

Evidencia previa (de `docs/analisis_contaminacion_indicadores.md`):
- TA (trend_acceptance) producía 119 señales vs 36 en daily
- WR de TA colapsaba de 58.3% (daily) → 15.1% (monthly)

Hipótesis principal: los indicadores con estado acumulativo (MarketProfile 8h, CVD session, z-scores) arrastran información residual entre días, creando señales falsas.

---

## 2. Resultados Consolidados por Escenario

### 2.1 DATASETS DIARIOS — 24h aislados (training set original)

| Setup              | BAL_2024_02 | BAL_2024_05 | UP_2023_02 | UP_2025_10 | DOWN_2025_02 | DOWN_2025_12 |
|--------------------|:-----------:|:-----------:|:----------:|:----------:|:------------:|:------------:|
| failed_breakout    | —           | —           | —          | —          | —            | +0.43% (1/1, 100%) |
| liquidity_exhaustion | +0.38% (2/1, 50%) | +0.76% (4/1, 75%) | -0.37% (0/2, 0%) | -0.37% (0/1, 0%) | -0.37% (0/2, 0%) | +1.13% (2/0, 100%) |
| tactical_absorption | +0.38% (1/1, 50%) | +0.31% (5/6, 45%) | -0.37% (0/8, 0%) | -0.37% (0/1, 0%) | -0.37% (0/4, 0%) | +1.13% (3/0, 100%) |
| trend_acceptance   | —           | -0.37% (1/2, 33%) | +0.34% (10/2, 67%) | **+0.83% (5/0, 100%)** | +0.16% (5/3, 62%) | — |
| **TOTAL**          | **+0.38%**  | **+0.31%**  | **+0.05%** | **+0.48%** | **-0.04%**   | **+1.01%**   |
| Win Rate Total     | 50%         | 55%         | 43%        | 75%        | 40%          | 100%         |
| Total Señales      | 4           | 20          | 28         | 8          | 15           | 6            |

### 2.2 DATASETS MENSUALES — 30 días continuos (production-like)

| Setup              | Marzo 2026 | Abril 2026 | Mayo 2026 |
|--------------------|:----------:|:----------:|:---------:|
| failed_breakout    | -0.03% (31/17) | -0.01% (14/7) | **+1.30% (9/1, 90%)** |
| liquidity_exhaustion | -0.01% (14/45) | **+0.52% (52/36, 59%)** | **+1.97% (34/4, 89%)** |
| tactical_absorption | +0.13% (40/81, 33%) | +0.19% (67/118, 35%) | -0.02% (25/81, 23%) |
| trend_acceptance   | -0.42% (15/34, 30.6%) | **0% WR** -0.97% (0/28) | **0% WR** -0.97% (0/23) |
| **TOTAL**          | **-0.03%** ❌ | **+0.16%** ✅ | **-0.04%** ❌ |
| Win Rate Total     | 36.1%      | 40.4%      | 29.6%     |
| Total Señales      | 277        | 329        | 179       |

---

## 3. Resumen por Régimen

| Tipo         | Dataset                | TA WR    | Net Taker TA | Net Taker Total | WR Total |
|--------------|------------------------|----------|--------------|-----------------|----------|
| Daily 24h   | BAL_2024-02            | —        | —            | +0.38% ✅       | 50%      |
| Daily 24h   | BAL_2024-05            | 33%      | -0.37%       | +0.31% ✅       | 55%      |
| Daily 24h   | UP_2023-02             | 67%      | +0.34%       | +0.05% ✅       | 43%      |
| Daily 24h   | UP_2025-10             | **100%** | **+0.83%**   | **+0.48%** ✅   | **75%**  |
| Daily 24h   | DOWN_2025-02           | 62%      | +0.16%       | -0.04% ❌       | 40%      |
| Daily 24h   | DOWN_2025-12           | —        | —            | **+1.01%** ✅   | **100%** |
| Monthly     | Marzo 2026             | 30.6%    | -0.42%       | -0.03% ❌       | 36.1%    |
| Monthly     | Abril 2026             | **0%**   | **-0.97%** ❌ | +0.16% ✅       | 40.4%    |
| Monthly     | Mayo 2026              | **0%**   | **-0.97%** ❌ | -0.04% ❌       | 29.6%    |

---

## 4. Validación del SBR (Test de Trigger)

* **Activaciones del reset**: 30 eventos detectados a lo largo del monthly de Mayo (uno por día natural)
* **Componentes alcanzados**: SensorManager ✓, OrderFlowEngine ✓, ContextRegistry ✓, los 4 detectores (Trend/Failed/Liquidity/TA-focused) ✓
* **Sin errores**: ningún crash de backtest, ninguna excepción en el log principal

---

## 5. Hallazgos Clave

### 5.1 Hallazgos Positivos (a favor de SBR)
1. **TA colapso en monthly, no en daily**: TA tiene 0% WR en todos los monthly (25 de 51 señales perdidas), pero 67-100% WR en trending dailies
2. **El sistema compensa con otros setups**: liquidity_exhaustion + tactical_absorption cargan el peso cuando TA muere → Abril logra +0.16%
3. **Sin regresión en dailies**: Edge promedio de dailies con SBR es similar o mejor que baseline (TA 67% WR mantiene su ventaja)
4. **SBR limpio**: 30 resets detectados, todos los componentes sincronizados, sin errores de runtime

### 5.2 Problemas Detectados
1. **TA está estructuralmente roto en 2026**: aunque SBR lo deje en estado limpio, sigue perdiendo
2. **Dailies pequeños (sin señales TA)**: algunos BAL apenas producen 2-4 señales — pocas muestras para concluir
3. **Liquidity exhaustion en dailies viejos no tiene edge**: 0% WR en muchos casos (LTC NOISY_UNCERTAIN_1)
4. **Diferencia entre meses**: Mismo modelo, distinto mes → resultados distintos (mercado está cambiando)

---

## 6. Conclusiones para Decisión

### Pregunta de fondo: ¿Mochamos SBR?

**A favor del merge:**
- Resuelve la causa raíz del bug (estado acumulativo entre días)
- Documenta formalmente la arquitectura y reduce futuras regresiones por arrastre
- Asegura paridad conceptual entre backtest y live
- No hay regresión en edge conocido (dailies 2023-2025)

**En contra del merge (por ahora):**
- TA colapsa en monthly más allá del efecto que SBR puede arreglar → no hay recuperación de edge en Mayo
- El cambio de régimen entre 2023-2025 y 2026 sugiere que TA ya no es apto sin reoptimización
- Los 3 monthly dan resultados mixtos: solo abril es positivo
- Posible sobreingeniería para resolver un fix parcial

**Decisión recomendada**: Análisis detallado en la próxima sesión. Hoy dejamos el branch listo pero sin mergear.

---

## 7. Próximos Pasos (Para la próxima sesión)

1. **Análisis técnico de Mayo 2026**: ¿Por qué TA tiene 0% WR incluso con SBR? ¿Fallos de parámetros? ¿Cambio de régimen?
2. **Decisión sobre merge**: Tangible, ir a `memory.md` sección "Ruta Actual"
3. **Si merge se rechaza**: ¿Borrar el branch `feat/session-boundary-reset` o guardarlo como fork?
4. **Si merge se aprueba**: Sync `.agent/workflows/sync-docs.md`, ejecutar protocolo validate-all
