# Architecture decisions

1. Python and FastAPI provide a small API with interactive Swagger docs.
2. A modular monolith avoids unnecessary infrastructure.
3. Local JSON persistence keeps the prototype easy to run; production multi-worker use needs PostgreSQL transactions and row locks.
4. Predictive pacing is rule-based and explainable; no ML is required by the assignment.
5. The pacing engine only recommends a call count; the independent safety cap limits actual starts to available agents and queued borrowers.
6. Two mock providers demonstrate reliable and flaky behaviour.
7. Dataset import deduplicates borrower IDs and derives queue priority from account DPD.
8. Provider events are monotonic: duplicate events are idempotent and late non-terminal events cannot move a call backward.
9. Restart recovery marks in-flight calls for reconciliation; repeated provider timeouts trip the safety controller and stop new calls for that provider.
