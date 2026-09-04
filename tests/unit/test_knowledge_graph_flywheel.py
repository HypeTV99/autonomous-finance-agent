import pytest
from decimal import Decimal
from compliance_engine import (
    FinancialDecisionKnowledgeGraphEngine,
    AutonomousLearningFlywheelService,
    create_sample_decision
)
from schemas import (
    KnowledgeGraphNodeType,
    KnowledgeGraphEdgeType,
    ClosedLoopLearningFeedback,
    FeedbackOutcomeType
)

def test_10_stage_knowledge_graph_construction():
    decision = create_sample_decision()
    kg = FinancialDecisionKnowledgeGraphEngine.build_knowledge_graph(decision)
    
    assert kg.is_closed_loop_complete is True
    assert len(kg.nodes) == 10
    
    node_types = [n.node_type for n in kg.nodes]
    expected_stages = [
        KnowledgeGraphNodeType.VENDOR,
        KnowledgeGraphNodeType.CONTRACT,
        KnowledgeGraphNodeType.INVOICE,
        KnowledgeGraphNodeType.RISK_SIGNALS,
        KnowledgeGraphNodeType.DECISION,
        KnowledgeGraphNodeType.HUMAN_OVERRIDE,
        KnowledgeGraphNodeType.PAYMENT_DISBURSEMENT,
        KnowledgeGraphNodeType.BANK_OUTCOME,
        KnowledgeGraphNodeType.RECONCILIATION,
        KnowledgeGraphNodeType.AUDIT_OUTCOME
    ]
    assert node_types == expected_stages
    
    # Check forward lineage edges + feedback learning loop
    assert len(kg.edges) == 10
    feedback_edges = [e for e in kg.edges if e.is_feedback_learning_edge]
    assert len(feedback_edges) == 1
    assert feedback_edges[0].edge_type == KnowledgeGraphEdgeType.FEEDBACK_LOOP

def test_closed_loop_learning_flywheel_feedback():
    initial = AutonomousLearningFlywheelService.get_vendor_intelligence("VEND-ALPHA-01")
    init_completed = initial.lifetime_transactions_completed
    init_cap = initial.auto_approval_velocity_cap
    
    # Feed back confirmed bank settlement outcome
    feedback = ClosedLoopLearningFeedback(
        feedback_id="FB-TEST-001",
        invoice_number="INV-884",
        vendor_id="VEND-ALPHA-01",
        outcome_type=FeedbackOutcomeType.BANK_SETTLED_CONFIRMED,
        settlement_latency_ms=310,
        bank_utr="UTR-HDFC-4821-TEST",
        timestamp="2026-08-24T14:00:00Z"
    )
    
    updated = AutonomousLearningFlywheelService.ingest_feedback(feedback)
    assert updated.lifetime_transactions_completed == init_completed + 1
    assert updated.auto_approval_velocity_cap > init_cap
    assert updated.settlement_reliability_score_pct >= 99.8
