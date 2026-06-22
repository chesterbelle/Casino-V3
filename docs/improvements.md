# Propuesta de Mejora de Rendimiento: Backtest Feed V10.4

## El Problema Actual (El Cuello de Botella)

Actualmente, el backtester de Casino-V3 sufre de un grave problema de rendimiento al procesar datasets mensuales masivos (como el archivo de 4GB de SOL). Aunque el commit `fc00888` introdujo "streaming por ventanas de tiempo" (24 horas) para evitar errores de falta de memoria (OOM), lo hizo delegando el ordenamiento y la unión de eventos a **Pandas**.

Por cada ventana de 24 horas, el sistema hace lo siguiente:
1. Extrae los Depth Snapshots (L2) a un DataFrame de Pandas.
2. Extrae los Market Trades a otro DataFrame de Pandas.
3. Ejecuta `pd.concat([depth_df, trades_df])`.
4. Ejecuta un `sort_values("timestamp")` en Python para ordenar cronológicamente la mezcla.
5. Itera sobre el resultado usando `itertuples()`.

Para 100 millones de eventos, pedirle a Python y Pandas que asignen memoria dinámica, concatenen y ordenen repetidamente es increíblemente lento y costoso. Esto es el responsable de que el backtest tenga un piso base de unas 46 horas para un solo activo.

## La Solución Quirúrgica: Motor en C de SQLite (`UNION ALL`)

Dado que los datos ya están estructurados dentro de SQLite, podemos usar el motor interno de la base de datos (escrito en C, extremadamente rápido) para que nos entregue la línea de tiempo perfectamente ordenada, eliminando Pandas de la ecuación.

### Propuesta Técnica

Reemplazar las consultas individuales y el bloque de `pd.concat` en `core/backtest_feed.py` por una sola consulta unificada (`UNION ALL`):

```sql
SELECT timestamp, 'DEPTH' as event_type, bids, asks, NULL as price, NULL as volume, NULL as side
FROM depth_snapshots
WHERE symbol = ? AND timestamp >= ? AND timestamp < ?

UNION ALL

SELECT timestamp, 'TICK' as event_type, NULL as bids, NULL as asks, price, amount as volume, side
FROM market_trades
WHERE symbol = ? AND timestamp >= ? AND timestamp < ?

ORDER BY timestamp ASC
```

### Beneficios Esperados
1. **Reducción de RAM:** Eliminamos la creación de DataFrames intermedios.
2. **Eliminación de overhead de ordenamiento:** El motor C de SQLite hace el `ORDER BY` de forma casi instantánea usando índices si existen, o algoritmos nativos mucho más eficientes que Pandas para este volumen.
3. **Cero riesgo lógico:** No altera la detección de *race conditions*, porque los eventos siguen emitiéndose exactamente en el mismo orden de milisegundos hacia el orquestador asíncrono.
4. **Impacto:** Podría reducir el tiempo de I/O puro significativamente, recortando varias horas del tiempo total de simulación sin tocar el `Slim Exit Engine` ni la base lógica.
