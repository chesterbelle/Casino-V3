# Casino-V3 (Slim v8.3) Architecture Blueprint

## System Philosophy: Zero-Necrosis
The system is built on a "Slim" paradigm: Two active exit pillars (Scale Out + Micro-Z Reversal). No trailing stops, no break-even, no dead code.

## Component Truth Table (System API)

| Component | Role | Primary Input | Primary Output | Critical Responsibility |
| :--- | :--- | :--- | :--- | :--- |
| `FootprintRegistry` | High-Fidelity L2 | Ticks / Trades | CVD / Price Profile | L2 Data Integrity |
| `AbsorptionDetector` | Tactical Sensor | Footprint Data | SignalEvent | Identifying institutional flow |
| `SetupEngine` | Structural Anchor | Signal + Macro | DecisionEvent | AMT-based entry geometry |
| `SlimExitEngine` | Resiliency Guard | Pos + Market | ExitDecision | Structural exit (ScaleOut/MicroZ) |
| `Croupier` | Traffic Controller | DecisionEvent | Exchange Order | Lifecycle management (OCO) |
| `Orchestrator` | Pipeline Engine | Audit Protocol | Merged Data | Deterministic audit workflow |

## Data Pipeline
`Ticks` → `FootprintRegistry` → `AbsorptionDetector` → `SetupEngine` → `AdaptivePlayer` → `Croupier` → `Exchange`

## Constitutional Rules (AI Mandatory)
1. **NO MERGE/REBASE**: 3 incompatible bots exist in separate branches. Never cross-contaminate.
2. **NO PUSH**: Only perform `git push` on explicit user command.
3. **ZERO-NECROSIS**: If a component is not in the "Truth Table" above, it is candidate for deletion/archival.
4. **VALIDATION FIRST**: Before ANY logic change, execute `.agent/workflows/validate-all.md`.
5. **DETERMINISM**: All audit workflows MUST run through `scripts/orchestrator.py`. Manual shell-based audits are forbidden.

*Note: This architecture is the "Source of Truth". All legacy docs in `archive/` are for historical context only.*
