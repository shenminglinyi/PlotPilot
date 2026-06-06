type EnvValue = string | boolean | undefined

function envFlag(value: EnvValue): boolean {
  if (typeof value === 'boolean') return value
  if (typeof value !== 'string') return false
  return ['1', 'true', 'yes', 'on', 'enabled'].includes(value.trim().toLowerCase())
}

const aiInvocationDebug = envFlag(import.meta.env.VITE_ENABLE_AI_INVOCATION_DEBUG)

export const featureFlags = Object.freeze({
  aiInvocationDebug,
  variableCenterDebugPanels: aiInvocationDebug,
})

export type FeatureFlags = typeof featureFlags
