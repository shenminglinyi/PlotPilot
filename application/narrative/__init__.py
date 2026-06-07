"""Narrative fact services.

This package is the shared spine for cross-entity narrative truth:

    text / manual edit / model extraction
        -> EntityResolver
        -> narrative_events
        -> projections: triples, entity state, context, UI

Bounded-context tables such as ``prop_events`` remain their aggregate logs, but
cross-entity changes should also be mirrored into ``narrative_events`` with
entity-scoped mutations. That gives characters, props, knowledge graph, context
assembly, and UI relation views one replayable source of truth instead of many
independent fact copies.
"""
