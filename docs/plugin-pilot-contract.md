# Official character candidate pilot: integration contract

Experimental, manual-only official plugin flow. Host API `0.1` reads one saved
chapter and one existing character, produces a persistent candidate, then requires
separate human confirmation to adopt its field changes. No automatic daemon use.

## API and UI paths

- Vue: `/plugins/character-candidates`, linked from each novel workbench top bar.
- Prefix: `/api/v1/plugin-pilot`.
- `GET /catalog`: validated official manifest metadata and hard budgets.
- `GET /projects`: existing novels (IDs, slugs, titles only).
- `GET /projects/{project_id}/inputs`: saved chapter and canonical character choices.
- `GET /model`: active model identity only, no keys; consent binds this identity.
- `POST /runs`: plugin ID, project ID, one saved chapter ID, one existing character
  ID, model identity, and explicit consent. One model invocation; validated output
  is persisted as an independent candidate. No manuscript or character writes.
- `GET /projects/{project_id}/candidates`: persistent candidates, full before/after
  diff, exact quoted evidence, source/target revision snapshots and adoption state.
- `POST /candidates/{candidate_id}/adopt`: project ID, stable client command ID,
  explicit confirmation. Returns committed result or `pending`, never queue=true
  as success.
- `GET /projects/{project_id}/commands/{command_id}`: query uncertain submission.

## Minimal implementation

Fixed `official-plugins/` JSON manifests plus plain-text templates; only the host's
finite read/render/invoke/validate/submit action sequence. No code, eval, imports,
user package directory, dynamic HTML or plugin-ID-specific execution branch.
Host-defined `character_card_patch@1` allows only personality, appearance and
core_motivation strings, with evidence copied from the chosen chapter.

Revision sidecar and INSERT/UPDATE/DELETE triggers on `chapters` and
`unified_characters` cover legacy upserts, Bible delete/reinsert and ABA. Tombstones
survive deletes. Any source or target change rejects adoption and requires a new
generation; there is no source-reconfirmation UX in this pilot.

The existing PersistenceQueue provides a bounded local acknowledged command
lane. Snapshot, candidate storage and adoption handlers execute on its real writer
thread. Adoption reads versions, conditionally updates the canonical row, checks
real rowcount, and stores adoption plus durable command result in one transaction.
Async callers wait without blocking the event loop. Stable command IDs bind a
payload hash; unknown outcomes are queried, not blindly retried.

Existing LLMControlService/profile and LLMProviderFactory/LLMService are reused.
The pilot enforces small output caps despite legacy config minimums and bounds
provider HTTP attempts as well as host-level calls. Fake LLM injection is test-only.
Existing cloud connector routes and behavior remain intact.

For `pending` or a failed response, query the same command ID. An `unknown` result
does not prove failure. The UI allows an explicit manual retry using the identical
original command ID and payload; it never automatically resends or replaces IDs.
