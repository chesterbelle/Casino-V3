# Prometheus Alert Rules for Casino-V3

This document describes recommended alert rules for production monitoring.

## Installation

1. Add these rules to your Prometheus configuration:

```yaml
# prometheus.yml
rule_files:
  - "alert_rules.yml"

alerting:
  alertmanagers:
    - static_configs:
        - targets: ["localhost:9093"]  # Alertmanager address
```

2. Create `alert_rules.yml` with the rules below

3. Reload Prometheus: `kill -HUP $(pidof prometheus)`

---

## Critical Alerts 🚨

### Bot Down
```yaml
- alert: BotDown
  expr: up{job="casino-v3"} == 0
  for: 1m
  labels:
    severity: critical
  annotations:
    summary: "Casino-V3 bot is down"
    description: "The bot has been down for more than 1 minute"
```

### High Error Rate
```yaml
- alert: HighErrorRate
  expr: rate(errors_total[5m]) > 10
  for: 2m
  labels:
    severity: critical
  annotations:
    summary: "High error rate detected"
    description: "Error rate is {{ $value }}/s (threshold: 10 errors/s)"
```

### Circuit Breaker Open
```yaml
- alert: CircuitBreakerOpen
  expr: circuit_breaker_state == 1
  for: 5m
  labels:
    severity: critical
  annotations:
    summary: "Circuit breaker {{ $labels.name }} is OPEN"
    description: "Service {{ $labels.name }} has been unavailable for 5 minutes"
```

### Balance Drop
```yaml
- alert: AccountBalanceDrop
  expr: |
    (account_balance_usdt - account_balance_usdt offset 1h)
    / account_balance_usdt offset 1h * 100 < -10
  for: 5m
  labels:
    severity: critical
  annotations:
    summary: "Account balance dropped >10% in 1 hour"
    description: "Current balance: {{ $value | humanize }}%"
```

---

## Warning Alerts ⚠️

### High Order Latency
```yaml
- alert: HighOrderLatency
  expr: |
    histogram_quantile(0.95, sum(rate(order_latency_seconds_bucket[5m])) by (le)) > 2.0
  for: 5m
  labels:
    severity: warning
  annotations:
    summary: "High order execution latency"
    description: "p95 latency is {{ $value }}s (threshold: 2s)"
```

### WebSocket Reconnections
```yaml
- alert: FrequentWebSocketReconnections
  expr: increase(websocket_reconnections_total[15m]) > 5
  labels:
    severity: warning
  annotations:
    summary: "Frequent WebSocket reconnections"
    description: "{{ $value }} reconnections in last 15 minutes"
```

### Low Win Rate
```yaml
- alert: LowWinRate
  expr: win_rate < 40 and sum(positions_closed_total) > 50
  for: 1h
  labels:
    severity: warning
  annotations:
    summary: "Win rate below 40%"
    description: "Current win rate: {{ $value }}% (min trades: 50)"
```

### Position Limit Reached
```yaml
- alert: PositionLimitReached
  expr: sum(open_positions) >= 10
  for: 5m
  labels:
    severity: warning
  annotations:
    summary: "Position limit reached"
    description: "{{ $value }} open positions (limit: 10)"
```

---

## Operational Alerts 📊

### High Event Loop Lag
```yaml
- alert: HighEventLoopLag
  expr: event_loop_lag_seconds > 0.5
  for: 2m
  labels:
    severity: warning
  annotations:
    summary: "High event loop lag"
    description: "Loop lag is {{ $value }}s (threshold: 0.5s)"
```

### State Save Age
```yaml
- alert: StateSaveStale
  expr: state_save_age_seconds > 300
  for: 5m
  labels:
    severity: warning
  annotations:
    summary: "State hasn't been saved recently"
    description: "Last save was {{ $value}}s ago (threshold: 300s)"
```

### No Trades
```yaml
- alert: NoTradesExecuted
  expr: increase(positions_opened_total[1h]) == 0
  for: 2h
  labels:
    severity: info
  annotations:
    summary: "No trades executed in 2 hours"
    description: "Bot may be inactive or waiting for signals"
```

---

## Alert Routing

### Alertmanager Configuration Example

```yaml
# alertmanager.yml
route:
  group_by: ['severity']
  group_wait: 30s
  group_interval: 5m
  repeat_interval: 4h
  receiver: 'telegram-critical'

  routes:
    - match:
        severity: critical
      receiver: 'telegram-critical'
      continue: true

    - match:
        severity: warning
      receiver: 'telegram-warning'

    - match:
        severity: info
      receiver: 'email'

receivers:
  - name: 'telegram-critical'
    telegram_configs:
      - api_url: 'https://api.telegram.org'
        bot_token: 'YOUR_BOT_TOKEN'
        chat_id: YOUR_CHAT_ID
        parse_mode: 'HTML'
        message: |
          🚨 <b>CRITICAL ALERT</b>

          <b>{{ .GroupLabels.alertname }}</b>
          {{ range .Alerts }}
          {{ .Annotations.description }}
          {{ end }}

  - name: 'telegram-warning'
    telegram_configs:
      - api_url: 'https://api.telegram.org'
        bot_token: 'YOUR_BOT_TOKEN'
        chat_id: YOUR_CHAT_ID
        message: |
          ⚠️ WARNING: {{ .GroupLabels.alertname }}
          {{ range .Alerts }}
          {{ .Annotations.summary }}
          {{ end }}

  - name: 'email'
    email_configs:
      - to: 'your-email@example.com'
        from: 'alerts@example.com'
        smarthost: 'smtp.gmail.com:587'
        auth_username: 'your-email@example.com'
        auth_password: 'your-app-password'
```

---

## Alert Testing

```bash
# Test alert rule syntax
promtool check rules alert_rules.yml

# Test specific expression
curl -G 'http://localhost:9090/api/v1/query' \
  --data-urlencode 'query=rate(errors_total[5m]) > 10'

# Trigger test alert (in Alertmanager)
curl -X POST http://localhost:9093/api/v2/alerts -d '[
  {
    "labels": {
      "alertname": "TestAlert",
      "severity": "critical"
    },
    "annotations": {
      "summary": "Test alert"
    }
  }
]'
```

---

## Best Practices

1. **Severity Levels**:
   - `critical`: Immediate action required (bot down, circuit breaker open)
   - `warning`: Investigation needed (high latency, low win rate)
   - `info`: Informational (no trades, routine events)

2. **For Duration**:
   - Critical: 1-5 minutes (fast response)
   - Warning: 5-15 minutes (reduce noise)
   - Info: 1-2 hours (trends only)

3. **Avoid Alert Fatigue**:
   - Group similar alerts
   - Use meaningful thresholds
   - Implement inhibition rules
   - Regular rule review and tuning

4. **Testing**:
   - Test alerts in staging first
   - Verify notification delivery
   - Check for false positives
   - Document runbooks for each alert

---

For more information, see:
- [Prometheus Alerting Documentation](https://prometheus.io/docs/alerting/latest/overview/)
- [Alertmanager Configuration](https://prometheus.io/docs/alerting/latest/configuration/)
- [CONFIGURATION.md](../CONFIGURATION.md) - Bot configuration
- [TROUBLESHOOTING.md](../TROUBLESHOOTING.md) - Common issues
