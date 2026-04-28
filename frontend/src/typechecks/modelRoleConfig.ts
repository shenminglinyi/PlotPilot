import {
  DEFAULT_MODEL_ROLE_CONFIG,
  buildModelRoleSummary,
  getModelLabel,
  getModelOptions,
  loadModelRoleConfig,
  saveModelRoleConfig,
  upsertModelProfile,
  type ModelRoleConfig,
} from '@/utils/modelRoleConfig'

const config: ModelRoleConfig = loadModelRoleConfig()
const writerOptions = getModelOptions(config, 'writer')
const supervisorOptions = getModelOptions(config, 'supervisor')
const writerLabel: string = getModelLabel(config, config.writingModel)
const summary: string = buildModelRoleSummary(config)

saveModelRoleConfig({
  ...DEFAULT_MODEL_ROLE_CONFIG,
  writingModel: writerOptions[0]?.value || 'custom-writer',
})

const updated = upsertModelProfile(config, {
  value: 'custom-model',
  label: '自定义模型',
  role: 'both',
})

void supervisorOptions
void writerLabel
void summary
void updated
