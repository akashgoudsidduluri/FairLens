\# FairLens India



\*An agentic auditor for black-box lending models.\*



\*\*Event:\*\* OpenQuest Innovation Challenge, Vasavi College of Engineering

\*\*Domain:\*\* 6, Responsible AI, Privacy, Trust \& Accessibility (Trust track)



\---



\## Problem Statement



AI models that approve loans can discriminate by gender, region, or caste-linked signals such as names and pincodes. The affected people, and often the auditors, cannot see inside the model. Existing fairness toolkits need the model's data and internals and return abstract metrics that are hard to act on or verify. There is no practical way to independently audit a black-box lending model, separate real bias from legitimate explanations such as income differences, and produce evidence others can trust.



\---



\## Description



FairLens India investigates a lending model through its API, without needing its data or internals. Four agents work in sequence, with a human making the final call:



1\. \*\*Prober:\*\* creates twin applicants identical except for one signal (gender, name group, or pincode group) and sends them to the model.

2\. \*\*Statistician:\*\* measures how often the twin gets a different decision, with confidence intervals and multiple-testing correction, and scans for the worst-hit intersectional subgroups.

3\. \*\*Skeptic:\*\* tries to disprove each finding (too few samples, explained by income, statistically weak or immaterial) and rejects the ones that don't hold up.

4\. \*\*Reporter:\*\* explains the surviving findings in plain language, using only numbers computed by code, never invented by the LLM.

5\. \*\*Human auditor:\*\* reviews and approves, which issues a hash-chained certificate anyone can verify. Tampering makes verification fail.



The dashboard also shows an impact estimate (people wrongly rejected per 10,000) and a fairness-vs-accuracy trade-off slider.



\---



\## Use Case



A bank, regulator, or civil-society auditor wants to check whether a loan-approval model treats applicants fairly, but only has access to the model's API. FairLens probes it with twin applicants, separates genuine bias from legitimate differences such as income, translates the result into human impact, and produces a verifiable certificate that a human auditor has signed off.



\*\*Other uses:\*\* pre-deployment fairness checks, regulator spot-audits, and a future CI/CD fairness gate for model releases.



\---



\## Responsible Design



\- Synthetic data only, no personal or confidential data

\- The LLM explains but never computes

\- A human must approve before any certificate is issued

\- Limitations: probing gives evidence of bias, not proof of fairness, and the base data is not Indian lending data



\---



\## Quick Start



```bash

git clone <your-repo-url> \&\& cd fairlens

pip install -r requirements.txt

cp .env.example .env        # add ANTHROPIC\_API\_KEY (optional; template fallback works without it)

./run.sh                    # starts the sandbox API and the Streamlit dashboard

```



\*(Setup commands will be finalized once the build is complete.)\*



\---



\## Pitch



> \*"Fairlearn gives you a number. FairLens investigates the model like an auditor: it probes it live, challenges its own findings, and issues a certificate a human signs."\*

