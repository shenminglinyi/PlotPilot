import { continuityApi, type ContinuityOverviewResponse } from '@/api/continuity'

async function check() {
  const overview: ContinuityOverviewResponse = await continuityApi.getOverview('novel-id', 1)
  const firstSignal = overview.relationship_tracking.active_signals[0]
  const firstNode = overview.outline_deviation.outline_nodes[0]

  if (firstSignal?.source === 'structured') {
    await continuityApi.recordRelationshipEvent('novel-id', {
      chapter_number: overview.chapter_number,
      source_character: firstSignal.source_character,
      target_character: firstSignal.target_character,
      relation: firstSignal.relation,
      event_type: firstSignal.change_signal,
      evidence: firstSignal.signal_excerpt,
      severity: firstSignal.severity,
    })
  }

  if (firstNode) {
    await continuityApi.upsertOutlineNodeStatus('novel-id', {
      chapter_number: overview.chapter_number,
      node_key: firstNode.node_key,
      outline_text: firstNode.outline_text,
      status: firstNode.status,
      note: firstNode.note,
      evidence: firstNode.evidence,
    })
  }
}

void check
