from datetime import datetime, timedelta, timezone
from decimal import Decimal
from app.memory.models import MemoryStatus
from app.memory.services.decay import compute_effective_confidence, compute_effective_weight

def test_decay_supposed_vs_verified():
    now = datetime.now(timezone.utc)
    thirty_days_ago = now - timedelta(days=30)
    base_conf = 1.0
    
    # Supposed: 0.05 rate -> exp(-0.05 * 30) = exp(-1.5) approx 0.2231
    # Verified: 0.002 rate -> exp(-0.002 * 30) = exp(-0.06) approx 0.9417
    
    conf_supposed = compute_effective_confidence(base_conf, MemoryStatus.supposed, thirty_days_ago, now=now)
    conf_verified = compute_effective_confidence(base_conf, MemoryStatus.verified, thirty_days_ago, now=now)
    
    assert conf_supposed < conf_verified
    assert conf_supposed == 0.2231
    assert conf_verified == 0.9418 # rounded 0.94176

def test_decay_verified_floor():
    now = datetime.now(timezone.utc)
    three_years_ago = now - timedelta(days=1095)
    base_conf = 1.0
    
    # Floor for verified is 0.3
    conf_verified = compute_effective_confidence(base_conf, MemoryStatus.verified, three_years_ago, now=now)
    
    assert conf_verified >= 0.3
    assert conf_verified == 0.3

def test_decay_now():
    now = datetime.now(timezone.utc)
    base_conf = 0.8
    
    conf = compute_effective_confidence(base_conf, MemoryStatus.known, now, now=now)
    
    # exp(0) = 1
    assert conf == base_conf

def test_decay_and_weight_with_decimal():
    now = datetime.now(timezone.utc)
    thirty_days_ago = now - timedelta(days=30)
    
    # Simulate DB Numeric type yielding Decimal values
    base_conf_decimal = Decimal("1.000")
    importance_decimal = Decimal("0.850")
    
    conf_effective = compute_effective_confidence(
        base_conf_decimal, MemoryStatus.supposed, thirty_days_ago, now=now
    )
    # Should work without TypeError and return a float
    assert isinstance(conf_effective, float)
    assert conf_effective == 0.2231
    
    # Check weight computation with float/Decimal mix
    weight = compute_effective_weight(conf_effective, importance_decimal)
    assert isinstance(weight, float)
    assert weight == round(0.2231 * 0.85, 4)

