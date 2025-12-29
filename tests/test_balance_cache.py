"""
Test para Balance Cache

Verifica que el cache y fallback de balance funciona correctamente.
"""

import sys
import time
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from exchanges.resilience.balance_cache import BalanceCache, BalanceSource


def test_balance_cache():
    """Test básico de balance cache."""
    print("=" * 80)
    print("🧪 TEST: Balance Cache & Fallback")
    print("=" * 80)

    # 1. Crear cache
    cache = BalanceCache(cache_ttl=2.0, max_age=10.0, currency="USD")
    print("\n✅ BalanceCache inicializado")
    print(f"   TTL: {cache._cache_ttl}s | Max age: {cache._max_age}s")

    # 2. Actualizar con datos del exchange
    print("\n📝 Actualizando con datos del exchange...")
    balance_data = {"free": {"USD": 5000.0}, "used": {"USD": 0.0}, "total": {"USD": 5000.0}}

    snapshot = cache.update_from_exchange(balance_data)
    print(f"   Balance: ${snapshot.balance:,.2f}")
    print(f"   Source: {snapshot.source.value}")
    print(f"   Is stale: {snapshot.is_stale}")

    assert snapshot.balance == 5000.0, "Balance debe ser 5000"
    assert snapshot.source == BalanceSource.EXCHANGE_FRESH, "Source debe ser EXCHANGE_FRESH"
    assert not snapshot.is_stale, "No debe estar stale"

    # 3. Obtener balance (cache fresco)
    print("\n✅ Obteniendo balance (cache fresco)...")
    snapshot = cache.get_balance_safe()
    print(f"   Balance: ${snapshot.balance:,.2f}")
    print(f"   Source: {snapshot.source.value}")
    print(f"   Age: {snapshot.staleness_seconds:.2f}s")

    assert snapshot.source == BalanceSource.EXCHANGE_FRESH, "Debe usar cache fresco"

    # 4. Esperar a que el cache expire (TTL)
    print("\n⏳ Esperando TTL (2s)...")
    time.sleep(2.5)

    snapshot = cache.get_balance_safe()
    print(f"   Balance: ${snapshot.balance:,.2f}")
    print(f"   Source: {snapshot.source.value}")
    print(f"   Age: {snapshot.staleness_seconds:.2f}s")
    print(f"   Is stale: {snapshot.is_stale}")

    assert snapshot.source == BalanceSource.EXCHANGE_CACHED, "Debe usar cache stale"
    assert snapshot.is_stale, "Debe estar stale"

    # 5. Actualizar balance calculado
    print("\n🧮 Actualizando balance calculado...")
    cache.update_calculated(4950.0)  # Simulamos una pérdida de $50

    snapshot = cache.get_balance_safe()
    print(f"   Balance: ${snapshot.balance:,.2f}")
    print(f"   Source: {snapshot.source.value}")

    assert snapshot.balance == 4950.0, "Debe usar balance calculado"
    assert snapshot.source == BalanceSource.CALCULATED, "Source debe ser CALCULATED"

    # 6. Verificar métricas
    print("\n📊 Métricas del cache:")
    metrics = cache.get_metrics()
    print(f"   Total fetches: {metrics['total_fetches']}")
    print(f"   Cache hits: {metrics['cache_hits']}")
    print(f"   Cache hit rate: {metrics['cache_hit_rate']:.2%}")
    print(f"   Current age: {metrics['current_age']:.2f}s")
    print(f"   Is stale: {metrics['is_stale']}")

    assert metrics["total_fetches"] == 1, "Debe haber 1 fetch"
    assert metrics["cache_hits"] >= 2, "Debe haber al menos 2 cache hits"

    # 7. Verificar estado
    print("\n📊 Estado del cache:")
    status = cache.get_status()
    print(f"   Cached balance: ${status['cached_balance']:,.2f}")
    print(f"   Cache age: {status['cache_age']:.2f}s")
    print(f"   Calculated balance: ${status['calculated_balance']:,.2f}")
    print(f"   Calculated age: {status['calculated_age']:.2f}s")

    print("\n" + "=" * 80)
    print("✅ TEST PASSED: Balance Cache funciona correctamente")
    print("=" * 80)


def test_balance_cache_fallback():
    """Test de fallback cuando no hay datos frescos."""
    print("\n" + "=" * 80)
    print("🧪 TEST: Balance Cache Fallback")
    print("=" * 80)

    # 1. Crear cache
    cache = BalanceCache(cache_ttl=1.0, max_age=5.0, currency="USD")

    # 2. Actualizar con datos
    balance_data = {"free": {"USD": 3000.0}}
    cache.update_from_exchange(balance_data)
    print("\n✅ Balance inicial: $3,000.00")

    # 3. Esperar a que expire TTL
    print("⏳ Esperando TTL (1s)...")
    time.sleep(1.5)

    # 4. Obtener con fallback (debe usar cache stale)
    snapshot = cache.get_balance_safe()
    print(f"\n✅ Balance con fallback:")
    print(f"   Balance: ${snapshot.balance:,.2f}")
    print(f"   Source: {snapshot.source.value}")
    print(f"   Is stale: {snapshot.is_stale}")
    print(f"   Age: {snapshot.staleness_seconds:.2f}s")

    assert snapshot.balance == 3000.0, "Debe mantener balance"
    assert snapshot.is_stale, "Debe estar stale"

    # 5. Esperar a que expire max_age
    print("\n⏳ Esperando max_age (5s)...")
    time.sleep(4.0)  # Total: 5.5s

    # 6. Intentar obtener (debe fallar)
    print("\n❌ Intentando obtener balance muy stale...")
    try:
        snapshot = cache.get_balance_safe()
        print(f"   ERROR: No debería haber retornado balance")
        assert False, "Debería haber lanzado RuntimeError"
    except RuntimeError as e:
        print(f"   ✅ RuntimeError esperado: {e}")

    print("\n" + "=" * 80)
    print("✅ TEST PASSED: Fallback funciona correctamente")
    print("=" * 80)


if __name__ == "__main__":
    test_balance_cache()
    test_balance_cache_fallback()
