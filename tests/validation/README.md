# Validación: Testing vs Backtesting

## 🎯 Objetivo

Validar que `main.py` con Player Paroli produce los mismos resultados en:
- **Modo Testing** (`--mode=testing`) - Kraken testnet en vivo
- **Modo Backtesting** (`--mode=backtest`) - Con los mismos datos descargados

## 🔄 Flujo Completo

### 1. Ejecutar en Modo Testing (60 velas)
```bash
# Ejecutar main.py en modo testing durante 60 velas
python main.py --mode=testing --player=paroli --symbol=BTC/USD:USD --interval=1m --max-candles=60

# Esto guardará logs y resultados automáticamente
```

### 2. Descargar Datos Históricos
```bash
# Descargar las mismas 60 velas que se usaron en testing
python tests/validation/download_historical_data.py \
    --start "2024-11-06T20:00:00Z" \
    --end "2024-11-06T21:00:00Z" \
    --output data/validation/BTC_USD_60candles.csv
```

### 3. Ejecutar en Modo Backtesting
```bash
# Ejecutar main.py en modo backtest con los datos descargados
python main.py --mode=backtest --player=paroli --data=data/validation/BTC_USD_60candles.csv --max-candles=60
```

### 4. Comparar Resultados
```bash
# Comparar los resultados de ambos modos
python tests/validation/compare_results.py \
    --testing-log logs/testing_20241106_2000.log \
    --backtest-log logs/backtest_20241106_2100.log
```

## 📊 Qué se Compara

1. **Balance Final** - Debe ser idéntico (±0.1%)
2. **Número de Trades** - Debe ser exacto
3. **Señales Generadas** - Deben ser las mismas
4. **Precios de Entrada** - Deben coincidir (±0.1% por slippage)
5. **Win Rate** - Debe ser idéntico
6. **PnL Total** - Debe coincidir (±0.1%)

## ✅ Criterios de Éxito

- ✅ Mismo número de trades
- ✅ Balance final difiere <0.1%
- ✅ Win rate idéntico
- ✅ Señales generadas en los mismos momentos

## 📝 Notas

- El modo testing toma 60 minutos (60 velas de 1m)
- Asegúrate de tener balance en Kraken testnet
- Los datos históricos deben descargarse inmediatamente después del testing
- Pequeñas diferencias (<0.1%) son aceptables por slippage
