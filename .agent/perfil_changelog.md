# 📝 Bitácora de Iteración de Perfiles (Sintonía Fina)

Este archivo es la memoria técnica de la optimización de parámetros por cluster. Su objetivo es evitar la redundancia y documentar la relación entre el cambio paramétrico y el Net Taker resultante.

## 🛠️ Protocolo de Registro
Cada iteración debe registrarse siguiendo este formato:
1. **Hipótesis**: Qué se espera lograr (ej: "Reducir timeout rate en THIN").
2. **Cambios**: Parámetros exactos modificados (Valor A $\rightarrow$ Valor B).
3. **Resultado**: Métrica principal (Net Taker) y comportamiento observado.
4. **Veredicto**: ✅ Mantener, ❌ Revertir, ⚠️ Ajustar.

---

## 💎 MEGA_LIQUID (BTC, ETH)
*Estado actual: Baseline*

| Iter | Fecha | Hipótesis | Cambios | Net Taker | Veredicto | Nota |
|:---:|:---:|:---|:---|:---:|:---:|:---|
| 0 | - | Baseline | Seed Uniform Grid | - | - | Inicio de optimización |

---

## 🚀 MAJOR_LIQUID (SOL, BNB, XRP, DOGE, SUI)
*Estado actual: Baseline*

| Iter | Fecha | Hipótesis | Cambios | Net Taker | Veredicto | Nota |
|:---:|:---:|:---|:---|:---:|:---:|:---|
| 0 | - | Baseline | Seed Uniform Grid | - | - | Inicio de optimización |

---

## ⚖️ MID_LIQUID (LTC, AVAX, ADA, LINK)
*Estado actual: Baseline*

| Iter | Fecha | Hipótesis | Cambios | Net Taker | Veredicto | Nota |
|:---:|:---:|:---|:---|:---:|:---:|:---|
| 0 | - | Baseline | Seed Uniform Grid | - | - | Inicio de optimización |

---

## 🌪️ THIN_VOLATILE (XRP, DOGE)
*Estado actual: Iteración 2 (En progreso)*

| Iter | Fecha | Hipótesis | Cambios | Net Taker | Veredicto | Nota |
|:---:|:---:|:---|:---|:---:|:---:|:---|
| 0 | - | Baseline | Seed Uniform Grid | -0.33% | - | Ruido masivo en TAV |
| 1 | 2026-06-06 | Filtro de Pureza: Reducir ruido en TAV y LE elevando umbrales de calidad y presión | Exh block 1.5→1.2, perf 0.5→0.3; Liq strong 2.0→3.0, adeq 1.5→2.0, weak 1.0→1.5; z_block 2.0→1.5; FB dist 0.0010→0.0015 | -0.33% | ❌ Revertir | Filtro insuficiente: 4267 señales (igual a base) |
| 2 | 2026-06-06 | La Purga: Bloqueo agresivo de señales mediocres y ruido de baja intensidad | Grade B 0.4→0.6, A 0.65→0.85; Weight Exh 0.3→0.5, Liq 0.15→0.25, Reg 0.3→0.2; z_score_min 1.5→2.5, conc_min 0.4→0.6 | PENDING | ⚠️ Ajustar | BUG FIX: Corregido filtrado de Grade None y normalización de pesos. |

---

## 📉 ILLIQUID_SPEC (Long-tail)
*Estado actual: Baseline*

| Iter | Fecha | Hipótesis | Cambios | Net Taker | Veredicto | Nota |
|:---:|:---:|:---|:---|:---:|:---:|:---|
| 0 | - | Baseline | Seed Uniform Grid | - | - | Inicio de optimización |
