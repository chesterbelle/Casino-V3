# Revisión de Flags del Bot para Absorption V1

## Resumen Ejecutivo

✅ **Todos los flags del bot son compatibles con Absorption V1**

Se identificó y corrigió un problema con `--fast-track` que impedía el testing de infraestructura de Absorption V1.

---

## Flags Revisados

### 1. `--fast-track` ✅ CORREGIDO

**Propósito:** Validación de infraestructura (forzar ejecución en ventanas cortas)

**Problema identificado:**
- LTA V4 bypasea 6 guardians en fast-track mode
- Absorption V1 NO bypasseaba ningún gate → 0 trades en protocolos de validación

**Solución implementada:**
- Agregado `fast_track: bool = False` al `AbsorptionSetupEngine.__init__`
- Bypass en `_check_cvd_flattening()` → permite CVD slope > 5.0
- Bypass en `_check_price_holding()` → permite precio > 0.05% del nivel
- Bypass en `_calculate_tp()` → usa TP mock a 0.20% fijo (no busca LVN)
- Pasado `self.fast_track` desde `SetupEngineV4` al `AbsorptionSetupEngine`

**Archivos modificados:**
- `decision/absorption_setup_engine.py`
- `decision/setup_engine.py`

**Tests:**
- ✅ 8/10 tests passing (2 skipped como esperado)
- ✅ Validator passing (LTA + Absorption V1)

**Documentación:**
- ✅ `.agent/memory.md` actualizado
- ✅ `.agent/FAST_TRACK_ABSORPTION_ANALYSIS.md` creado

---

### 2. `--audit` ✅ COMPATIBLE

**Propósito:** Zero-Interference Audit Mode (validación de edge)

**Funcionamiento:**
- AdaptivePlayer ignora TODAS las señales en audit mode (línea 107-109 en `players/adaptive.py`)
- Señales se registran en Historian pero no se ejecutan
- ExitEngine desactiva layers 4-2 en audit mode (solo logging)

**Compatibilidad con Absorption V1:**
- ✅ **Totalmente compatible** - El bypass es agnóstico a la estrategia
- ✅ Señales de AbsorptionDetector se registran correctamente
- ✅ No requiere cambios

**Uso recomendado:**
```bash
# Backtest con audit mode
.venv/bin/python backtest.py --dataset tests/validation/ltc_24h_audit.csv --audit

# Análisis de edge
.venv/bin/python utils/setup_edge_auditor.py data/historian.db
```

---

### 3. `--close-on-exit` ✅ COMPATIBLE

**Propósito:** Emergency sweep + Drain Phase progresiva

**Funcionamiento:**
- Al final de sesión: cierra todas las posiciones en el exchange
- Con `--timeout`: activa Drain Phase (DEFENSIVE → AGGRESSIVE → PANIC)
- Bloquea nuevas entradas durante Drain Phase

**Compatibilidad con Absorption V1:**
- ✅ **Totalmente compatible** - Opera a nivel de Croupier, agnóstico a estrategia
- ✅ Absorption V1 respeta `is_drain_mode` en Croupier
- ✅ No requiere cambios

**Uso recomendado:**
```bash
# Demo con timeout y cierre limpio
main.py --mode demo --symbol LTC/USDT:USDT --timeout 30 --close-on-exit
```

---

### 4. `--timeout` ✅ COMPATIBLE

**Propósito:** Limitar duración de sesión (para testing)

**Funcionamiento:**
- Activa Drain Phase cuando `elapsed >= timeout - drain_duration`
- `drain_duration = min(DRAIN_PHASE_MINUTES, timeout * 0.30)`

**Compatibilidad con Absorption V1:**
- ✅ **Totalmente compatible** - Opera a nivel de main loop
- ✅ No requiere cambios

---

### 5. `--mode` (demo/live/backtest) ✅ COMPATIBLE

**Propósito:** Seleccionar modo de ejecución

**Compatibilidad con Absorption V1:**
- ✅ **demo:** Compatible - FootprintRegistry funciona con ticks reales
- ✅ **live:** Compatible - Mismo comportamiento que demo
- ✅ **backtest:** Compatible - VirtualExchange simula ticks correctamente
- ✅ No requiere cambios

---

### 6. `--symbol` ✅ COMPATIBLE

**Propósito:** Seleccionar símbolo a operar

**Compatibilidad con Absorption V1:**
- ✅ **Totalmente compatible** - FootprintRegistry auto-registra símbolos
- ✅ Funciona con cualquier símbolo (BTC, ETH, LTC, etc.)
- ✅ No requiere cambios

**Nota:** Absorption V1 requiere tick data, por lo que el símbolo debe estar en `tick_registry` del SensorManager.

---

### 7. `--bet-size` ✅ COMPATIBLE

**Propósito:** Tamaño de posición (% del balance)

**Compatibilidad con Absorption V1:**
- ✅ **Totalmente compatible** - AdaptivePlayer maneja sizing agnóstico a estrategia
- ✅ No requiere cambios

---

### 8. `--fast-track` + `--close-on-exit` ⚠️ INTERACCIÓN ESPECIAL

**Comportamiento:**
- Si ambos flags están activos, Drain Phase se DESACTIVA (línea 823 en `main.py`)
- Razón: Fast-track es para testing de infraestructura, no para cierre limpio

**Compatibilidad con Absorption V1:**
- ✅ **Compatible** - Comportamiento correcto para protocolos de validación
- ✅ No requiere cambios

---

## Protocolos de Validación Actualizados

### `/fast-track-parity` (30 min)
```bash
# Demo
main.py --mode demo --symbol LTC/USDT:USDT --timeout 30 --fast-track --close-on-exit

# Backtest
backtest.py --dataset tests/validation/ltc_24h_audit.csv --fast-track
```
**Status:** ✅ Compatible con Absorption V1 (después de fix)

### `/execution-quality-audit` (15 min)
```bash
main.py --mode demo --symbol LTC/USDT:USDT --timeout 15 --fast-track
```
**Status:** ✅ Compatible con Absorption V1 (después de fix)

### `/edge-audit`
```bash
# Backtest con audit mode
backtest.py --dataset tests/validation/ltc_24h_audit.csv --audit

# Análisis
.venv/bin/python utils/setup_edge_auditor.py data/historian.db
```
**Status:** ✅ Compatible con Absorption V1

---

## Conclusiones

### ✅ Flags Compatibles (sin cambios)
- `--audit` - Zero-Interference Audit Mode
- `--close-on-exit` - Emergency sweep + Drain Phase
- `--timeout` - Limitar duración de sesión
- `--mode` - Seleccionar modo de ejecución
- `--symbol` - Seleccionar símbolo
- `--bet-size` - Tamaño de posición

### ✅ Flags Corregidos
- `--fast-track` - Agregado bypass en AbsorptionSetupEngine

### ⚠️ Interacciones Especiales
- `--fast-track` + `--close-on-exit` - Drain Phase desactivado (correcto)

### 📝 Recomendaciones

1. **Testing de infraestructura:** Usar `--fast-track` para forzar ejecución
2. **Validación de edge:** Usar `--audit` para registrar señales sin ejecutar
3. **Demo sessions:** Usar `--timeout` + `--close-on-exit` para cierre limpio
4. **Producción:** NUNCA usar `--fast-track` o `--audit`

---

**Fecha:** 2026-04-27
**Fase:** Phase 6 (Validation Updates)
**Status:** ✅ REVISIÓN COMPLETADA - TODOS LOS FLAGS COMPATIBLES
