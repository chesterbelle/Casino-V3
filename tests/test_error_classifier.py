"""
Test para Error Classifier

Verifica que la clasificación de errores funciona correctamente.
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from exchanges.resilience.error_classifier import ErrorCategory, ErrorClassifier


def test_error_classification():
    """Test de clasificación de errores."""
    print("=" * 80)
    print("🧪 TEST: Error Classification")
    print("=" * 80)

    classifier = ErrorClassifier()

    # Test 1: Network error (retriable)
    print("\n📝 Test 1: Network Error")
    error = ConnectionError("Connection timeout")
    classification = classifier.classify(error)
    print(f"   Category: {classification.category.value}")
    print(f"   Retriable: {classification.is_retriable}")
    print(f"   Action: {classification.suggested_action.value}")
    print(f"   Retry delay: {classification.retry_delay}s")

    assert classification.is_retriable, "Network error debe ser retriable"
    assert classification.category == ErrorCategory.NETWORK, "Debe ser NETWORK"

    # Test 2: Authentication error (NO retriable)
    print("\n📝 Test 2: Authentication Error")
    error = Exception("Invalid API key")
    classification = classifier.classify(error)
    print(f"   Category: {classification.category.value}")
    print(f"   Retriable: {classification.is_retriable}")
    print(f"   Action: {classification.suggested_action.value}")

    assert not classification.is_retriable, "Auth error NO debe ser retriable"
    assert classification.category == ErrorCategory.AUTHENTICATION, "Debe ser AUTHENTICATION"

    # Test 3: Rate limit error (retriable con delay largo)
    print("\n📝 Test 3: Rate Limit Error")
    error = Exception("Rate limit exceeded")
    classification = classifier.classify(error)
    print(f"   Category: {classification.category.value}")
    print(f"   Retriable: {classification.is_retriable}")
    print(f"   Retry delay: {classification.retry_delay}s")

    assert classification.is_retriable, "Rate limit debe ser retriable"
    assert classification.category == ErrorCategory.RATE_LIMIT, "Debe ser RATE_LIMIT"
    assert classification.retry_delay == 60.0, "Delay debe ser 60s para rate limit"

    # Test 4: Insufficient funds (NO retriable)
    print("\n📝 Test 4: Insufficient Funds")
    error = Exception("Insufficient balance")
    classification = classifier.classify(error)
    print(f"   Category: {classification.category.value}")
    print(f"   Retriable: {classification.is_retriable}")

    assert not classification.is_retriable, "Insufficient funds NO debe ser retriable"
    assert classification.category == ErrorCategory.INSUFFICIENT_FUNDS, "Debe ser INSUFFICIENT_FUNDS"

    # Test 5: Server error (retriable)
    print("\n📝 Test 5: Server Error")
    error = Exception("Internal server error 500")
    classification = classifier.classify(error)
    print(f"   Category: {classification.category.value}")
    print(f"   Retriable: {classification.is_retriable}")
    print(f"   Retry delay: {classification.retry_delay}s")

    assert classification.is_retriable, "Server error debe ser retriable"
    assert classification.category == ErrorCategory.SERVER_ERROR, "Debe ser SERVER_ERROR"

    # Test 6: Unknown error (NO retriable por defecto)
    print("\n📝 Test 6: Unknown Error")
    error = Exception("Some random error")
    classification = classifier.classify(error)
    print(f"   Category: {classification.category.value}")
    print(f"   Retriable: {classification.is_retriable}")

    assert not classification.is_retriable, "Unknown error NO debe ser retriable (conservador)"
    assert classification.category == ErrorCategory.UNKNOWN, "Debe ser UNKNOWN"

    # Verificar métricas
    print("\n📊 Métricas del clasificador:")
    metrics = classifier.get_metrics()
    print(f"   Total clasificados: {metrics['total_classified']}")
    print(f"   Retriables: {metrics['retriable_count']}")
    print(f"   No retriables: {metrics['non_retriable_count']}")
    print(f"   Tasa retriable: {metrics['retriable_rate']:.2%}")
    print(f"   Por categoría: {metrics['category_counts']}")

    assert metrics["total_classified"] == 6, "Debe haber 6 errores clasificados"
    assert metrics["retriable_count"] == 3, "Debe haber 3 retriables"
    assert metrics["non_retriable_count"] == 3, "Debe haber 3 no retriables"

    print("\n" + "=" * 80)
    print("✅ TEST PASSED: Error Classification funciona correctamente")
    print("=" * 80)


if __name__ == "__main__":
    test_error_classification()
