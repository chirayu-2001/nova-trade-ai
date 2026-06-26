"""Customer validation rule models and loader."""

import json
import os
from enum import Enum
from typing import Optional

from pydantic import BaseModel

from backend.config.settings import settings


class MatchType(str, Enum):
    EXACT = "exact"
    FUZZY = "fuzzy"
    NUMERIC_TOLERANCE = "numeric_tolerance"
    REGEX = "regex"
    SEMANTIC = "semantic"
    EXACT_PREFIX = "exact_prefix"
    CONTAINS = "contains"
    FORMAT = "format"
    CROSS_DOCUMENT_CONSISTENT = "cross_document_consistent"
    PRESENT_ON_ALL = "present_on_all"


class FieldRule(BaseModel):
    expected: Optional[str] = None
    match_type: str = "exact"
    case_sensitive: bool = False
    threshold: float = 0.85
    tolerance_pct: float = 2.0
    unit: Optional[str] = None
    pattern: Optional[str] = None
    prefix_length: Optional[int] = None
    digits: Optional[int] = None
    severity: str = "high"
    required: bool = True
    field: Optional[str] = None  # For cross-reference rules


class CustomerRuleSet(BaseModel):
    customer_id: str
    customer_name: str
    applies_to: Optional[str] = None
    rules: dict[str, FieldRule] = {}


def load_customer_rules(customer_id: str) -> CustomerRuleSet:
    """Load customer rules from JSON file."""
    rules_dir = settings.customer_rules_dir
    rules_path = os.path.join(rules_dir, f"{customer_id}.json")

    if not os.path.exists(rules_path):
        raise FileNotFoundError(f"Customer rules not found: {rules_path}")

    with open(rules_path) as f:
        data = json.load(f)

    # Parse rules
    parsed_rules = {}
    for rule_name, rule_data in data.get("rules", {}).items():
        parsed_rules[rule_name] = FieldRule(**rule_data)

    return CustomerRuleSet(
        customer_id=customer_id,
        customer_name=data.get("customer_name", customer_id),
        applies_to=data.get("applies_to"),
        rules=parsed_rules,
    )


def list_available_customers() -> list[str]:
    """List all customer IDs with rule files."""
    rules_dir = settings.customer_rules_dir
    if not os.path.exists(rules_dir):
        return []
    return [
        f.replace(".json", "")
        for f in os.listdir(rules_dir)
        if f.endswith(".json")
    ]
