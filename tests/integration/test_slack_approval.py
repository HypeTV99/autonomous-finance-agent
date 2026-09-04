from slack_service import HardenedSlackService
from schemas import ApprovalTier

def test_slack_hmac_token_and_tier_routing():
    slack = HardenedSlackService(webhook_url="https://hooks.slack.com/services/test", signing_secret="secret123")
    
    # Generate action token
    token = slack.generate_action_token("INV-SLACK-001", "APPROVE")
    assert token is not None

    # Verify action token
    valid, inv, act = slack.verify_action_token(token)
    assert valid is True
    assert inv == "INV-SLACK-001"
    assert act == "APPROVE"

    # Tampered token fails
    tampered_token = token[:-4] + "AAAA"
    valid_tamp, _, reason = slack.verify_action_token(tampered_token)
    assert valid_tamp is False
