"""Ten-line certificate demo: issue, verify, tamper, verify again.

Run: .venv\\Scripts\\python -m trust.demo_certificate
"""

from __future__ import annotations

from trust.certificate import (
    fresh_demo_db,
    issue,
    tamper_for_demo,
    verify,
)

DB = "data/certificate_demo.db"
fresh_demo_db(DB)
for i in range(3):
    cert = issue(
        {"model_id": 2, "findings_hash": f"f{i}", "report_hash": f"r{i}", "config_hash": "c"},
        approver="Demo Auditor",
        decision="approve",
        db_path=DB,
    )
    print("issued", cert.index, cert.record_hash[:12])
print("verify clean", verify(DB))
print("tamper", tamper_for_demo(1, DB)["field"], "at index 1")
print("verify after tamper", verify(DB))
