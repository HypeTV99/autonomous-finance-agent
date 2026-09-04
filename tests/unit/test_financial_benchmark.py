import pytest
from benchmark_suite import FinancialControlBenchmarkEngine, BenchmarkVectorType

def test_financial_control_benchmark_corpus_generation():
    corpus = FinancialControlBenchmarkEngine.generate_benchmark_corpus(count=1000, seed=42)
    assert len(corpus) == 1000
    
    # Check that clean invoices make up ~75%
    clean_invoices = [tx for tx in corpus if tx.vector_type == BenchmarkVectorType.NORMAL_CLEAN_INVOICE]
    assert len(clean_invoices) == 750

    # Check adversarial vector presence
    dup_invoices = [tx for tx in corpus if tx.vector_type == BenchmarkVectorType.DUPLICATE_INVOICE]
    assert len(dup_invoices) == 25

    cooling_invoices = [tx for tx in corpus if tx.vector_type == BenchmarkVectorType.BANK_ACCOUNT_CHANGED_UNDER_48H]
    assert len(cooling_invoices) == 20

def test_financial_control_benchmark_execution_and_invariants():
    metrics = FinancialControlBenchmarkEngine.execute_benchmark_suite(count=1000)
    
    assert metrics.total_transactions_evaluated == 1000
    assert metrics.clean_normal_transactions == 750
    assert metrics.adversarial_control_violations == 250
    
    # Invariant KPI assertions
    assert metrics.control_violations_detection_rate_pct >= 95.0
    assert metrics.false_positive_rate_pct <= 2.0
    assert metrics.auto_processing_rate_pct >= 70.0
    assert metrics.unsafe_autonomous_actions == 0
    assert metrics.duplicate_payouts_leaked == 0
    assert metrics.duplicate_payouts_prevented >= 25
    assert metrics.reconciliation_recovery_success_rate_pct >= 95.0
    assert metrics.decision_replay_fidelity_pct == 100.0
    assert metrics.cryptographic_verification_fidelity_pct == 100.0
    assert metrics.evaluation_throughput_tx_per_sec > 100.0  # Fast in-memory execution
