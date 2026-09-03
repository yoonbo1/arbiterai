# Scaling to millions of requests: cloud options

The filter that matters most: **will the vendor sign a BAA for the specific service you use?**
A cloud signing a BAA for storage does not mean its GPU or managed-inference product is covered.
Verify per-service, and verify prices at decision time; GPU pricing moves monthly.

## Option A — Big three hyperscaler (safest compliance path)

| | AWS | Azure | GCP |
|---|---|---|---|
| BAA | Yes, broad service list | Yes, broad | Yes, broad |
| GPU compute | EC2 g6/g6e (L4/L40S), p4d/p5 (A100/H100) | NC/ND series | G2 (L4), A3 (H100) |
| Managed inference w/ BAA | Bedrock (Anthropic, Meta, Mistral models) | Azure OpenAI, AI Foundry | Vertex AI |
| Kubernetes | EKS | AKS | GKE |
| Queue | SQS / MSK (Kafka) | Service Bus / Event Hubs | Pub/Sub |
| Postgres+pgvector | RDS / Aurora | Flexible Server | Cloud SQL / AlloyDB |
| Object storage | S3 + KMS | Blob + Key Vault | GCS + Cloud KMS |

**Fit for this system:** run the whole compose stack on EKS/AKS/GKE. Workers autoscale on queue
depth (KEDA), vLLM pods on GPU utilization. Use spot/preemptible GPUs for the *ingestion* pool
(batch, retry-safe) and on-demand for the *query* pool (latency-sensitive).
**Cost saver:** route escalations to Bedrock/Azure OpenAI under BAA instead of keeping a large
model warm 24/7 — you pay per token only when the small model fails validation.
**Tradeoff:** highest unit cost for raw GPU hours; lowest compliance and ops risk. Pick this if
enterprise hospital customers will audit you.

## Option B — GPU-specialist clouds (cheapest GPU hours)

CoreWeave, Lambda, Crusoe, Nebius, and similar offer H100/A100/L40S at a fraction of
hyperscaler on-demand rates, often with managed Kubernetes.
**Check:** BAA availability (some sign, some don't), SOC 2 / HITRUST reports, data-center
region, and whether they offer private networking to your database tier.
**Pattern:** keep the control plane (gateway, Postgres, queue, object storage) on a hyperscaler
under its BAA; run only the stateless model pools on the GPU cloud over a private link, sending
**de-identified** payloads only. Since text is scrubbed before it reaches the models, this
lowers what the GPU vendor's BAA has to cover.
**Tradeoff:** two vendors, two BAAs, cross-cloud egress fees, more network design.

## Option C — Colocation / owned hardware (lowest cost at sustained volume)

At millions of requests/day with steady load, owning 8–16 GPUs in a HIPAA-audited colo
(Equinix, Flexential, etc.) typically beats cloud on a 2–3 year horizon.
**Pattern:** buy L40S/H100 nodes for the baseline; burst to Option A or B for spikes.
**Tradeoff:** capex, hardware ops, capacity planning, your own physical-security controls.

## Option D — Healthcare-focused platforms

Vendors that are already HIPAA/HITRUST-certified for AI workloads (e.g., cloud marketplaces
with healthcare-specific compliance packages, or healthcare AI infra startups) can shorten the
audit conversation. Usually a premium on top of hyperscaler pricing.
**Tradeoff:** less control, vendor lock-in, still need your own risk analysis.

## Recommended path

1. **Test (now):** one on-prem or rented single-GPU box, as in this repo.
2. **Pilot (first paying tenants):** Option A, one region, EKS/GKE, spot GPUs for ingestion,
   managed Postgres with pgvector, Bedrock/Azure OpenAI under BAA as the escalation tier.
   This gets you a clean compliance story fast.
3. **Scale (millions/day):** measure the split between small/large model tokens from the
   `jobs` table. If large-model spend dominates, move to reserved/committed GPU capacity
   (Option A savings plans or Option B). If sustained utilization is >60%, evaluate Option C
   for the baseline and keep cloud for burst.
4. **Multi-region / data residency:** offer a dedicated-isolation tier per tenant as its own
   Kubernetes namespace or cluster in the tenant's required region.

## Sizing rule of thumb (verify with your own metering)

- One quantized 7–8B model on one L4/L40S with vLLM handles roughly 300–600 queries/min at
  typical RAG prompt sizes. Millions/day ≈ 700–1,400/min average with 3–5× peak, so plan for
  4–10 small-model GPUs at peak, plus 1–3 large/VLM GPUs.
- Ingestion is bursty; size it on document backlog and run it on spot.
- Postgres with pgvector is fine to tens of millions of chunks per tenant with HNSW; beyond that
  or for very high QPS, consider a dedicated vector DB (Qdrant/Milvus/Weaviate, self-hosted).
