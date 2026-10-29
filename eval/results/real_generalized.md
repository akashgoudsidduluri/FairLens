# Generalized protocol on the real targets (R5 Step 6)

This table is separate from the frozen real-target sections in `expected_findings.md`.
It reports the R5 generalized protocol (age twins added) without replacing the old-protocol facts.
Seed 42, frozen materiality 0.02, Holm across the discovery panel.

| Target | Runtime | Cells examined | Cells tested | Discovery pairs | Confirmation pairs | Candidates | Confirmed | Kept | Merged |
|---|---|---|---|---|---|---|---|---|---|
| uci-credit-default | 56.7s | 56 | 56 | 13600 | 0 | 0 | 0 | 0 | 0 |
| adult-income | 31.5s | 56 | 56 | 13600 | 400 | 1 | 1 | 1 | 0 |

## Age main effects (generalized treatment `age`, comparison `<35`)

| Target | Level | n | b | c | Net flip | Corrected p | MDE | Testable |
|---|---|---|---|---|---|---|---|---|
| uci-credit-default | 35-44 | 1000 | 0 | 0 | +0.0000 | 1 | 0.044 | True |
| uci-credit-default | 45+ | 1000 | 0 | 0 | +0.0000 | 1 | 0.044 | True |
| adult-income | 35-44 | 1000 | 0 | 0 | +0.0000 | 1 | 0.044 | True |
| adult-income | 45+ | 1000 | 0 | 6 | -0.0060 | 1 | 0.044 | True |

## Kept findings (generalized protocol)

| Target | Finding | Treatment | Context | Confirmation n | Net flip | Corrected p |
|---|---|---|---|---|---|---|
| uci-credit-default | (none) | - | - | - | - | - |
| adult-income | gen-gender-female-age-45plus-urban_rural-rural-name_group-n2 | gender=female | age=45+, urban_rural=rural, name_group=N2 | 400 | +0.0500 | 0.0273 |

Merged cells stay in the result files with their reasons; they are not counted as kept findings.

