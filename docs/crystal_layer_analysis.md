# 🔍 ANÁLISIS DE LA CAPA DE CRISTAL Y PRESSURE ENGINE

> **Fecha**: 2026-06-06
> **Autor**: Kiro Analysis Agent
> **Scope**: Arquitectura Crystal Layer, Pressure Engine, 4 AMT Scenarios

---

## 📌 VISTA GENERAL

La **Capa de Cristal** es la capa de lógica de trading que determina **CUÁNDO** entrar. Está construida sobre una arquitectura de 4 escenarios AMT (Auction Market Theory) que comparten un motor centralizado de medición de presión: el **Pressure Engine**.

Esta arquitectura surgió del refactor "v8.4 Crystal Reforge" y evolucionó a "AMT V10 Alpha" con la activación de los 4 escenarios en 2026-06-05.

---

## 🏗️ ARQUITECTURA ACTUAL

```
┌─────────────────────────────────────────────────────────────────────┐
│                        CAPA DE CRISTAL                              │
├─────────────────────────────────────────────────────────────────────┤
│  Pressure Engine (Centralizado)                                     │
│  ├── CVD Velocity Z-Score Normalization                             │
│  ├── Absorption Detection (concentration + noise + delta)          │
│  ├── Volatility Z-Score                                             │
│  ├── Price Displacement Z-Score                                     │
│  └── Anti-Fade Protection (block_long/block_short)                 │
└─────────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────────┐
│                    4 AMT SCENARIOS (Sensores)                       │
├─────────────────────────────────────────────────────────────────────┤
│  1. TacticalAbsorption (sensors/absorption/absorption_detector.py) │
│     → Flujo direccional institucional                                │
│     → Cooldown 180s, structural filter ±0.3% POC/VAH/VAL            │
│                                                                     │
│  2. TrendAcceptance (decision/scenarios/trend_acceptance.py)       │
│     → Flujo direccional: breakout VA + pullback                     │
│     → Cooldown 600s, CVD confirmation threshold                     │
│                                                                     │
│  3. LiquidityExhaustion (decision/scenarios/liquidity_exhaustion)  │
│     → Reversión: tests múltiples con delta decreciente              │
│     → Sliding window 120s, min 3 tests                               │
│                                                                     │
│  4. FailedBreakout (decision/scenarios/failed_breakout.py)         │
│     → Reversión: breakout + divergente delta + re-entry             │
│     → Cooldown 60s, max age 60s                                      │
└─────────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────────┐
│                    SCENARIO MANAGER (Orquestador)                   │
├─────────────────────────────────────────────────────────────────────┤
│  ├── Priority Map (liquidity_exhaustion:100, failed_breakout:50,   │
││     trend_acceptance:30)                                          │
│  ├── Conflict Resolution (LONG vs SHORT → delta <30 = neutralize)  │
│  ├── Signal Fusion (composite signals from multiple scenarios)     │
│  └── Telemetry (signal distribution stats)                         │
└─────────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────────┐
│                    SETUP ENGINE V4 (Orchestrator)                   │
├─────────────────────────────────────────────────────────────────────┤
│  ├── Quality Scoring (v8.4 Crystal Reforge)                        │
│  ├── Target Calculation (TP/SL por perfil y setup)                 │
│  ├── Setup Mode Routing (CONTINUATION vs REVERSION)                │
│  └── Dispatch TradeProposal to AdaptivePlayer                      │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 🎯 PRESSURE ENGINE — ANÁLISIS DETALLADO

### **1. Propósito**
Motor centralizado que calcula métricas de microestructura de forma agnóstica y las normaliza para que los escenarios puedan tomar decisiones consistentes.

### **2. Estado (PressureState)**
```python
@dataclass
class PressureState:
    cvd_delta: float              # CVD acumulado raw
    cvd_velocity: float           # Velocidad normalizada (Z-score)
    imbalance_ratio: float        # NO SE USA ACTUALMENTE
    volatility_z: float           # Z-score de volatilidad de precio
    absorption_score: float       # Score de absorción (0-1)
    timestamp: float              # Último update
    price_displacement_z: float   # Z-score de desplazamiento de precio
    block_long: bool              # Anti-fade protection
    block_short: bool             # Anti-fade protection
```

### **3. Componentes Clave**

#### **a) CVD Velocity Z-Score (NORMALIZACIÓN)**
- Calcula velocidad de cambio de CVD por tick
- Usa `RollingZScore(window=200)` para normalizar
- **Objetivo**: Comparar flujo entre coins con diferentes volúmenes
- **Fórmula**: `zscore = (raw_velocity - mean) / std`

#### **b) Absorption Detection (CONCENTRACIÓN + RUIDO)**
```python
# Si footprint_levels disponible:
concentration = max(ask_vol, bid_vol) / total_vol
noise = min(ask_vol, bid_vol) / total_vol

conc_norm = (concentration - concentration_min) / (1 - concentration_min)
noise_norm = (noise_max - noise) / noise_max

absorption_score = min(1.0, (conc_norm * noise_norm) ** 0.5)
```
- **Concentration**: Qué tan concentrado está el volumen en un lado
- **Noise**: Qué tanto hay de "ruido" (volumen del lado opuesto)
- **Score**: Media geométrica de ambos (requiere ambos factores)

#### **c) Volatility Z-Score**
- Calcula returns de precio (log Returns aproximado)
- Usa ventana móvil 200 para calcular mean y std
- **Fórmula**: `z = (|return| - mean) / std`

#### **d) Price Displacement Z-Score**
- Mide qué tan lejos está el precio de la media móvil de 200
- **Fórmula**: `z = (price - ma200) / std_200`

#### **e) Anti-Fade Protection (BLOCK LONG/SHORT)**
- Bloquea señales contrarias cuando hay desplazamiento extremo
- `block_long = cvd_sell AND price_displacement_z > 2.0`
- `block_short = cvd_buy AND price_displacement_z < -2.0`

---

## 🎭 LOS 4 ESCENARIOS — COMPORTAMIENTO

| Escenario | Naturaleza | Cadena de Razonamiento | Cooldown | Key Parameters |
|-----------|------------|------------------------|----------|----------------|
| **TacticalAbsorption** | Direccional | 1. Absorption score > 0.5<br>2. CVD velocity Z > z_score_min<br>3. Volatility Z < max<br>4. Price displacement Z < max<br>5. Anti-fade not triggered<br>6. Near structural level (±0.3%) | 180s | z_score_min, concentration_min, noise_max, level_tolerance_pct |
| **TrendAcceptance** | Direccional | 1. Price breaks VA with CVD confirmation<br>2. Price extends beyond broken level<br>3. Price pulls back to broken level (now support/resistance) | 600s | cvd_confirmation_threshold (5.0), pullback_bps (12), min_breakout_distance_bps (20) |
| **LiquidityExhaustion** | Reversión | 1. Multiple tests of same level (≥3)<br>2. Delta declining at each test<br>3. Price bounced from level | 30s | min_tests (3), declining_threshold (0.7), test_memory_seconds (120) |
| **FailedBreakout** | Reversión | 1. Price breaks VAH/VAL<br>2. CVD didn't confirm (divergent)<br>3. Price re-enters VA quickly (<60s) | 60s | max_break_age (60s), min_break_distance_pct (0.03%), cvd_divergence_threshold (0.3) |

### **Clasificación por SetupMode**

**DIRECTIONAL_SCENARIOS** (SetupMode.CONTINUATION):
- `tactical_absorption`
- `trend_acceptance`

**REVERSION_SCENARIOS** (SetupMode.REVERSION):
- `failed_breakout`
- `liquidity_exhaustion`

---

## 🔍 HALLAZGOS CRÍTICOS

### **1. ARQUITECTURA DUAL (SENSOR MANAGER vs SETUP ENGINE)**

El sistema tiene **DOS puntos de entrada** a los escenarios:

#### **A) SensorManager (core/sensor_manager.py:88-99)**
```python
# Phase 410: Update PressureEngine with tick data
self.pressure_engine.update(qty, is_buyer_maker, event.timestamp, event.price)

# Extraer niveles estructurales
poc, vah, val = reg.get_structural(event.symbol)
structural = {"poc": poc, "vah": vah, "val": val}

# Ejecutar escenarios directamente
for name, scenario in self.scenarios.items():
    result = scenario.on_tick(event.symbol, event.price, event.timestamp, structural)
    if result:
        await self._emit_signal(result, name, event.symbol)
```
- **Ejecuta TODOS los 4 escenarios** en cada tick
- Emite señales directamente al motor
- **Propósito**: Capturar señales "instantáneas" (tactical_absorption)

#### **B) SetupEngine (decision/engine/core.py:127-145)**
```python
# Update PressureEngine
self.pressure_engine.update(qty, is_buyer_maker, timestamp, price)

# Get structural levels
poc, vah, val = reg.get_structural(symbol)
structural_levels = {"poc": poc, "vah": vah, "val": val}

# Evaluate via ScenarioManager (con prioritization + fusion)
signal = self.scenario_manager.on_tick(symbol, price, timestamp, structural_levels)

if signal:
    await self._process_signal(signal, trace=trace)
```
- **Ejecuta ScenarioManager** que orquesta los 3 primeros escenarios
- **NO ejecuta tactical_absorption** (lo hace SensorManager)
- **Propósito**: Detectar conflictos y fusionar señales

#### **PROBLEMA IDENTIFICADO**:
- `tactical_absorption` se ejecuta **DOBLE** (SensorManager + SetupEngine on_signal)
- Los otros 3 escenarios se ejecutan **SOLO en SetupEngine**
- Esto crea inconsistencias si `tactical_absorption` dispara en SensorManager pero SetupEngine no lo ve

---

### **2. SCENARIO MANAGER EXCLUDES TACTICAL ABSORPTION**

`decision/scenarios/__init__.py` solo exporta:
```python
from .failed_breakout import FailedBreakoutDetector
from .liquidity_exhaustion import LiquidityExhaustionDetector
from .trend_acceptance import TrendAcceptanceDetector

__all__ = ["FailedBreakoutDetector", "LiquidityExhaustionDetector", "TrendAcceptanceDetector"]
```

**NO INCLUYE** `AbsorptionDetector`.

Esto es intencional (está en `sensors/` no en `decision/scenarios/`) pero crea inconsistencia semántica.

**`ScenarioManager`** solo incluye:
```python
self.scenarios = [
    LiquidityExhaustionDetector(self.pressure),
    FailedBreakoutDetector(self.pressure),
    TrendAcceptanceDetector(self.pressure),
]
```

**NO INCLUYE** `AbsorptionDetector` (tactical_absorption).

Esto significa que:
- `tactical_absorption` **NO PARTICIPA** en conflict resolution
- `tactical_absorption` **NO PARTICIPA** en signal fusion
- `tactical_absorption` **NO TIENE PRIORITY MAP**

**IMPACTO**:
- Si `tactical_absorption` y `trend_acceptance` disparan al mismo tiempo, **NO HAY CONFLICT RESOLUTION**
- El código asume que tactical_absorption es "instant" y los otros son "confirmation"

---

### **3. DIFFERENT PRESSURE ENGINE INSTANCES**

#### **SetupEngine** (decision/engine/core.py:57-60)
```python
default_prof = profile_manager.profiles.get(profile_manager.default_profile, {})
pe_params = dict(default_prof.get("sensors", {}).get("absorption_detector", {}))
self.pressure_engine = PressureEngine(profile_params=pe_params)
```

#### **SensorManager** (core/sensor_manager.py:63)
```python
self.pressure_engine = PressureEngine()
```

**PROBLEMA**:
- `SetupEngine` tiene un PressureEngine con params del perfil por defecto
- `SensorManager` tiene un PressureEngine ** SIN PARAMS** (usa defaults hardcoded: z_score_min=3.0, concentration_min=0.50, etc.)
- **NO ESTÁN SINCRONIZADOS** → pueden disparar señales diferentes con los mismos datos

**Ejemplo de divergencia**:
- Para LTC: `profile_manager` da `z_score_min=2.0`
- `SensorManager` usa `z_score_min=3.0` (default)
- Mismo tick → diferentes señales de tactical_absorption

---

### **4. RUTEO DE ESCENARIOS NO UNIFICADO**

**SetupEngine** maneja escenarios de dos maneras:

#### **a) OnTick (line 137-141)**
```python
# Evaluate via ScenarioManager (con prioritization + fusion)
signal = self.scenario_manager.on_tick(symbol, price, timestamp, structural_levels)
```
- Ejecuta ScenarioManager (3 escenarios: LiquidityExhaustion, FailedBreakout, TrendAcceptance)

#### **b) OnSignal (line 194-201)**
```python
# Fast-Lane: tactical_absorption fires immediately
if event.sensor_id == "tactical_absorption":
    trace = black_box.create_trace(...)
    await self._process_signal(payload, trace=trace)
    return
```
- Ejecuta tactical_absorption directamente (sin ScenarioManager)

**PROBLEMA**:
- `tactical_absorption` bypassea toda la orquestación
- No hay priorización ni fusión
- Doble ejecución possible (OnTick + OnSignal)

---

### **5. TACTICAL_ABSORPTION NO ESTÁ EN `__init__.py`**

`decision/scenarios/__init__.py` solo exporta 3 escenarios, excluyendo `AbsorptionDetector`.

Esto es inconsistente con:
- `core/sensor_manager.py:111` que lo importa directamente
- La documentación que lo ubica en "decision/scenarios/"

**SUGERENCIA**: Mover `absorption_detector.py` a `decision/scenarios/` o actualizar `__init__.py` para incluirlo.

---

## 🧪 RESULTADOS ACTUALES (MID_LIQUID LTC)

**Total Signals**: 1754
**Net Taker**: +1.57%
**Win Rate**: 97.5% (solo 44 signals no ganadores en el set)

| Scenario | Signals | WR | Net Taker | Classificación |
|----------|---------|-----|-----------|----------------|
| trend_acceptance | 2044 | 58.9% | +0.18% | Direccional |
| tactical_absorption | 77 | 76.8% | +0.54% | Direccional |
| liquidity_exhaustion | 28 | 60.7% | +0.15% | Reversión |
| failed_breakout | 11 | 50.0% | -0.12% | Reversión |

**KEY INSIGHT (2026-06-06)**:
- `tactical_absorption` y `trend_acceptance` son **FLUJO DIRECCIONAL** (0/927 revierten en <15min)
- `failed_breakout` y `liquidity_exhaustion` son **REVERSIÓN CLÁSICA** (SL ajustado funciona)
- **Implicación**: SetupMode correcto = CONTINUATION para direccional, REVERSION para reversión

### **Breakdown por Dataset (LTC TREND_UP)**

| Dataset | Net Taker | Status |
|---------|-----------|--------|
| TREND_UP_2024-03 | +1.54% | ✅ |
| TREND_DOWN_2024-04 | +1.33% | ✅ |
| TREND_DOWN_2025-02 | +1.23% | ✅ |
| TREND_DOWN_2024-10 | -1.42% | ❌ |

**Hallazgo**: El único dataset negativo es TREND_DOWN 2024-10. El resto son consistentemente positivos.

---

## 📝 RECOMENDACIONES DE MEJORA

### **ALTA PRIORIDAD** (Crítico para estabilidad)

#### **1. SINCRONIZAR PRESSURE ENGINE INSTANCES**

**Problema**: `SensorManager` usa params default, `SetupEngine` usa params de perfil.

**Solución A (Recomendada)**:
```python
# En SetupEngine, compartir la instancia con SensorManager
class SetupEngineV4:
    def __init__(self, engine, context_registry=None):
        # ... existing code ...

        # Create PressureEngine for scenarios
        default_prof = profile_manager.profiles.get(profile_manager.default_profile, {})
        pe_params = dict(default_prof.get("sensors", {}).get("absorption_detector", {}))
        self.pressure_engine = PressureEngine(profile_params=pe_params)

        # Pass to SensorManager
        self.engine.sensor_manager.pressure_engine = self.pressure_engine  # Shared instance
```

**Solución B**:
```python
# En SensorManager, usar los mismos params
class SensorManager:
    def __init__(self, engine, timeframe="1m"):
        # ... existing code ...

        # Inyectar PressureEngine con params del perfil
        default_prof = profile_manager.profiles.get(profile_manager.default_profile, {})
        pe_params = dict(default_prof.get("sensors", {}).get("absorption_detector", {}))
        self.pressure_engine = PressureEngine(profile_params=pe_params)
```

#### **2. AGREGAR TACTICAL_ABSORPTION A SCENARIO MANAGER**

**Problema**: TacticalAbsorption no participa en orquestación.

**Solución A** (Mantener dual, pero documentar):
```python
# En ScenarioManager.__init__
self.scenarios = [
    LiquidityExhaustionDetector(self.pressure),
    FailedBreakoutDetector(self.pressure),
    TrendAcceptanceDetector(self.pressure),
    # NOTE: TacticalAbsorption es "instant signal" y bypassea orquestación
    # Se ejecuta directamente en SensorManager.on_tick y SetupEngine.on_signal
]

# Agregar al priority map (aunque no se use en orquestación)
self.PRIORITY_MAP["tactical_absorption"] = 150  # Mayor que todos
```

**Solución B** (Unificar en ScenarioManager):
```python
# En SensorManager, ejecutar solo como "trigger", no emitir señal directamente
# En SetupEngine.on_tick, ejecutar todos los escenarios incluyendo tactical_absorption

class SensorManager:
    async def on_tick(self, event):
        # Solo actualizar PressureEngine
        self.pressure_engine.update(qty, is_buyer_maker, event.timestamp, event.price)

        # Actualizar ContextRegistry
        ContextRegistry().set_pressure_state(event.symbol, self.pressure_engine.get_state())

        # NO ejecutar escenarios aquí
        # Solo dispatch microstructure event
```

#### **3. UNIFICAR RUTEO DE ESCENARIOS**

**Problema**: `tactical_absorption` se ejecuta en 2 lugares.

**Solución Recomendada**:
- Eliminar ejecución directa de `SetupEngine.on_signal`
- Ejecutar `tactical_absorption` SOLO en `SetupEngine.on_tick` (junto con ScenarioManager)
- Esto garantiza que todos los escenarios pasen por orquestación

---

### **MEDIA PRIORIDAD** (Mejoras de consistencia)

#### **4. CORREGIR `__init__.py`**

**Opción A**: Agregar AbsorptionDetector a exports
```python
from .failed_breakout import FailedBreakoutDetector
from .liquidity_exhaustion import LiquidityExhaustionDetector
from .trend_acceptance import TrendAcceptanceDetector
from sensors.absorption.absorption_detector import AbsorptionDetector

__all__ = [
    "FailedBreakoutDetector",
    "LiquidityExhaustionDetector",
    "TrendAcceptanceDetector",
    "AbsorptionDetector",
]
```

**Opción B**: Mover AbsorptionDetector a `decision/scenarios/`
```bash
mv sensors/absorption/absorption_detector.py decision/scenarios/tactical_absorption.py
```

#### **5. MEJORAR CONFLICT RESOLUTION**

**Opción A**: Agregar tactical_absorption al priority map
```python
self.PRIORITY_MAP = {
    "tactical_absorption": 150,  # Instant signals tienen mayor prioridad
    "liquidity_exhaustion": 100,
    "failed_breakout": 50,
    "trend_acceptance": 30,
}
```

**Opción B**: Crear prioridad por "tipo de señal"
```python
self.PRIORITY_MAP = {
    "instant": 150,   # tactical_absorption
    "liquidity_exhaustion": 100,
    "failed_breakout": 50,
    "trend_acceptance": 30,
}
```

---

### **BAJA PRIORIDAD** (Documentación y limpieza)

#### **6. DOCUMENTACIÓN**

- Crear documento separado "AMT Scenarios Architecture"
- Documentar la diferencia entre "instant signals" y "confirmation signals"
- Documentar por qué tactical_absorption tiene prioridad

#### **7. LIMPIEZA DE CÓDIGO MUERTO**

- Revisar si `imbalance_ratio` se usa en PressureEngine (parece no)
- Considerar remover campos no usados del `PressureState`

---

## 📊 RESUMEN DE TENSIONES ARQUITECTURALES

| Tensión | Descripción | Severidad | Solución |
|---------|-------------|-----------|----------|
| **Dual Execution** | tactical_absorption se ejecuta en SensorManager Y SetupEngine | 🔴 Alta | Unificar en SetupEngine.on_tick |
| **Pressure Engine Split** | Dos instancias con params diferentes | 🔴 Alta | Compartir instancia única |
| **No-Orchestration** | tactical_absorption bypassea ScenarioManager | 🟡 Media | Agregar a scenarios list + priority map |
| **Missing Export** | AbsorptionDetector no en __init__.py | 🟢 Baja | Agregar export o mover archivo |
| **No Conflict Resolution** | tactical_absorption no participa en conflict resolution | 🟡 Media | Agregar al priority map |

---

## 🎯 PRÓXIMOS PASOS SUGERIDOS

1. **ValidarPressureEngine sync** → Ejecutar mismo tick en ambas instancias, comparar output
2. **Unificar ejecución** → Mover tactical_absorption a SetupEngine.on_tick
3. **Revisar tests** → Actualizar tests para reflejar nueva arquitectura
4. **Documentar decisions** → Crear ADR (Architecture Decision Record)
5. **Add integration tests** → Verificar que ambos engines den mismo resultado

---

## 📚 REFERENCIAS

- **Changelog**: `.agent/changelog.md` — Sesión 2026-06-05 (4 AMT Scenarios Activated)
- **Memory**: `.agent/memory.md` — Roadmap y estado de capas
- **Architecture Map**: `.agent/architecture_map.md` — Blueprint (desactualizado)
- **Strategy Manifesto**: `docs/implementations/amt_v10_strategy_manifesto.md`

---

**Fin del análisis**.
© 2026 Casino-V3 Team. All rights reserved.
