import { powerSystemApi, type PowerSystemOverview } from '@/api/powerSystem'

async function check() {
  const overview: PowerSystemOverview = await powerSystemApi.getOverview('novel-id')
  await powerSystemApi.saveRules('novel-id', {
    tier_schema: overview.rules.tier_schema,
    core_rules: overview.standard,
  })
  await powerSystemApi.saveProfile('novel-id', {
    character_name: '林夜',
    rank_score: 80,
  })
  await powerSystemApi.createEvent('novel-id', {
    chapter_number: 1,
    character_name: '林夜',
    power_delta: 1,
  })
}

void check
