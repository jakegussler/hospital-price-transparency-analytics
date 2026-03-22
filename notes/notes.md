
## Data & Infrastructure Questions 


- How do you handle the wide variance in hospital file formats? (JSON, CSV, wide vs. long, inconsistent code usage)
- How do you normalize procedures across hospitals? (CDM code matching, HCPCS/CPT standardization, - description fuzzy matching)
- How do you model multi-terabyte pricing files efficiently at scale? (file ingestion strategy, schema design, partitioning)
- How do you define and handle data quality — missing rates, clearly erroneous values ($1 or $10M charges)?




## The narrative layer

- "You could pay X times more for the same procedure depending on which hospital you choose in [city]"
- "Self-pay rates beat negotiated rates at X% of hospitals for these procedures"
- "Hospital consolidation in [market] correlates with higher negotiated rates"


## Potential themes to focus on:
- Market variation: Where are prices most different for the same thing?”
- Cash vs negotiated: “When is self-pay cheaper than insurance-negotiated pricing?
- Payer leverage: Which insurers appear to negotiate best?
- Transparency/compliance quality: Which hospitals publish usable, complete, standardized data?