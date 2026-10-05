# Contracts

For engineers who consume the platform's events or implement a new adapter. It lists the event types and links the port interfaces. The HTTP contract is in [../api/README.md](../api/README.md).

## Events
Events are CloudEvents 1.0 with the JSON data inline.
- **Fields:** `specversion` is `1.0`. `id` is a UUID, and consumers dedupe on it. `type` is versioned, for example `platform.gateway.decision.v1`. `source` names the producing component. `subject` is the id the event is about. `time` is RFC 3339. One extension attribute is added: `tenantid`.
- **Delivery:** at least once. Within a tenant, events arrive in the order they were written. There is no order between tenants.
- **Content:** events never carry input text, file content or secrets. They carry ids, outcomes, counts and, for ingestion, the file's content hash. A decision event does not carry the input hash.
- **On Kafka:** the topic is `platform.<type without its version>`, the key is the tenant id, and the encoding is binary mode, with the attributes as `ce_*` headers and the data as the value. A message that a consumer cannot handle after `KAFKA_MAX_ATTEMPTS` goes to `<topic>.dlq`, with headers that say why and where it came from.
- **Versions:** a breaking change to an event's data creates a new type version. The old one is kept until its consumers move.

The table below is generated from `ports/events.py`, and a unit test checks each row's data fields against the real event.

<!-- BEGIN GENERATED: event-types -->
| Type | Kafka topic | Source | Subject | Meaning | Data fields |
|---|---|---|---|---|---|
| `platform.gateway.decision.v1` | `platform.gateway.decision` | `/gateway` | the decision id | The gateway recorded a decision, allow or deny. It is written in the decision's transaction. It holds the verdict and ids, never the input text or its hash. | `decision_id`, `outcome`, `stage`, `reason`, `action`, `resource`, `request_id`, `execution_id` |
| `platform.ingest.completed.v1` | `platform.ingest.completed` | `/ingest` | the job id | A worker finished an ingest job. It holds ids, the content hash and counts, never file content. | `job_id`, `document_id`, `namespace`, `content_hash`, `status`, `total_chunks` |
| `platform.gateway.purge.v1` | `platform.gateway.purge` | `/gateway/retention` | the job id | A worker purged expired decision records of one tenant. It holds counts and the chain checkpoint, no decision content. | `job_id`, `purged`, `retention_days`, `checkpoint_position`, `checkpoint_hash` |
<!-- END GENERATED: event-types -->

## Ports
The platform reaches every external system through a typed port, so a provider can be swapped by configuration. [ports.md](ports.md) lists the interfaces an adapter implements most often. All ports are in `ports/`, and the shared contract suites in `tests/contracts/` check every adapter of a port.

To add an adapter:
1. Implement the port in `adapters/`, the only package that may import a provider SDK.
2. Register it in `adapters/registry.py` under a settings value.
3. Run the port's contract suite against it.
