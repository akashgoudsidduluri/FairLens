"""Documented Indian name and region pools for the R3c LLM screener.

These pools exist only to make a name or region counterfactual concrete for a
language model. They are arbitrary collections of common Indian names and Indian
regions. **They are not a statement about anyone's religion, caste, language,
ethnicity, or community**, and no pool is intended to represent a coherent
group. Each pool deliberately mixes names from several backgrounds so that a
name-group flip cannot be read as a claim about one community.

Mapping is deterministic: the same canonical name or pincode always maps to the
same string, so a name twin changes exactly the name line and a region twin
changes exactly the region line.
"""

from __future__ import annotations

import hashlib

NAME_POOLS: dict[tuple[str, str], tuple[str, ...]] = {
    ("N1", "female"): (
        "Aarohi Sharma",
        "Meera Nair",
        "Fatima Khan",
        "Simran Kaur",
    ),
    ("N1", "male"): (
        "Aarav Sharma",
        "Arjun Nair",
        "Imran Khan",
        "Rohan Singh",
    ),
    ("N2", "female"): (
        "Ananya Rao",
        "Kavya Iyer",
        "Zoya Ahmed",
        "Neha Patil",
    ),
    ("N2", "male"): (
        "Vikram Rao",
        "Karthik Iyer",
        "Adil Ahmed",
        "Siddharth Patil",
    ),
    ("N3", "female"): (
        "Priya Das",
        "Riya Banerjee",
        "Sana Sheikh",
        "Divya Menon",
    ),
    ("N3", "male"): (
        "Rahul Das",
        "Aritra Banerjee",
        "Faisal Sheikh",
        "Nikhil Menon",
    ),
}

REGION_POOLS: dict[str, tuple[str, ...]] = {
    "P1": (
        "Mumbai, Maharashtra",
        "Pune, Maharashtra",
        "Ahmedabad, Gujarat",
    ),
    "P2": (
        "Chennai, Tamil Nadu",
        "Bengaluru, Karnataka",
        "Hyderabad, Telangana",
    ),
    "P3": (
        "Kolkata, West Bengal",
        "Bhubaneswar, Odisha",
        "Lucknow, Uttar Pradesh",
    ),
}


def _index(seed_text: str, size: int) -> int:
    digest = hashlib.sha256(seed_text.encode("utf-8")).hexdigest()
    return int(digest[:12], 16) % size


def full_name(name_group: str, gender: str, canonical_name: str) -> str:
    pool = NAME_POOLS[(name_group, gender)]
    return pool[_index(canonical_name, len(pool))]


def region_name(pincode_group: str, canonical_pincode: str) -> str:
    pool = REGION_POOLS[pincode_group]
    return pool[_index(canonical_pincode, len(pool))]
