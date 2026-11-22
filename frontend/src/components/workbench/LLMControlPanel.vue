<template>
  <div ref="rootScrollRef" class="llm-panel" data-ui>
    <!-- 顶部核心状态与主操作栏 -->
    <div class="llm-top-ledger">
      <div class="llm-ledger-cells">
        <div class="llm-ledger-cell">
          <span class="llm-ledger-caption">当前执笔模型</span>
          <div class="llm-ledger-value-row">
            <strong class="llm-ledger-value">{{ activeModelHeadline }}</strong>
            <span class="llm-status-pill" :class="runtimeReady ? 'is-ready' : 'is-pending'">
              {{ authSourceBadgeText }}
            </span>
          </div>
          <span class="llm-ledger-sub">{{ activeRouteExplanation }}</span>
        </div>

        <div class="llm-ledger-cell">
          <span class="llm-ledger-caption">路由编组策略</span>
          <div class="llm-ledger-value-row">
            <strong class="llm-ledger-value">
              {{ isIndependentMode ? '省额度分角色编组' : '统一单模型' }}
            </strong>
          </div>
          <span class="llm-ledger-sub">{{ roleSummaryLine }}</span>
        </div>
      </div>

      <div class="llm-ledger-actions">
        <n-button size="small" :loading="loading" @click="reloadAll">
          刷新状态
        </n-button>
        <n-button
          size="small"
          :loading="testing"
          :disabled="!activeMainProfile"
          @click="testProfileTarget(activeMainProfile)"
        >
          测试执笔连接
        </n-button>
        <n-button
          size="small"
          type="primary"
          :loading="saving"
          :disabled="!panelData"
          @click="saveAll"
        >
          保存配置
        </n-button>
      </div>
    </div>

    <div v-if="panelData?.runtime?.using_mock" class="llm-inline-notice">
      <span class="llm-inline-notice-title">尚未就绪：</span>
      <span>{{ panelData.runtime.reason || '请先在下方一键接入本机订阅网关、连接公开 OAuth 账号，或在高级配置中填写密钥。' }}</span>
    </div>

    <div class="llm-scroll-body" ref="editorRef">
      <!-- 第一屏核心区：免密钥直连（本机网关嗅探 + 标准公开 OAuth） -->
      <section class="llm-section">
        <div class="llm-section-head">
          <div>
            <h3 class="llm-section-title">免密钥直连：本机订阅网关与公开 OAuth</h3>
            <p class="llm-section-desc">
              直接复用本机已登录的 Claude / ChatGPT / Gemini / Grok 订阅桥接网关，或通过标准公开 PKCE / 设备码安全授权，凭据仅以 0600 权限保存在本机后端。
            </p>
          </div>
        </div>

        <div class="llm-connect-grid">
          <!-- 左栏：L2 本机订阅网关 (Magpie) 与官方 CLI 嗅探 -->
          <div class="llm-surface-card">
            <div class="llm-card-top">
              <div>
                <h4 class="llm-card-heading">本机订阅网关与 CLI 嗅探</h4>
                <p class="llm-card-copy">
                  自动检测本机回环端口（默认 Magpie <code>127.0.0.1:3425</code>），免填 API Key 拉取全部已登录订阅模型。
                </p>
              </div>
              <n-button size="small" :loading="probingGateways" @click="handleProbeGateways(false)">
                探测本机网关
              </n-button>
            </div>

            <div class="llm-gateway-custom-row">
              <n-input
                v-model:value="customGatewayUrl"
                size="small"
                placeholder="可选本机回环地址，例如 http://127.0.0.1:3425/v1"
              />
            </div>

            <div v-if="reachableGateways.length" class="llm-gateway-list">
              <div
                v-for="gw in reachableGateways"
                :key="gw.base_url"
                class="llm-gateway-item"
              >
                <div class="llm-gateway-item-head">
                  <div class="llm-gateway-title-group">
                    <span class="llm-gateway-name">{{ gw.name }}</span>
                    <span class="llm-status-pill is-ready">
                      在线 · {{ gw.latency_ms }}ms · {{ gw.models.length }} 模型
                    </span>
                  </div>
                  <span class="llm-gateway-url">{{ gw.base_url }}</span>
                </div>

                <div class="llm-gateway-recommend">
                  <span>黄金编组推荐：</span>
                  <span>主力 <code>{{ gw.recommended_roles.main || '-' }}</code></span>
                  <span>· 摘要 <code>{{ gw.recommended_roles.cheap || '-' }}</code></span>
                  <span>· 图谱 <code>{{ gw.recommended_roles.kg || '-' }}</code></span>
                </div>

                <div class="llm-gateway-btn-row">
                  <n-button
                    size="small"
                    type="primary"
                    :loading="connectingGatewayUrl === gw.base_url"
                    @click="handleConnectGateway(gw, true)"
                  >
                    一键接入并启用省额度编组
                  </n-button>
                  <n-button
                    size="small"
                    :loading="connectingGatewayUrl === gw.base_url"
                    @click="handleConnectGateway(gw, false)"
                  >
                    仅接入主力单模型
                  </n-button>
                </div>
              </div>
            </div>

            <div v-else class="llm-empty-slot">
              <span>
                {{
                  gatewayProbedOnce
                    ? '暂未在 127.0.0.1:3425 检出在线订阅网关。若你使用其他本机端口，请在上方填入后点击「探测本机网关」。'
                    : '点击右上角「探测本机网关」扫描本机回环订阅桥接服务。'
                }}
              </span>
            </div>

            <div v-if="cliTools.length" class="llm-cli-strip">
              <span class="llm-cli-label">本机 CLI 环境：</span>
              <span
                v-for="cli in cliTools"
                :key="cli.id"
                class="llm-cli-chip"
                :class="{ 'is-detected': cli.installed }"
                :title="cli.note"
              >
                {{ cli.name }} · {{ cli.installed ? (cli.authenticated_hint ? '已就绪' : '已安装') : '未检出' }}
              </span>
            </div>
          </div>

          <!-- 右栏：L1 标准公开 OAuth 授权 -->
          <div class="llm-surface-card">
            <div class="llm-card-top">
              <div>
                <h4 class="llm-card-heading">标准公开 OAuth 账号连接</h4>
                <p class="llm-card-copy">
                  遵循公开 PKCE 与 RFC 8628 设备码标准，刷新令牌只驻留本机后端，前端零明文落盘。
                </p>
              </div>
            </div>

            <div class="llm-oauth-list">
              <!-- OpenRouter PKCE -->
              <div class="llm-oauth-row">
                <div class="llm-oauth-info">
                  <div class="llm-oauth-title-line">
                    <span class="llm-oauth-name">OpenRouter</span>
                    <span
                      class="llm-status-pill"
                      :class="oauthMap.openrouter?.connected ? 'is-ready' : 'is-neutral'"
                    >
                      {{ oauthMap.openrouter?.connected ? '已授权' : 'PKCE 零配置' }}
                    </span>
                  </div>
                  <span class="llm-oauth-desc">
                    {{ oauthMap.openrouter?.connected ? (oauthMap.openrouter.account_label || '本机后端已托管 PKCE 密钥') : '无需预置 Client ID，浏览器一键授权直连数百款模型' }}
                  </span>
                </div>
                <div class="llm-oauth-actions">
                  <n-button
                    size="small"
                    :type="oauthMap.openrouter?.connected ? 'default' : 'primary'"
                    :loading="oauthBusy === 'openrouter'"
                    @click="handleStartOpenRouter"
                  >
                    {{ oauthMap.openrouter?.connected ? '重新授权' : '一键授权连接' }}
                  </n-button>
                  <n-button
                    v-if="oauthMap.openrouter?.connected"
                    size="small"
                    :loading="oauthBusy === 'openrouter-disconnect'"
                    @click="handleDisconnectOAuth('openrouter')"
                  >
                    断开
                  </n-button>
                </div>
              </div>

              <!-- GitHub Models Device Flow -->
              <div class="llm-oauth-row">
                <div class="llm-oauth-info">
                  <div class="llm-oauth-title-line">
                    <span class="llm-oauth-name">GitHub Models</span>
                    <span
                      class="llm-status-pill"
                      :class="oauthMap.github_models?.connected ? 'is-ready' : 'is-neutral'"
                    >
                      {{ oauthMap.github_models?.connected ? '已授权' : '设备码授权' }}
                    </span>
                  </div>
                  <span class="llm-oauth-desc">
                    {{ oauthMap.github_models?.connected ? (oauthMap.github_models.account_label || 'GitHub 设备码凭据已就绪') : 'RFC 8628 标准设备码流程，免回调端口映射' }}
                  </span>

                  <div v-if="showGithubClientInput && !oauthMap.github_models?.connected" class="llm-oauth-inline-input">
                    <n-input
                      v-model:value="githubClientIdInput"
                      size="small"
                      placeholder="输入 GitHub OAuth App Client ID（或配置环境变量）"
                    />
                  </div>

                  <div v-if="deviceFlowState" class="llm-device-code-box">
                    <div class="llm-device-code-line">
                      <span>设备验证码：</span>
                      <code class="llm-device-code-val">{{ deviceFlowState.user_code }}</code>
                      <n-button size="tiny" @click="openExternalUrl(deviceFlowState.verification_uri)">
                        打开验证页
                      </n-button>
                    </div>
                    <span class="llm-device-code-hint">{{ deviceFlowStatusText }}</span>
                  </div>
                </div>

                <div class="llm-oauth-actions">
                  <n-button
                    size="small"
                    :loading="oauthBusy === 'github_models'"
                    @click="handleStartGitHubDevice"
                  >
                    {{ oauthMap.github_models?.connected ? '重新授权' : '获取设备码' }}
                  </n-button>
                  <n-button
                    v-if="oauthMap.github_models?.connected"
                    size="small"
                    :loading="oauthBusy === 'github_models-disconnect'"
                    @click="handleDisconnectOAuth('github_models')"
                  >
                    断开
                  </n-button>
                </div>
              </div>

              <!-- Google Gemini OAuth PKCE -->
              <div class="llm-oauth-row">
                <div class="llm-oauth-info">
                  <div class="llm-oauth-title-line">
                    <span class="llm-oauth-name">Google Gemini</span>
                    <span
                      class="llm-status-pill"
                      :class="oauthMap.google_gemini?.connected ? 'is-ready' : 'is-neutral'"
                    >
                      {{ oauthMap.google_gemini?.connected ? '已授权' : 'OAuth PKCE' }}
                    </span>
                  </div>
                  <span class="llm-oauth-desc">
                    {{ oauthMap.google_gemini?.connected ? (oauthMap.google_gemini.account_label || 'Google OAuth 令牌自动续期中') : '桌面端 PKCE 授权，自动刷新短期访问令牌' }}
                  </span>

                  <div v-if="showGoogleClientInput && !oauthMap.google_gemini?.connected" class="llm-oauth-inline-input">
                    <n-input
                      v-model:value="googleClientIdInput"
                      size="small"
                      placeholder="Google Desktop OAuth Client ID"
                    />
                    <n-input
                      v-model:value="googleClientSecretInput"
                      type="password"
                      show-password-on="click"
                      size="small"
                      placeholder="可选 Client Secret（桌面应用若下发可填）"
                    />
                  </div>
                </div>

                <div class="llm-oauth-actions">
                  <n-button
                    size="small"
                    :loading="oauthBusy === 'google_gemini'"
                    @click="handleStartGoogleOAuth"
                  >
                    {{ oauthMap.google_gemini?.connected ? '重新授权' : '连接 Gemini' }}
                  </n-button>
                  <n-button
                    v-if="oauthMap.google_gemini?.connected"
                    size="small"
                    :loading="oauthBusy === 'google_gemini-disconnect'"
                    @click="handleDisconnectOAuth('google_gemini')"
                  >
                    断开
                  </n-button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <!-- 第二区：L3 省额度分角色智能路由（黄金编组） -->
      <section class="llm-section">
        <div class="llm-section-head">
          <div>
            <h3 class="llm-section-title">省额度黄金编组（分角色智能分流）</h3>
            <p class="llm-section-desc">
              把好钢用在正文执笔与核心大纲上；章后摘要、一致性巡检与知识图谱三元组自动分流至高配额轻量模型，次级角色未就绪时自动回退主力模型。
            </p>
          </div>

          <div class="llm-mode-controls">
            <div class="llm-mode-segmented" role="tablist" aria-label="路由编组模式">
              <button
                type="button"
                class="llm-seg-btn"
                :class="{ 'is-active': !isIndependentMode }"
                @click="setEndpointMode('unified')"
              >
                统一单模型
              </button>
              <button
                type="button"
                class="llm-seg-btn"
                :class="{ 'is-active': isIndependentMode }"
                @click="setEndpointMode('independent')"
              >
                省额度分角色编组
              </button>
            </div>

            <n-button
              size="small"
              :loading="applyingGolden"
              :disabled="!activeMainProfile"
              @click="handleAutoComposeGoldenRoles"
            >
              智能配平省额度编组
            </n-button>
          </div>
        </div>

        <div v-if="isIndependentMode && panelData" class="llm-role-table">
          <div
            v-for="slot in roleSlotRows"
            :key="slot.role"
            class="llm-role-row"
          >
            <div class="llm-role-meta">
              <div class="llm-role-title-line">
                <span class="llm-role-title">{{ slot.title }}</span>
                <span class="llm-role-badge" :class="`role-${slot.role}`">{{ slot.badge }}</span>
              </div>
              <span class="llm-role-scope">{{ slot.scope }}</span>
            </div>

            <div class="llm-role-controls">
              <n-select
                :value="slot.boundProfileId"
                :options="profileSelectOptions"
                size="small"
                placeholder="选择承载档案"
                @update:value="(val: string) => handleBindRoleProfile(slot.role, val)"
              />
              <n-input
                v-if="slot.profile"
                v-model:value="slot.profile.model"
                size="small"
                placeholder="输入该角色使用的模型 ID"
              />
            </div>
          </div>
        </div>

        <div v-else class="llm-unified-note">
          当前处于「统一单模型」模式：正文执笔、章后摘要与知识图谱均共用激活档案
          <strong>{{ activeMainProfile?.name || '默认档案' }}</strong>
          （<code>{{ activeMainProfile?.model || '未填模型' }}</code>）。点击上方「省额度分角色编组」或「智能配平省额度编组」即可开启自动分流。
        </div>
      </section>

      <!-- 第三区：高级手动配置与完整档案库（默认收折） -->
      <section class="llm-section llm-manual-section">
        <button
          type="button"
          class="llm-collapse-trigger"
          :aria-expanded="showManualSection"
          @click="showManualSection = !showManualSection"
        >
          <div class="llm-collapse-title-wrap">
            <span class="llm-section-title">高级手动配置与档案库</span>
            <span class="llm-collapse-meta">
              共 {{ panelData?.config.profiles.length || 0 }} 份档案 · 自定义 Base URL / 协议 / API Key / JSON 请求体
            </span>
          </div>
          <span class="llm-collapse-action">{{ showManualSection ? '收起面板' : '展开配置' }}</span>
        </button>

        <div v-show="showManualSection" class="llm-manual-body">
          <!-- 快速预设导入条 -->
          <div v-if="quickImportPresets.length" class="llm-preset-strip">
            <div class="llm-preset-strip-head">
              <span class="llm-preset-strip-title">常用供应商模板</span>
              <span class="llm-preset-strip-desc">点击一键新建对应协议与默认端点的空白档案</span>
            </div>
            <div class="llm-preset-grid">
              <button
                v-for="preset in quickImportPresets"
                :key="preset.key"
                type="button"
                class="llm-preset-card"
                @click="quickImportPreset(preset)"
              >
                <div class="llm-preset-card-head">
                  <span class="llm-preset-card-title">{{ preset.label }}</span>
                  <span class="llm-preset-card-protocol">{{ preset.protocol }}</span>
                </div>
                <div class="llm-preset-card-model">{{ preset.default_model || '手动指定模型' }}</div>
              </button>
            </div>
          </div>

          <div class="llm-layout">
            <div class="llm-sidebar">
              <div class="llm-sidebar-head">
                <div>
                  <div class="llm-sidebar-title">模型档案列表</div>
                  <div class="llm-sidebar-desc">点击编辑，设为激活即作为默认主力档案</div>
                </div>
                <n-space size="small">
                  <n-button size="tiny" @click="createProfile">新增</n-button>
                  <n-button size="tiny" :disabled="!selectedProfile" @click="duplicateProfile">复制</n-button>
                </n-space>
              </div>

              <div ref="sidebarListRef" class="llm-profile-list">
                <button
                  v-for="profile in panelData?.config.profiles || []"
                  :key="profile.id"
                  type="button"
                  class="llm-profile-item"
                  :class="{
                    'is-selected': profile.id === selectedProfileId,
                    'is-active': profile.id === panelData?.config.active_profile_id,
                  }"
                  @click="selectProfile(profile.id)"
                >
                  <div class="llm-profile-name-row">
                    <span class="llm-profile-name">{{ profile.name }}</span>
                    <span v-if="profile.id === panelData?.config.active_profile_id" class="llm-status-pill is-ready">
                      主力激活
                    </span>
                  </div>
                  <div class="llm-profile-meta">
                    {{ formatProfileAuthTag(profile) }} · {{ profile.model || '未填模型' }}
                  </div>
                </button>
              </div>
            </div>

            <div class="llm-editor">
              <n-card v-if="selectedProfile" size="small" :bordered="true" class="llm-card">
                <template #header>
                  <div class="llm-card-head">
                    <div>
                      <div class="llm-card-title">{{ selectedProfile.name || '未命名配置' }}</div>
                      <div class="llm-card-desc">
                        {{ selectedPreset?.description || '支持标准 OpenAI / Anthropic / Gemini 协议与扩展请求参数' }}
                      </div>
                    </div>
                    <n-space size="small">
                      <n-button
                        size="small"
                        :loading="testing"
                        @click="testSelected"
                      >
                        测试此档案
                      </n-button>
                      <n-button
                        size="small"
                        :disabled="selectedProfile.id === panelData?.config.active_profile_id"
                        @click="activateSelected"
                      >
                        设为主力激活
                      </n-button>
                      <n-button
                        size="small"
                        type="error"
                        secondary
                        :disabled="(panelData?.config.profiles.length || 0) <= 1"
                        @click="deleteSelected"
                      >
                        删除
                      </n-button>
                    </n-space>
                  </div>
                </template>

                <div class="llm-form-grid">
                  <div class="llm-field">
                    <label class="llm-label">配置名称</label>
                    <n-input v-model:value="selectedProfile.name" placeholder="例如：主力模型 / DeepSeek" />
                  </div>

                  <div class="llm-field">
                    <label class="llm-label">预设模板</label>
                    <div class="llm-field-row">
                      <n-select
                        v-model:value="selectedProfile.preset_key"
                        :options="presetOptions"
                        @update:value="handlePresetChange"
                      />
                      <n-button size="small" @click="applySelectedPresetDefaults">套用预设</n-button>
                    </div>
                  </div>

                  <div class="llm-field">
                    <label class="llm-label">协议类型</label>
                    <n-select
                      v-model:value="selectedProfile.protocol"
                      :options="protocolOptions"
                      :disabled="selectedProfile.auth_mode === 'oauth'"
                    />
                  </div>

                  <div class="llm-field">
                    <label class="llm-label">模型名称</label>
                    <div class="llm-model-row">
                      <n-select
                        v-if="fetchedModels.length > 0"
                        v-model:value="selectedProfile.model"
                        filterable
                        tag
                        :options="fetchedModelOptions"
                        placeholder="选择或输入模型 ID"
                      />
                      <n-input
                        v-else
                        v-model:value="selectedProfile.model"
                        placeholder="例如：claude-sonnet-4-20250514 / gpt-4o"
                      />
                      <n-button
                        size="small"
                        :loading="fetchingModels"
                        @click="handleFetchModels"
                      >
                        拉取模型
                      </n-button>
                    </div>
                  </div>

                  <div class="llm-field span-2">
                    <label class="llm-label">Base URL</label>
                    <n-input
                      v-model:value="selectedProfile.base_url"
                      :disabled="selectedProfile.auth_mode === 'oauth'"
                      placeholder="官方默认地址可留空；中转或本机网关请填到 /v1 或根路径"
                    />
                  </div>

                  <div class="llm-field span-2">
                    <label class="llm-label">认证凭据 / API Key</label>
                    <div v-if="selectedProfile.auth_mode === 'oauth'" class="llm-secret-readonly">
                      <span>
                        当前档案绑定公开 OAuth（<code>{{ selectedProfile.oauth_provider }}</code>），访问令牌由本机后端 0600 凭据仓隔离托管，前端不读写明文密钥。
                      </span>
                    </div>
                    <div v-else-if="selectedProfile.auth_mode === 'local_gateway'" class="llm-secret-readonly">
                      <span>
                        当前档案直连本机回环订阅网关，无需外部 API Key（如需自定义本地口令，可切换为手动密钥档案）。
                      </span>
                    </div>
                    <template v-else>
                      <n-input
                        :value="apiKeyInputDisplayValue"
                        type="password"
                        show-password-on="click"
                        :placeholder="
                          isSelectedSecretMasked
                            ? '已安全保存在本机后端（保持不变无需重填，输入新密钥即可覆盖）'
                            : '输入供应商 API Key / Token'
                        "
                        @update:value="handleManualApiKeyInput"
                      />
                      <span v-if="isSelectedSecretMasked" class="llm-secret-hint">
                        本机已存有密钥；若修改 Base URL 域名或协议，系统会要求重新输入对应密钥以防凭据跨站外泄。
                      </span>
                    </template>
                  </div>

                  <div class="llm-field">
                    <label class="llm-label">Temperature</label>
                    <n-input-number
                      v-model:value="selectedProfile.temperature"
                      :step="0.1"
                      :min="0"
                      :max="2"
                      style="width: 100%"
                    />
                  </div>

                  <div class="llm-field">
                    <label class="llm-label">Max Tokens</label>
                    <n-input-number
                      v-model:value="selectedProfile.max_tokens"
                      :step="256"
                      :min="DEFAULT_MAX_OUTPUT_TOKENS"
                      :max="1048576"
                      style="width: 100%"
                    />
                  </div>

                  <div class="llm-field">
                    <label class="llm-label">Timeout (秒)</label>
                    <n-input-number
                      v-model:value="selectedProfile.timeout_seconds"
                      :step="5"
                      :min="5"
                      :max="600"
                      style="width: 100%"
                    />
                  </div>

                  <div v-if="selectedProfile.protocol === 'openai'" class="llm-field span-2">
                    <div class="llm-legacy-row">
                      <n-switch v-model:value="selectedProfile.use_legacy_chat_completions" />
                      <span class="llm-legacy-copy">
                        兼容旧版 <code>/v1/chat/completions</code>（中转站不支持 OpenAI Responses API 时开启）
                      </span>
                    </div>
                  </div>

                  <div class="llm-field span-2">
                    <label class="llm-label">备注</label>
                    <n-input
                      v-model:value="selectedProfile.notes"
                      type="textarea"
                      :autosize="{ minRows: 2, maxRows: 4 }"
                      placeholder="记录该线路的计费池、速率限制或适用场景"
                    />
                  </div>
                </div>

                <n-collapse class="llm-advanced">
                  <n-collapse-item title="请求扩展 JSON（Headers / Query / Body）" name="advanced">
                    <div class="llm-form-grid">
                      <div class="llm-field span-2">
                        <label class="llm-label">Extra Headers (JSON)</label>
                        <n-input
                          :value="extraHeadersText"
                          type="textarea"
                          :autosize="{ minRows: 3, maxRows: 6 }"
                          @update:value="handleExtraHeadersInput"
                        />
                      </div>

                      <div class="llm-field">
                        <label class="llm-label">Extra Query (JSON)</label>
                        <n-input
                          :value="extraQueryText"
                          type="textarea"
                          :autosize="{ minRows: 3, maxRows: 6 }"
                          @update:value="handleExtraQueryInput"
                        />
                      </div>

                      <div class="llm-field">
                        <label class="llm-label">Extra Body (JSON)</label>
                        <n-input
                          :value="extraBodyText"
                          type="textarea"
                          :autosize="{ minRows: 3, maxRows: 6 }"
                          @update:value="handleExtraBodyInput"
                        />
                      </div>
                    </div>
                  </n-collapse-item>
                </n-collapse>
              </n-card>
            </div>
          </div>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import {
  NButton,
  NCard,
  NCollapse,
  NCollapseItem,
  NInput,
  NInputNumber,
  NSelect,
  NSpace,
  NSwitch,
  useMessage,
} from 'naive-ui'
import {
  MASKED_SECRET_SENTINEL,
  llmControlApi,
  type CLIStatusItem,
  type LLMOAuthProviderId,
  type LLMControlConfig,
  type LLMControlPanelData,
  type LLMPreset,
  type LLMProfile,
  type LLMProtocol,
  type LLMRoleKey,
  type LLMRuntimeSummary,
  type LocalGatewayItem,
  type ModelItem,
  type OAuthDeviceStartResponse,
  type OAuthProviderStatus,
} from '../../api/llmControl'
import { DEFAULT_MAX_OUTPUT_TOKENS } from '@/constants/llm'
import { readStorageJson, writeStorageJson } from '@/utils/storage'
import { formatApiError } from '../../utils/apiError'

interface Props {
  scrollStateKey?: string
  active?: boolean
}

interface PanelUiState {
  selectedProfileId?: string
  editorTop?: number
  sidebarTop?: number
  showManualSection?: boolean
}

const ROLE_NAME_MAIN = '主力模型'
const ROLE_NAME_CHEAP = '经济模型'
const ROLE_NAME_KG = '知识图谱模型'

const props = withDefaults(defineProps<Props>(), {
  scrollStateKey: '',
  active: true,
})

const emit = defineEmits<{
  'panel-updated': [data: LLMControlPanelData]
}>()

const message = useMessage()

const panelData = ref<LLMControlPanelData | null>(null)
const loading = ref(false)
const saving = ref(false)
const testing = ref(false)
const fetchingModels = ref(false)
const fetchedModels = ref<ModelItem[]>([])
const selectedProfileId = ref('')
const showManualSection = ref(false)
const extraHeadersText = ref('{}')
const extraQueryText = ref('{}')
const extraBodyText = ref('{}')
const rootScrollRef = ref<HTMLElement | null>(null)
const editorRef = ref<HTMLElement | null>(null)
const sidebarListRef = ref<HTMLElement | null>(null)

// L1 OAuth 状态
const oauthProviders = ref<OAuthProviderStatus[]>([])
const oauthBusy = ref('')
const showGithubClientInput = ref(false)
const githubClientIdInput = ref('')
const showGoogleClientInput = ref(false)
const googleClientIdInput = ref('')
const googleClientSecretInput = ref('')
const deviceFlowState = ref<OAuthDeviceStartResponse | null>(null)
const deviceFlowStatusText = ref('')
let devicePollTimer: ReturnType<typeof setTimeout> | null = null
let devicePollGeneration = 0
let deviceStartGeneration = 0
let deviceFlowOriginEpoch = -1
let devicePollAbort: AbortController | null = null
let authRefreshEpoch = 0
let activePanelLoadId = 0
let completionRefreshAbort: AbortController | null = null
let isUnmounted = false

interface ProfileJsonDraft {
  headers: string
  query: string
  body: string
  dirty: boolean
}

const profileJsonDrafts = new Map<string, ProfileJsonDraft>()

interface RefreshGuardOptions {
  epoch?: number
  signal?: AbortSignal
  requireActive?: boolean
}

// L2 本机网关嗅探状态
const probingGateways = ref(false)
const gatewayProbedOnce = ref(false)
const customGatewayUrl = ref('')
const discoveredGateways = ref<LocalGatewayItem[]>([])
const cliTools = ref<CLIStatusItem[]>([])
const connectingGatewayUrl = ref('')

// L3 省额度编组状态
const applyingGolden = ref(false)

const protocolOptions = [
  { label: 'OpenAI 兼容', value: 'openai' },
  { label: 'Anthropic / Claude 兼容', value: 'anthropic' },
  { label: 'Gemini', value: 'gemini' },
]

const oauthMap = computed<Partial<Record<LLMOAuthProviderId, OAuthProviderStatus>>>(() => {
  const map: Partial<Record<LLMOAuthProviderId, OAuthProviderStatus>> = {}
  for (const item of oauthProviders.value) {
    map[item.provider] = item
  }
  return map
})

const reachableGateways = computed(() =>
  discoveredGateways.value.filter((gw) => gw.reachable),
)

const presetOptions = computed(() =>
  (panelData.value?.presets || []).map((preset) => ({
    label: preset.label,
    value: preset.key,
  })),
)

const quickImportPresets = computed(() =>
  (panelData.value?.presets || []).filter((preset) => preset.key !== 'custom-openai-compatible'),
)

const selectedProfile = computed(() =>
  panelData.value?.config?.profiles.find((profile) => profile.id === selectedProfileId.value) || null,
)

const activeMainProfile = computed<LLMProfile | null>(() => {
  const cfg = panelData.value?.config
  if (!cfg || !cfg.profiles.length) return null
  const boundMain = cfg.role_bindings?.main
  if (boundMain) {
    const found = cfg.profiles.find((p) => p.id === boundMain)
    if (found) return found
  }
  return (
    cfg.profiles.find((p) => p.id === cfg.active_profile_id)
    || cfg.profiles[0]
    || null
  )
})

const selectedPreset = computed<LLMPreset | null>(() => {
  if (!selectedProfile.value || !panelData.value) return null
  return panelData.value.presets.find((preset) => preset.key === selectedProfile.value?.preset_key) || null
})

const runtimeReady = computed(() => Boolean(panelData.value && !panelData.value.runtime.using_mock))

const activeModelHeadline = computed(() => {
  if (loading.value && !panelData.value) return '读取中…'
  const rtModel = panelData.value?.runtime?.model
  if (rtModel && !panelData.value?.runtime?.using_mock) return rtModel
  return activeMainProfile.value?.model || '尚未配置模型'
})

const authSourceBadgeText = computed(() => {
  const p = activeMainProfile.value
  if (!p || panelData.value?.runtime?.using_mock) return '待接入'
  if (p.auth_mode === 'local_gateway') return '本机订阅网关'
  if (p.auth_mode === 'oauth') return `OAuth · ${p.oauth_provider || '已授权'}`
  return `${p.protocol} · 密钥已配`
})

const activeRouteExplanation = computed(() => {
  const p = activeMainProfile.value
  if (!p) return '暂无可用模型档案'
  if (p.auth_mode === 'local_gateway') {
    return `${p.name} · 直连 ${p.base_url || '127.0.0.1'}`
  }
  if (p.auth_mode === 'oauth') {
    return `${p.name} · 0600 凭据仓安全托管`
  }
  return `${p.name} · ${p.base_url || '官方默认端点'}`
})

const isIndependentMode = computed(
  () => panelData.value?.config?.endpoint_mode === 'independent',
)

function resolveProfileForRole(role: LLMRoleKey): LLMProfile | null {
  const cfg = panelData.value?.config
  if (!cfg) return null
  const boundId = cfg.role_bindings?.[role]
  if (boundId) {
    const exact = cfg.profiles.find((p) => p.id === boundId)
    if (exact) return exact
  }
  if (role === 'cheap') {
    return (
      cfg.profiles.find((p) => p.name === ROLE_NAME_CHEAP || p.name.includes('经济'))
      || activeMainProfile.value
    )
  }
  if (role === 'kg') {
    return (
      cfg.profiles.find((p) => p.name === ROLE_NAME_KG || p.name.includes('知识图谱'))
      || activeMainProfile.value
    )
  }
  return activeMainProfile.value
}

const roleSummaryLine = computed(() => {
  if (!isIndependentMode.value) {
    return '全部写作、摘要与知识图谱环节共用同一主力档案'
  }
  const cheapModel = resolveProfileForRole('cheap')?.model || '回退主力'
  const kgModel = resolveProfileForRole('kg')?.model || '回退主力'
  return `摘要巡检 → ${cheapModel} · 图谱抽取 → ${kgModel}`
})

const profileSelectOptions = computed(() =>
  (panelData.value?.config.profiles || []).map((p) => ({
    label: `${p.name} (${p.model || '未设模型'})`,
    value: p.id,
  })),
)

const roleSlotRows = computed(() => {
  const mainP = resolveProfileForRole('main')
  const cheapP = resolveProfileForRole('cheap')
  const kgP = resolveProfileForRole('kg')
  return [
    {
      role: 'main' as LLMRoleKey,
      title: '主力执笔与总纲推演',
      badge: '高智商主力',
      scope: '章节正文、剧本分镜、世界观圣经、核心大纲与深度审校改写',
      boundProfileId: mainP?.id || '',
      profile: mainP,
    },
    {
      role: 'cheap' as LLMRoleKey,
      title: '章后摘要与常规巡检',
      badge: '省额度快模',
      scope: '多粒度摘要、张力打分、套话扫描、衔接检查与常规一致性快检',
      boundProfileId: cheapP?.id || '',
      profile: cheapP,
    },
    {
      role: 'kg' as LLMRoleKey,
      title: '知识图谱与记忆三元组',
      badge: '结构化提取',
      scope: '人物关系三元组、伏笔消费检测、道具事件与九维状态 JSON 提取',
      boundProfileId: kgP?.id || '',
      profile: kgP,
    },
  ]
})

const isSelectedSecretMasked = computed(
  () =>
    Boolean(
      selectedProfile.value
      && selectedProfile.value.auth_mode !== 'oauth'
      && selectedProfile.value.auth_mode !== 'local_gateway'
      && (selectedProfile.value.api_key === MASKED_SECRET_SENTINEL
        || (selectedProfile.value.has_secret && !selectedProfile.value.api_key)),
    ),
)

const apiKeyInputDisplayValue = computed(() => {
  if (!selectedProfile.value) return ''
  if (selectedProfile.value.api_key === MASKED_SECRET_SENTINEL) return ''
  return selectedProfile.value.api_key
})

function handleManualApiKeyInput(nextVal: string) {
  if (!selectedProfile.value) return
  if (!nextVal && selectedProfile.value.has_secret) {
    selectedProfile.value.api_key = MASKED_SECRET_SENTINEL
    return
  }
  selectedProfile.value.api_key = nextVal
}

const fetchedModelOptions = computed(() =>
  fetchedModels.value.map((m) => ({
    label: m.id,
    value: m.id,
  })),
)

function formatProfileAuthTag(profile: LLMProfile): string {
  if (profile.auth_mode === 'local_gateway') return '本机网关'
  if (profile.auth_mode === 'oauth') return `OAuth:${profile.oauth_provider || '已绑定'}`
  return profile.protocol
}

function getUiStateStorageKey(): string {
  return props.scrollStateKey ? `plotpilot.llm-panel.ui.${props.scrollStateKey}` : ''
}

function readUiState(): PanelUiState {
  const key = getUiStateStorageKey()
  if (!key) return {}
  return readStorageJson<PanelUiState>(key, {}, 'session')
}

function saveUiState() {
  const key = getUiStateStorageKey()
  if (!key) return
  const payload: PanelUiState = {
    selectedProfileId: selectedProfileId.value || undefined,
    editorTop: editorRef.value?.scrollTop || 0,
    sidebarTop: sidebarListRef.value?.scrollTop || 0,
    showManualSection: showManualSection.value,
  }
  writeStorageJson(key, payload, 'session')
}

function restoreUiState() {
  const state = readUiState()
  if (typeof state.showManualSection === 'boolean') {
    showManualSection.value = state.showManualSection
  }
  if (editorRef.value && typeof state.editorTop === 'number') {
    editorRef.value.scrollTop = state.editorTop
  }
  if (sidebarListRef.value && typeof state.sidebarTop === 'number') {
    sidebarListRef.value.scrollTop = state.sidebarTop
  }
}

function deepClone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T
}

function prettyJson(value: Record<string, unknown>): string {
  return JSON.stringify(value || {}, null, 2)
}

function newProfileId(): string {
  return globalThis.crypto?.randomUUID?.() || `profile-${Date.now()}`
}

function buildProfileFromPreset(preset?: LLMPreset): LLMProfile {
  return {
    id: newProfileId(),
    name: preset?.label || '新配置',
    preset_key: preset?.key || 'custom-openai-compatible',
    protocol: (preset?.protocol || 'openai') as LLMProtocol,
    base_url: preset?.default_base_url || '',
    api_key: '',
    model: preset?.default_model || '',
    temperature: 0.7,
    max_tokens: DEFAULT_MAX_OUTPUT_TOKENS,
    timeout_seconds: 300,
    extra_headers: {},
    extra_query: {},
    extra_body: {},
    notes: '',
    use_legacy_chat_completions: false,
    auth_mode: 'api_key',
    oauth_provider: '',
    oauth_session_id: '',
    has_secret: false,
  }
}

function defaultRuntimeSummary(): LLMRuntimeSummary {
  return {
    source: 'mock',
    active_profile_id: null,
    active_profile_name: null,
    protocol: null,
    model: null,
    base_url: null,
    using_mock: true,
    reason: '尚未加载或未返回运行时摘要',
  }
}

function normalizePanelData(raw: unknown): LLMControlPanelData {
  let root: Record<string, unknown> =
    raw && typeof raw === 'object' ? { ...(raw as Record<string, unknown>) } : {}

  const wrapped = root.data
  if (
    wrapped &&
    typeof wrapped === 'object' &&
    'config' in (wrapped as object) &&
    !('config' in root)
  ) {
    root = { ...(wrapped as Record<string, unknown>) }
  }

  const cfgIn = root.config
  const cfgObj =
    cfgIn && typeof cfgIn === 'object'
      ? (cfgIn as Record<string, unknown>)
      : { version: 1, active_profile_id: null, profiles: [] }

  let profiles: LLMProfile[] = Array.isArray(cfgObj.profiles)
    ? (cfgObj.profiles as LLMProfile[])
        .filter((p) => p && typeof p === 'object' && typeof p.id === 'string')
        .map((p) => {
          const mode = p.auth_mode ?? 'api_key'
          if (mode === 'api_key' && p.has_secret && (!p.api_key || !p.api_key.trim())) {
            return { ...p, api_key: MASKED_SECRET_SENTINEL }
          }
          return p
        })
    : []

  if (!profiles.length) {
    profiles = [buildProfileFromPreset(undefined)]
  }

  let activeId =
    typeof cfgObj.active_profile_id === 'string' ? cfgObj.active_profile_id : null
  if (!activeId || !profiles.some((p) => p.id === activeId)) {
    activeId = profiles[0]?.id ?? null
  }

  const rawBindings = cfgObj.role_bindings
  const roleBindings: Partial<Record<LLMRoleKey, string>> = {}
  if (rawBindings && typeof rawBindings === 'object') {
    for (const k of ['main', 'cheap', 'kg'] as const) {
      const v = (rawBindings as Record<string, unknown>)[k]
      if (typeof v === 'string' && v.trim()) {
        roleBindings[k] = v.trim()
      }
    }
  }

  const config: LLMControlConfig = {
    version: typeof cfgObj.version === 'number' ? cfgObj.version : 1,
    active_profile_id: activeId,
    endpoint_mode: cfgObj.endpoint_mode === 'independent' ? 'independent' : 'unified',
    role_bindings: roleBindings,
    profiles,
  }

  const presets: LLMPreset[] = Array.isArray(root.presets)
    ? (root.presets as LLMPreset[])
    : []

  const rtIn = root.runtime
  const runtime: LLMRuntimeSummary =
    rtIn && typeof rtIn === 'object'
      ? { ...defaultRuntimeSummary(), ...(rtIn as Partial<LLMRuntimeSummary>) }
      : defaultRuntimeSummary()

  return { config, presets, runtime }
}

function applyNormalizedPanel(raw: unknown, emitEvent = true) {
  const normalized = normalizePanelData(raw)
  profileJsonDrafts.clear()
  panelData.value = deepClone(normalized)
  const uiState = readUiState()
  const preferredId = selectedProfileId.value || uiState.selectedProfileId
  selectedProfileId.value =
    (preferredId && normalized.config.profiles.some((p) => p.id === preferredId)
      ? preferredId
      : '')
    || normalized.config.active_profile_id
    || normalized.config.profiles[0]?.id
    || ''
  syncJsonEditors()
  if (emitEvent) {
    emit('panel-updated', deepClone(normalized))
  }
}

function uniqueProfileName(baseName: string): string {
  const normalized = baseName.trim() || '新配置'
  const names = new Set((panelData.value?.config?.profiles || []).map((profile) => profile.name))
  if (!names.has(normalized)) return normalized
  let index = 2
  while (names.has(`${normalized} ${index}`)) {
    index += 1
  }
  return `${normalized} ${index}`
}

function recordSelectedJsonDraft(patch: Partial<Omit<ProfileJsonDraft, 'dirty'>>) {
  const prof = selectedProfile.value
  if (!prof) return
  const prev = profileJsonDrafts.get(prof.id) ?? {
    headers: extraHeadersText.value,
    query: extraQueryText.value,
    body: extraBodyText.value,
    dirty: false,
  }
  profileJsonDrafts.set(prof.id, {
    headers: patch.headers ?? prev.headers,
    query: patch.query ?? prev.query,
    body: patch.body ?? prev.body,
    dirty: true,
  })
}

function handleExtraHeadersInput(val: string) {
  extraHeadersText.value = val
  recordSelectedJsonDraft({ headers: val })
}

function handleExtraQueryInput(val: string) {
  extraQueryText.value = val
  recordSelectedJsonDraft({ query: val })
}

function handleExtraBodyInput(val: string) {
  extraBodyText.value = val
  recordSelectedJsonDraft({ body: val })
}

function syncJsonEditors() {
  const prof = selectedProfile.value
  if (!prof) {
    extraHeadersText.value = '{}'
    extraQueryText.value = '{}'
    extraBodyText.value = '{}'
    return
  }
  const draft = profileJsonDrafts.get(prof.id)
  if (draft?.dirty) {
    extraHeadersText.value = draft.headers
    extraQueryText.value = draft.query
    extraBodyText.value = draft.body
    return
  }
  extraHeadersText.value = prettyJson((prof.extra_headers || {}) as Record<string, unknown>)
  extraQueryText.value = prettyJson((prof.extra_query || {}) as Record<string, unknown>)
  extraBodyText.value = prettyJson((prof.extra_body || {}) as Record<string, unknown>)
}

function parseJsonObject(label: string, text: string): Record<string, unknown> {
  if (!text.trim()) return {}
  try {
    const parsed = JSON.parse(text)
    if (!parsed || Array.isArray(parsed) || typeof parsed !== 'object') {
      throw new Error(`${label} 必须是 JSON 对象`)
    }
    return parsed as Record<string, unknown>
  } catch (error) {
    const reason = error instanceof Error ? error.message : 'JSON 解析失败'
    throw new Error(`${label} 格式无效：${reason}`)
  }
}

function commitProfileJsonDraft(profile: LLMProfile) {
  const draft = profileJsonDrafts.get(profile.id)
  if (!draft?.dirty) return
  const prefix = profile.name ? `档案「${profile.name}」的 ` : ''
  const headersObj = parseJsonObject(`${prefix}Extra Headers`, draft.headers)
  const queryObj = parseJsonObject(`${prefix}Extra Query`, draft.query)
  const bodyObj = parseJsonObject(`${prefix}Extra Body`, draft.body)
  profile.extra_headers = Object.fromEntries(
    Object.entries(headersObj).map(([key, value]) => [key, String(value)]),
  )
  profile.extra_query = queryObj
  profile.extra_body = bodyObj
  draft.dirty = false
}

function commitAllProfileJsonDrafts() {
  if (!panelData.value) return
  const staged = new Map<
    string,
    {
      headers: Record<string, string>
      query: Record<string, unknown>
      body: Record<string, unknown>
    }
  >()
  for (const profile of panelData.value.config.profiles) {
    const draft = profileJsonDrafts.get(profile.id)
    if (!draft?.dirty) continue
    const prefix = profile.name ? `档案「${profile.name}」的 ` : ''
    const headersObj = parseJsonObject(`${prefix}Extra Headers`, draft.headers)
    const queryObj = parseJsonObject(`${prefix}Extra Query`, draft.query)
    const bodyObj = parseJsonObject(`${prefix}Extra Body`, draft.body)
    staged.set(profile.id, {
      headers: Object.fromEntries(
        Object.entries(headersObj).map(([key, value]) => [key, String(value)]),
      ),
      query: queryObj,
      body: bodyObj,
    })
  }
  for (const profile of panelData.value.config.profiles) {
    const applied = staged.get(profile.id)
    if (!applied) continue
    profile.extra_headers = applied.headers
    profile.extra_query = applied.query
    profile.extra_body = applied.body
    const draft = profileJsonDrafts.get(profile.id)
    if (draft) {
      draft.dirty = false
    }
  }
}

function resetPanelLoadingOwnership() {
  activePanelLoadId += 1
  if (!isUnmounted && loading.value) {
    loading.value = false
  }
}

function invalidateCompletionRefresh() {
  authRefreshEpoch += 1
  resetPanelLoadingOwnership()
  if (completionRefreshAbort) {
    completionRefreshAbort.abort()
    completionRefreshAbort = null
  }
}

function supersedePendingAuthAndRefresh(clearDeviceDisplay = true) {
  invalidateDevicePollCycle(clearDeviceDisplay)
  invalidateCompletionRefresh()
}

function canApplyRefresh(opts?: RefreshGuardOptions): boolean {
  if (isUnmounted) return false
  if (opts?.signal?.aborted) return false
  if ((opts?.requireActive ?? false) && !props.active) return false
  if (opts?.epoch !== undefined && opts.epoch !== authRefreshEpoch) return false
  return true
}

async function loadPanel(opts?: RefreshGuardOptions): Promise<boolean> {
  const targetEpoch = opts?.epoch ?? authRefreshEpoch
  const guard: RefreshGuardOptions = { ...opts, epoch: targetEpoch }
  if (!canApplyRefresh(guard)) return false
  const loadId = ++activePanelLoadId
  loading.value = true
  try {
    const data = await llmControlApi.getPanel(opts?.signal)
    if (!canApplyRefresh(guard)) return false
    applyNormalizedPanel(data, true)
    await nextTick()
    if (canApplyRefresh(guard)) {
      restoreUiState()
    }
    return true
  } catch (error: unknown) {
    if (canApplyRefresh(guard)) {
      message.error(formatApiError(error, '加载 LLM 配置失败'))
    }
    return false
  } finally {
    if (!isUnmounted && loadId === activePanelLoadId) {
      loading.value = false
    }
  }
}

async function loadOAuthStatus(opts?: RefreshGuardOptions): Promise<boolean> {
  const targetEpoch = opts?.epoch ?? authRefreshEpoch
  const guard: RefreshGuardOptions = { ...opts, epoch: targetEpoch }
  if (!canApplyRefresh(guard)) return false
  try {
    const res = await llmControlApi.getOAuthStatus(opts?.signal)
    if (!canApplyRefresh(guard)) return false
    if (res && Array.isArray(res.providers)) {
      oauthProviders.value = res.providers
      return true
    }
    return false
  } catch {
    // OAuth 状态辅助读取，静默降级
    return false
  }
}

async function handleProbeGateways(silent = false) {
  probingGateways.value = true
  try {
    const res = await llmControlApi.probeLocalGateways(customGatewayUrl.value.trim())
    discoveredGateways.value = Array.isArray(res.gateways) ? res.gateways : []
    cliTools.value = Array.isArray(res.cli_tools) ? res.cli_tools : []
    gatewayProbedOnce.value = true
    if (!silent) {
      const count = reachableGateways.value.length
      if (count > 0) {
        message.success(`检出 ${count} 个在线本机订阅网关`)
      } else {
        message.info('未在默认回环端口检出在线网关')
      }
    }
  } catch (error: unknown) {
    gatewayProbedOnce.value = true
    if (!silent) {
      message.error(formatApiError(error, '探测本机网关失败'))
    }
  } finally {
    probingGateways.value = false
  }
}

async function reloadAll() {
  supersedePendingAuthAndRefresh(false)
  const refreshEpoch = authRefreshEpoch
  const guard: RefreshGuardOptions = {
    epoch: refreshEpoch,
    requireActive: props.active,
  }
  await Promise.all([loadPanel(guard), loadOAuthStatus(guard), handleProbeGateways(true)])
}

async function handleConnectGateway(gw: LocalGatewayItem, enableGolden: boolean) {
  const mainModel = gw.recommended_roles.main || gw.models[0] || ''
  if (!mainModel) {
    message.warning('该网关尚未返回可用模型列表')
    return
  }
  supersedePendingAuthAndRefresh(true)
  const opEpoch = authRefreshEpoch
  connectingGatewayUrl.value = gw.base_url
  try {
    const updated = await llmControlApi.connectLocalGateway({
      base_url: gw.base_url,
      name: gw.name,
      main_model: mainModel,
      cheap_model: gw.recommended_roles.cheap || mainModel,
      kg_model: gw.recommended_roles.kg || gw.recommended_roles.cheap || mainModel,
      enable_golden_roles: enableGolden,
      use_legacy_chat_completions: true,
    })
    if (!canApplyRefresh({ epoch: opEpoch, requireActive: true })) return
    applyNormalizedPanel(updated, true)
    message.success(
      enableGolden
        ? `已接入 ${gw.name} 并配平省额度三角色编组`
        : `已接入 ${gw.name} 主力模型`,
    )
  } catch (error: unknown) {
    if (canApplyRefresh({ epoch: opEpoch, requireActive: true })) {
      message.error(formatApiError(error, '接入本机网关失败'))
    }
  } finally {
    if (connectingGatewayUrl.value === gw.base_url) {
      connectingGatewayUrl.value = ''
    }
  }
}

function openExternalUrl(url: string) {
  window.open(url, '_blank', 'noopener,noreferrer')
}

async function handleStartOpenRouter() {
  supersedePendingAuthAndRefresh(true)
  const opEpoch = authRefreshEpoch
  oauthBusy.value = 'openrouter'
  try {
    const res = await llmControlApi.startOpenRouterOAuth()
    if (!canApplyRefresh({ epoch: opEpoch, requireActive: true })) return
    window.open(res.authorize_url, 'plotpilot-oauth-openrouter', 'width=620,height=740')
    message.info('已在浏览器打开 OpenRouter 授权页，授权完成后将自动同步')
  } catch (error: unknown) {
    if (canApplyRefresh({ epoch: opEpoch, requireActive: true })) {
      message.error(formatApiError(error, '发起 OpenRouter PKCE 授权失败'))
    }
  } finally {
    if (oauthBusy.value === 'openrouter') {
      oauthBusy.value = ''
    }
  }
}

function clearDevicePollTimer() {
  if (devicePollTimer !== null) {
    clearTimeout(devicePollTimer)
    devicePollTimer = null
  }
}

function abortDevicePollRequest() {
  if (devicePollAbort) {
    devicePollAbort.abort()
    devicePollAbort = null
  }
}

function invalidateDevicePollCycle(clearDisplay = false) {
  devicePollGeneration += 1
  deviceFlowOriginEpoch = -1
  clearDevicePollTimer()
  abortDevicePollRequest()
  if (clearDisplay) {
    deviceFlowState.value = null
    deviceFlowStatusText.value = ''
  }
}

function isDeviceFlowGenerationActive(
  gen: number,
  originEpoch: number,
  flowId?: string,
): boolean {
  if (
    isUnmounted
    || !props.active
    || gen !== devicePollGeneration
    || originEpoch !== authRefreshEpoch
    || originEpoch !== deviceFlowOriginEpoch
  ) {
    return false
  }
  if (flowId !== undefined && deviceFlowState.value?.flow_id !== flowId) {
    return false
  }
  return true
}

function scheduleDevicePoll(
  flowId: string,
  intervalSec: number,
  gen: number,
  originEpoch: number,
) {
  if (!isDeviceFlowGenerationActive(gen, originEpoch, flowId)) return
  clearDevicePollTimer()
  const waitMs = Math.max(2, intervalSec) * 1000
  devicePollTimer = setTimeout(async () => {
    devicePollTimer = null
    if (!isDeviceFlowGenerationActive(gen, originEpoch, flowId)) return
    abortDevicePollRequest()
    const controller = new AbortController()
    devicePollAbort = controller
    try {
      const poll = await llmControlApi.pollGitHubDeviceOAuth(flowId, controller.signal)
      if (!isDeviceFlowGenerationActive(gen, originEpoch, flowId)) return
      if (poll.status === 'completed') {
        invalidateDevicePollCycle(true)
        invalidateCompletionRefresh()
        const completionEpoch = authRefreshEpoch
        const refreshController = new AbortController()
        completionRefreshAbort = refreshController
        const refreshOpts: RefreshGuardOptions = {
          epoch: completionEpoch,
          signal: refreshController.signal,
          requireActive: true,
        }
        try {
          const [statusApplied, panelApplied] = await Promise.all([
            loadOAuthStatus(refreshOpts),
            loadPanel(refreshOpts),
          ])
          if (canApplyRefresh(refreshOpts) && statusApplied && panelApplied) {
            message.success('GitHub Models 设备授权已完成')
          }
        } finally {
          if (completionRefreshAbort === refreshController) {
            completionRefreshAbort = null
          }
        }
        return
      }
      if (poll.status === 'expired' || poll.status === 'error') {
        deviceFlowStatusText.value = poll.message || '设备码已过期，请重新发起'
        invalidateDevicePollCycle(false)
        return
      }
      deviceFlowStatusText.value = '等待浏览器确认授权中…'
      scheduleDevicePoll(flowId, poll.interval || intervalSec, gen, originEpoch)
    } catch {
      if (controller.signal.aborted || !isDeviceFlowGenerationActive(gen, originEpoch, flowId)) {
        return
      }
      deviceFlowStatusText.value = '轮询暂停，请稍后重试'
      invalidateDevicePollCycle(false)
    } finally {
      if (devicePollAbort === controller) {
        devicePollAbort = null
      }
    }
  }, waitMs)
}

async function handleStartGitHubDevice() {
  const status = oauthMap.value.github_models
  if (!status?.configured && !githubClientIdInput.value.trim()) {
    showGithubClientInput.value = true
    message.info('请先填入 GitHub OAuth App Client ID（或优先使用左侧本机网关免配置直连）')
    return
  }
  supersedePendingAuthAndRefresh(true)
  const gen = devicePollGeneration
  const originEpoch = authRefreshEpoch
  deviceFlowOriginEpoch = originEpoch
  deviceStartGeneration = gen
  const controller = new AbortController()
  devicePollAbort = controller
  oauthBusy.value = 'github_models'
  try {
    const res = await llmControlApi.startGitHubDeviceOAuth(
      githubClientIdInput.value.trim(),
      controller.signal,
    )
    if (
      !canApplyRefresh({ epoch: originEpoch, requireActive: true })
      || gen !== devicePollGeneration
      || originEpoch !== deviceFlowOriginEpoch
    ) {
      return
    }
    deviceFlowState.value = res
    deviceFlowStatusText.value = '请在打开的 GitHub 页面输入上方验证码…'
    openExternalUrl(res.verification_uri)
    scheduleDevicePoll(res.flow_id, res.interval || 5, gen, originEpoch)
  } catch (error: unknown) {
    if (
      controller.signal.aborted
      || !canApplyRefresh({ epoch: originEpoch, requireActive: true })
      || gen !== devicePollGeneration
      || originEpoch !== deviceFlowOriginEpoch
    ) {
      return
    }
    showGithubClientInput.value = true
    message.error(formatApiError(error, '发起 GitHub 设备码授权失败'))
  } finally {
    if (devicePollAbort === controller) {
      devicePollAbort = null
    }
    if (deviceStartGeneration === gen && oauthBusy.value === 'github_models') {
      oauthBusy.value = ''
    }
  }
}

async function handleStartGoogleOAuth() {
  const status = oauthMap.value.google_gemini
  if (!status?.configured && !googleClientIdInput.value.trim()) {
    showGoogleClientInput.value = true
    message.info('请先填入 Google OAuth Client ID（或优先使用左侧本机网关免配置直连）')
    return
  }
  supersedePendingAuthAndRefresh(true)
  const opEpoch = authRefreshEpoch
  oauthBusy.value = 'google_gemini'
  try {
    const res = await llmControlApi.startGoogleOAuth(
      googleClientIdInput.value.trim(),
      googleClientSecretInput.value.trim(),
    )
    if (!canApplyRefresh({ epoch: opEpoch, requireActive: true })) return
    window.open(res.authorize_url, 'plotpilot-oauth-google', 'width=620,height=760')
    message.info('已在浏览器打开 Google Gemini 授权页，完成后自动同步')
  } catch (error: unknown) {
    if (canApplyRefresh({ epoch: opEpoch, requireActive: true })) {
      showGoogleClientInput.value = true
      message.error(formatApiError(error, '发起 Google Gemini OAuth 失败'))
    }
  } finally {
    if (oauthBusy.value === 'google_gemini') {
      oauthBusy.value = ''
    }
  }
}

async function handleDisconnectOAuth(provider: LLMOAuthProviderId) {
  supersedePendingAuthAndRefresh(true)
  const disconnectEpoch = authRefreshEpoch
  const busyTag = `${provider}-disconnect`
  oauthBusy.value = busyTag
  try {
    const res = await llmControlApi.disconnectOAuth(provider)
    if (!canApplyRefresh({ epoch: disconnectEpoch, requireActive: true })) return
    if (res && Array.isArray(res.providers)) {
      oauthProviders.value = res.providers
    }
    const panelApplied = await loadPanel({ epoch: disconnectEpoch, requireActive: true })
    if (panelApplied && canApplyRefresh({ epoch: disconnectEpoch, requireActive: true })) {
      message.success('已断开 OAuth 连接并清理本机后端令牌')
    }
  } catch (error: unknown) {
    if (canApplyRefresh({ epoch: disconnectEpoch, requireActive: true })) {
      message.error(formatApiError(error, '断开 OAuth 失败'))
    }
  } finally {
    if (oauthBusy.value === busyTag) {
      oauthBusy.value = ''
    }
  }
}

function resolveExistingRoleTarget(
  cfg: LLMControlConfig,
  role: 'cheap' | 'kg',
  roleName: string,
): LLMProfile | undefined {
  const boundId = cfg.role_bindings?.[role]
  if (boundId) {
    const byBoundId = cfg.profiles.find((p) => p.id === boundId)
    if (byBoundId) return byBoundId
  }
  return cfg.profiles.find((p) => p.name === roleName)
}

function stageAndCommitProfileJsonDrafts(profilesToCommit: LLMProfile[]): void {
  const seenIds = new Set<string>()
  const staged = new Map<
    string,
    {
      profile: LLMProfile
      headers: Record<string, string>
      query: Record<string, unknown>
      body: Record<string, unknown>
    }
  >()
  for (const profile of profilesToCommit) {
    if (!profile || seenIds.has(profile.id)) continue
    seenIds.add(profile.id)
    const draft = profileJsonDrafts.get(profile.id)
    if (!draft?.dirty) continue
    const prefix = profile.name ? `档案「${profile.name}」的 ` : ''
    const headersObj = parseJsonObject(`${prefix}Extra Headers`, draft.headers)
    const queryObj = parseJsonObject(`${prefix}Extra Query`, draft.query)
    const bodyObj = parseJsonObject(`${prefix}Extra Body`, draft.body)
    staged.set(profile.id, {
      profile,
      headers: Object.fromEntries(
        Object.entries(headersObj).map(([key, value]) => [key, String(value)]),
      ),
      query: queryObj,
      body: bodyObj,
    })
  }
  for (const [profileId, applied] of staged.entries()) {
    applied.profile.extra_headers = applied.headers
    applied.profile.extra_query = applied.query
    applied.profile.extra_body = applied.body
    const draft = profileJsonDrafts.get(profileId)
    if (draft) {
      draft.dirty = false
    }
  }
}

function ensureSecondaryRoleProfilesExist(): boolean {
  if (!panelData.value) return false
  const cfg = panelData.value.config
  const base = activeMainProfile.value || cfg.profiles[0]
  if (!base) return true

  const resolvedCheap = resolveExistingRoleTarget(cfg, 'cheap', ROLE_NAME_CHEAP)
  const resolvedKg = resolveExistingRoleTarget(cfg, 'kg', ROLE_NAME_KG)
  const candidatesToValidate: LLMProfile[] = [base]
  if (resolvedCheap) candidatesToValidate.push(resolvedCheap)
  if (resolvedKg) candidatesToValidate.push(resolvedKg)

  try {
    stageAndCommitProfileJsonDrafts(candidatesToValidate)
  } catch (error) {
    message.error(error instanceof Error ? error.message : '请求扩展 JSON 格式错误')
    return false
  }

  if (!cfg.role_bindings) cfg.role_bindings = {}
  cfg.role_bindings.main = base.id

  const ensureOne = (
    role: 'cheap' | 'kg',
    roleName: string,
    existingTarget: LLMProfile | undefined,
  ) => {
    if (existingTarget) {
      cfg.role_bindings![role] = existingTarget.id
      return
    }
    const cloned: LLMProfile = {
      ...deepClone(base),
      id: `${role}-${Date.now()}`,
      name: roleName,
      temperature: role === 'kg' ? 0.3 : 0.5,
    }
    cfg.profiles.push(cloned)
    cfg.role_bindings![role] = cloned.id
  }

  ensureOne('cheap', ROLE_NAME_CHEAP, resolvedCheap)
  ensureOne('kg', ROLE_NAME_KG, resolvedKg)
  return true
}

function setEndpointMode(mode: 'unified' | 'independent') {
  if (!panelData.value) return
  if (mode === 'independent') {
    if (!ensureSecondaryRoleProfilesExist()) {
      return
    }
  }
  panelData.value.config.endpoint_mode = mode
}

function handleBindRoleProfile(role: LLMRoleKey, profileId: string) {
  if (!panelData.value) return
  if (!panelData.value.config.role_bindings) {
    panelData.value.config.role_bindings = {}
  }
  panelData.value.config.role_bindings[role] = profileId
  if (role === 'main') {
    panelData.value.config.active_profile_id = profileId
  }
}

async function handleAutoComposeGoldenRoles() {
  const source = activeMainProfile.value
  if (!source) return
  try {
    commitProfileJsonDraft(source)
  } catch (error) {
    message.error(error instanceof Error ? error.message : '请求扩展 JSON 格式错误')
    return
  }
  supersedePendingAuthAndRefresh(true)
  const opEpoch = authRefreshEpoch
  applyingGolden.value = true
  try {
    let modelIds: string[] = []
    if (source.auth_mode === 'local_gateway') {
      const matchedGw = reachableGateways.value.find((g) => g.base_url === source.base_url)
      if (matchedGw && matchedGw.models.length) {
        modelIds = matchedGw.models
      }
    }
    if (!modelIds.length) {
      try {
        const listRes = await llmControlApi.fetchModels({
          protocol: source.protocol,
          base_url: source.base_url,
          api_key: source.api_key,
          profile_id: source.id,
        })
        if (listRes.success && listRes.items.length) {
          modelIds = listRes.items.map((i) => i.id)
        }
      } catch {
        // 拉取列表不支持时退回当前模型推荐
      }
    }
    if (!modelIds.length && source.model) {
      modelIds = [source.model]
    }
    const rec = await llmControlApi.recommendRoleModels(modelIds, source.id)
    if (!canApplyRefresh({ epoch: opEpoch, requireActive: true })) return
    const mainM = rec.main || source.model
    const cheapM = rec.cheap || mainM
    const kgM = rec.kg || cheapM
    const updated = await llmControlApi.applyGoldenRoles({
      source_profile_id: source.id,
      main_model: mainM,
      cheap_model: cheapM,
      kg_model: kgM,
    })
    if (!canApplyRefresh({ epoch: opEpoch, requireActive: true })) return
    applyNormalizedPanel(updated, true)
    message.success(`已启用省额度编组：主力 ${mainM} · 摘要 ${cheapM} · 图谱 ${kgM}`)
  } catch (error: unknown) {
    if (canApplyRefresh({ epoch: opEpoch, requireActive: true })) {
      message.error(formatApiError(error, '智能配平省额度编组失败'))
    }
  } finally {
    applyingGolden.value = false
  }
}

async function handleFetchModels() {
  if (!selectedProfile.value) return
  fetchingModels.value = true
  fetchedModels.value = []
  try {
    const result = await llmControlApi.fetchModels({
      protocol: selectedProfile.value.protocol,
      base_url: selectedProfile.value.base_url,
      api_key: selectedProfile.value.api_key,
      profile_id: selectedProfile.value.id,
    })
    if (result.success && result.items.length > 0) {
      fetchedModels.value = result.items
      message.success(`成功拉取 ${result.count} 个模型`)
    } else {
      message.warning('未获取到可用模型列表')
    }
  } catch (error: unknown) {
    message.error(`模型列表拉取失败：${formatApiError(error, '拉取失败')}`)
  } finally {
    fetchingModels.value = false
  }
}

function selectProfile(profileId: string) {
  selectedProfileId.value = profileId
  syncJsonEditors()
  saveUiState()
}

function handlePresetChange(presetKey: string) {
  if (!selectedProfile.value || !panelData.value) return
  const preset = panelData.value.presets.find((item) => item.key === presetKey)
  if (!preset) return
  selectedProfile.value.protocol = preset.protocol
  if (!selectedProfile.value.base_url.trim()) {
    selectedProfile.value.base_url = preset.default_base_url
  }
  if (!selectedProfile.value.model.trim()) {
    selectedProfile.value.model = preset.default_model
  }
}

function applySelectedPresetDefaults() {
  if (!selectedProfile.value || !selectedPreset.value) return
  selectedProfile.value.protocol = selectedPreset.value.protocol
  selectedProfile.value.base_url = selectedPreset.value.default_base_url
  selectedProfile.value.model = selectedPreset.value.default_model
}

function createProfile() {
  if (!panelData.value) return
  const preset = panelData.value.presets[0]
  const next = buildProfileFromPreset(preset)
  next.name = uniqueProfileName(preset?.label || '新配置')
  panelData.value.config.profiles.push(next)
  selectedProfileId.value = next.id
  syncJsonEditors()
}

function quickImportPreset(preset: LLMPreset) {
  if (!panelData.value) return
  const next = buildProfileFromPreset(preset)
  next.name = uniqueProfileName(preset.label)
  panelData.value.config.profiles.push(next)
  selectedProfileId.value = next.id
  syncJsonEditors()
  message.info(`已导入「${next.name}」预设，填入 API Key 后点击保存即可生效`)
}

function duplicateProfile() {
  if (!panelData.value || !selectedProfile.value) return
  try {
    commitProfileJsonDraft(selectedProfile.value)
  } catch (error) {
    message.error(error instanceof Error ? error.message : '请求扩展 JSON 格式错误')
    return
  }
  const copy = deepClone(selectedProfile.value)
  copy.id = newProfileId()
  copy.name = `${selectedProfile.value.name} 副本`
  if (copy.api_key === MASKED_SECRET_SENTINEL) {
    copy.api_key = ''
    copy.has_secret = false
  }
  panelData.value.config.profiles.push(copy)
  selectedProfileId.value = copy.id
  syncJsonEditors()
}

function deleteSelected() {
  if (!panelData.value || !selectedProfile.value) return
  if (panelData.value.config.profiles.length <= 1) return

  const deletingId = selectedProfile.value.id
  profileJsonDrafts.delete(deletingId)
  panelData.value.config.profiles = panelData.value.config.profiles.filter(
    (profile) => profile.id !== deletingId,
  )
  if (panelData.value.config.active_profile_id === deletingId) {
    panelData.value.config.active_profile_id = panelData.value.config.profiles[0]?.id || null
  }
  if (panelData.value.config.role_bindings) {
    for (const k of ['main', 'cheap', 'kg'] as const) {
      if (panelData.value.config.role_bindings[k] === deletingId) {
        delete panelData.value.config.role_bindings[k]
      }
    }
  }
  selectedProfileId.value = panelData.value.config.profiles[0]?.id || ''
  syncJsonEditors()
}

async function saveAll() {
  if (!panelData.value) return
  try {
    commitAllProfileJsonDrafts()
  } catch (error) {
    message.error(error instanceof Error ? error.message : '请求扩展 JSON 格式错误')
    return
  }

  supersedePendingAuthAndRefresh(true)
  const opEpoch = authRefreshEpoch
  saving.value = true
  try {
    const response = await llmControlApi.saveConfig(panelData.value.config)
    if (!canApplyRefresh({ epoch: opEpoch, requireActive: true })) return
    applyNormalizedPanel(response, true)
    await nextTick()
    if (canApplyRefresh({ epoch: opEpoch, requireActive: true })) {
      restoreUiState()
      saveUiState()
      message.success('AI 路由与模型配置已保存')
    }
  } catch (error) {
    if (canApplyRefresh({ epoch: opEpoch, requireActive: true })) {
      message.error(`保存失败：${formatApiError(error, '保存失败')}`)
    }
  } finally {
    saving.value = false
  }
}

async function activateSelected() {
  if (!panelData.value || !selectedProfile.value) return
  panelData.value.config.active_profile_id = selectedProfile.value.id
  if (panelData.value.config.role_bindings) {
    panelData.value.config.role_bindings.main = selectedProfile.value.id
  }
  await saveAll()
}

async function testProfileTarget(target: LLMProfile | null) {
  if (!target) return
  try {
    commitProfileJsonDraft(target)
  } catch (error) {
    message.error(error instanceof Error ? error.message : '请求扩展 JSON 格式错误')
    return
  }
  testing.value = true
  try {
    const result = await llmControlApi.testProfile(target)
    if (result.ok) {
      const preview = result.preview ? ` · ${result.preview}` : ''
      message.success(`连接畅通（${result.latency_ms}ms）${preview}`)
    } else {
      message.error(result.error || '连接测试未通过')
    }
  } catch (error) {
    message.error(`测试失败：${formatApiError(error, '连接失败')}`)
  } finally {
    testing.value = false
  }
}

async function testSelected() {
  if (!selectedProfile.value) return
  await testProfileTarget(selectedProfile.value)
}

function handleOAuthWindowMessage(ev: MessageEvent) {
  if (ev.origin !== window.location.origin) return
  if (isUnmounted || !props.active) return
  const payload = ev.data
  if (!payload || typeof payload !== 'object') return
  if ((payload as Record<string, unknown>).type !== 'plotpilot-oauth-complete') return
  supersedePendingAuthAndRefresh(true)
  const completionEpoch = authRefreshEpoch
  const refreshController = new AbortController()
  completionRefreshAbort = refreshController
  const refreshOpts: RefreshGuardOptions = {
    epoch: completionEpoch,
    signal: refreshController.signal,
    requireActive: true,
  }
  void (async () => {
    try {
      const [statusApplied, panelApplied] = await Promise.all([
        loadOAuthStatus(refreshOpts),
        loadPanel(refreshOpts),
        handleProbeGateways(true),
      ])
      if (
        (payload as Record<string, unknown>).ok
        && canApplyRefresh(refreshOpts)
        && statusApplied
        && panelApplied
      ) {
        message.success('OAuth 授权成功，模型凭据已安全写入本机')
      }
    } finally {
      if (completionRefreshAbort === refreshController) {
        completionRefreshAbort = null
      }
    }
  })()
}

watch(
  () => props.active,
  (isActive) => {
    if (!isActive) {
      supersedePendingAuthAndRefresh(false)
    }
  },
)

watch(selectedProfileId, () => {
  fetchedModels.value = []
  syncJsonEditors()
  saveUiState()
})

watch(showManualSection, () => {
  saveUiState()
})

onMounted(() => {
  isUnmounted = false
  window.addEventListener('message', handleOAuthWindowMessage)
  void reloadAll()
})

onBeforeUnmount(() => {
  isUnmounted = true
  window.removeEventListener('message', handleOAuthWindowMessage)
  invalidateDevicePollCycle(false)
  invalidateCompletionRefresh()
  saveUiState()
})
</script>

<style scoped>
.llm-panel {
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: var(--app-page-bg, #f4f4f2);
  color: var(--app-text-primary, #161615);
}

/* ── 顶部双格汇总台账 ── */
.llm-top-ledger {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 14px 18px;
  background: var(--app-surface, #ffffff);
  border-bottom: 1px solid var(--app-border, #e3e3de);
  flex-shrink: 0;
}

.llm-ledger-cells {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 20px;
  flex: 1;
  min-width: 0;
}

.llm-ledger-cell {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}

.llm-ledger-caption {
  font-size: 12px;
  color: var(--app-text-muted, #66645e);
}

.llm-ledger-value-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.llm-ledger-value {
  font-size: 16px;
  font-weight: 600;
  color: var(--app-text-primary, #161615);
  font-variant-numeric: tabular-nums;
}

.llm-ledger-sub {
  font-size: 13px;
  color: var(--app-text-secondary, #454440);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.llm-ledger-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

/* ── 低饱和宣纸语义徽标（深墨文字 + 淡色底，对比度 >= 4.5:1） ── */
.llm-status-pill {
  display: inline-flex;
  align-items: center;
  height: 22px;
  padding: 0 8px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 500;
  white-space: nowrap;
}

.llm-status-pill.is-ready {
  background: var(--color-success-light, #dcfae5);
  color: #04250e;
}

.llm-status-pill.is-pending {
  background: var(--color-warning-light, #fff6e0);
  color: var(--color-gold, #7a5510);
}

.llm-status-pill.is-neutral {
  background: var(--app-surface-subtle, #ecece9);
  color: var(--app-text-secondary, #454440);
}

.llm-inline-notice {
  margin: 12px 18px 0;
  padding: 10px 14px;
  border-radius: 6px;
  border: 1px solid var(--color-gold-border, rgba(122, 85, 16, 0.24));
  background: var(--color-warning-light, #fff6e0);
  color: var(--color-gold, #7a5510);
  font-size: 14px;
  line-height: 1.5;
  flex-shrink: 0;
}

.llm-inline-notice-title {
  font-weight: 600;
}

/* ── 主滚动区 ── */
.llm-scroll-body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 16px 18px 24px;
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.llm-section {
  background: var(--app-surface, #ffffff);
  border: 1px solid var(--app-border, #e3e3de);
  border-radius: 8px;
  padding: 18px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.llm-section-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
}

.llm-section-title {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--app-text-primary, #161615);
}

.llm-section-desc {
  margin: 4px 0 0;
  max-width: 66ch;
  font-size: 14px;
  line-height: 1.55;
  color: var(--app-text-secondary, #454440);
}

/* ── 免密钥双栏卡片 ── */
.llm-connect-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

.llm-surface-card {
  background: var(--app-page-bg, #f4f4f2);
  border: 1px solid var(--app-border, #e3e3de);
  border-radius: 8px;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.llm-card-top {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.llm-card-heading {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: var(--app-text-primary, #161615);
}

.llm-card-copy {
  margin: 4px 0 0;
  font-size: 14px;
  line-height: 1.5;
  color: var(--app-text-secondary, #454440);
}

.llm-gateway-custom-row {
  display: flex;
  gap: 8px;
}

.llm-gateway-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.llm-gateway-item {
  background: var(--app-surface, #ffffff);
  border: 1px solid var(--app-border, #e3e3de);
  border-radius: 6px;
  padding: 12px 14px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.llm-gateway-item-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  flex-wrap: wrap;
}

.llm-gateway-title-group {
  display: flex;
  align-items: center;
  gap: 8px;
}

.llm-gateway-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--app-text-primary, #161615);
}

.llm-gateway-url {
  font-size: 12px;
  color: var(--app-text-muted, #66645e);
}

.llm-gateway-recommend {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  font-size: 13px;
  color: var(--app-text-secondary, #454440);
}

.llm-gateway-btn-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 2px;
}

.llm-empty-slot {
  border: 1px dashed var(--app-border-strong, #ccccc5);
  border-radius: 6px;
  padding: 12px 14px;
  font-size: 14px;
  color: var(--app-text-muted, #66645e);
  line-height: 1.5;
}

.llm-cli-strip {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
  padding-top: 4px;
}

.llm-cli-label {
  font-size: 12px;
  color: var(--app-text-muted, #66645e);
}

.llm-cli-chip {
  font-size: 12px;
  padding: 2px 8px;
  border-radius: 4px;
  background: var(--app-surface, #ffffff);
  border: 1px solid var(--app-border, #e3e3de);
  color: var(--app-text-muted, #66645e);
}

.llm-cli-chip.is-detected {
  color: var(--color-brand, #1f5e5b);
  border-color: var(--color-brand-border, rgba(31, 94, 91, 0.22));
}

/* ── OAuth 行列表 ── */
.llm-oauth-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.llm-oauth-row {
  background: var(--app-surface, #ffffff);
  border: 1px solid var(--app-border, #e3e3de);
  border-radius: 6px;
  padding: 12px 14px;
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.llm-oauth-info {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
  flex: 1;
}

.llm-oauth-title-line {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.llm-oauth-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--app-text-primary, #161615);
}

.llm-oauth-desc {
  font-size: 13px;
  line-height: 1.45;
  color: var(--app-text-secondary, #454440);
}

.llm-oauth-inline-input {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-top: 6px;
}

.llm-oauth-actions {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
}

.llm-device-code-box {
  margin-top: 6px;
  padding: 8px 10px;
  border-radius: 6px;
  background: var(--app-page-bg, #f4f4f2);
  border: 1px solid var(--app-border, #e3e3de);
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 13px;
}

.llm-device-code-line {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.llm-device-code-val {
  font-size: 15px;
  font-weight: 600;
  color: var(--color-brand, #1f5e5b);
}

.llm-device-code-hint {
  font-size: 12px;
  color: var(--app-text-muted, #66645e);
}

/* ── 省额度黄金编组 ── */
.llm-mode-controls {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.llm-mode-segmented {
  display: inline-flex;
  background: var(--app-surface-subtle, #ecece9);
  border: 1px solid var(--app-border, #e3e3de);
  border-radius: 6px;
  padding: 2px;
}

.llm-seg-btn {
  border: none;
  background: transparent;
  color: var(--app-text-secondary, #454440);
  padding: 5px 12px;
  border-radius: 4px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: background-color 0.16s ease, color 0.16s ease;
}

.llm-seg-btn.is-active {
  background: var(--app-surface, #ffffff);
  color: var(--app-text-primary, #161615);
  font-weight: 600;
}

.llm-role-table {
  display: flex;
  flex-direction: column;
  border: 1px solid var(--app-border, #e3e3de);
  border-radius: 6px;
  overflow: hidden;
}

.llm-role-row {
  display: grid;
  grid-template-columns: minmax(0, 1.15fr) minmax(0, 1fr);
  gap: 16px;
  align-items: center;
  padding: 12px 16px;
  background: var(--app-surface, #ffffff);
  border-bottom: 1px solid var(--app-divider, #eaeae6);
}

.llm-role-row:last-child {
  border-bottom: none;
}

.llm-role-meta {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.llm-role-title-line {
  display: flex;
  align-items: center;
  gap: 8px;
}

.llm-role-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--app-text-primary, #161615);
}

.llm-role-badge {
  font-size: 12px;
  padding: 1px 7px;
  border-radius: 4px;
  background: var(--app-surface-subtle, #ecece9);
  color: var(--app-text-secondary, #454440);
}

.llm-role-badge.role-main {
  background: var(--color-brand-light, rgba(31, 94, 91, 0.08));
  color: var(--color-brand, #1f5e5b);
}

.llm-role-badge.role-cheap {
  background: var(--color-gold-light, #e8dec9);
  color: var(--color-gold, #7a5510);
}

.llm-role-scope {
  font-size: 13px;
  color: var(--app-text-muted, #66645e);
}

.llm-role-controls {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}

.llm-unified-note {
  padding: 12px 14px;
  border-radius: 6px;
  background: var(--app-page-bg, #f4f4f2);
  color: var(--app-text-secondary, #454440);
  font-size: 14px;
  line-height: 1.55;
}

/* ── 收折手动面板 ── */
.llm-manual-section {
  padding: 0;
  overflow: hidden;
}

.llm-collapse-trigger {
  width: 100%;
  border: none;
  background: var(--app-surface, #ffffff);
  padding: 15px 18px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  cursor: pointer;
  text-align: left;
  transition: background-color 0.16s ease;
}

.llm-collapse-trigger:hover {
  background: var(--app-surface-raised, #fafafa);
}

.llm-collapse-title-wrap {
  display: flex;
  align-items: baseline;
  gap: 12px;
  flex-wrap: wrap;
}

.llm-collapse-meta {
  font-size: 13px;
  color: var(--app-text-muted, #66645e);
}

.llm-collapse-action {
  font-size: 13px;
  font-weight: 600;
  color: var(--color-brand, #1f5e5b);
  flex-shrink: 0;
}

.llm-manual-body {
  padding: 0 18px 18px;
  border-top: 1px solid var(--app-divider, #eaeae6);
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.llm-preset-strip {
  margin-top: 14px;
  padding: 14px;
  border: 1px solid var(--app-border, #e3e3de);
  border-radius: 8px;
  background: var(--app-page-bg, #f4f4f2);
}

.llm-preset-strip-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
  flex-wrap: wrap;
}

.llm-preset-strip-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--app-text-primary, #161615);
}

.llm-preset-strip-desc {
  font-size: 13px;
  color: var(--app-text-muted, #66645e);
}

.llm-preset-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(165px, 1fr));
  gap: 10px;
}

.llm-preset-card {
  border: 1px solid var(--app-border, #e3e3de);
  border-radius: 6px;
  background: var(--app-surface, #ffffff);
  padding: 10px 12px;
  text-align: left;
  display: flex;
  flex-direction: column;
  gap: 4px;
  cursor: pointer;
  transition: border-color 0.16s ease, background-color 0.16s ease;
}

.llm-preset-card:hover {
  border-color: var(--color-brand, #1f5e5b);
  background: var(--app-surface-raised, #fafafa);
}

.llm-preset-card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.llm-preset-card-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--app-text-primary, #161615);
}

.llm-preset-card-protocol {
  flex-shrink: 0;
  font-size: 12px;
  color: var(--color-brand, #1f5e5b);
  background: var(--color-brand-light, rgba(31, 94, 91, 0.08));
  border-radius: 4px;
  padding: 1px 6px;
}

.llm-preset-card-model {
  font-size: 12px;
  color: var(--app-text-muted, #66645e);
}

.llm-layout {
  display: grid;
  grid-template-columns: 240px minmax(0, 1fr);
  gap: 14px;
  align-items: start;
}

.llm-sidebar {
  border: 1px solid var(--app-border, #e3e3de);
  border-radius: 8px;
  background: var(--app-page-bg, #f4f4f2);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.llm-sidebar-head {
  padding: 12px 14px;
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 8px;
  border-bottom: 1px solid var(--app-border, #e3e3de);
}

.llm-sidebar-title {
  font-size: 14px;
  font-weight: 600;
}

.llm-sidebar-desc {
  font-size: 12px;
  color: var(--app-text-muted, #66645e);
  margin-top: 2px;
}

.llm-profile-list {
  max-height: 440px;
  overflow-y: auto;
  padding: 10px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.llm-profile-item {
  width: 100%;
  border: 1px solid var(--app-border, #e3e3de);
  border-radius: 6px;
  background: var(--app-surface, #ffffff);
  padding: 10px 12px;
  text-align: left;
  cursor: pointer;
  transition: border-color 0.16s ease, background-color 0.16s ease;
}

.llm-profile-item:hover,
.llm-profile-item.is-selected {
  border-color: var(--color-brand, #1f5e5b);
}

.llm-profile-item.is-active {
  background: var(--color-brand-light, rgba(31, 94, 91, 0.08));
  border-color: var(--color-brand-border, rgba(31, 94, 91, 0.22));
}

.llm-profile-name-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
}

.llm-profile-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--app-text-primary, #161615);
}

.llm-profile-meta {
  margin-top: 4px;
  font-size: 12px;
  color: var(--app-text-muted, #66645e);
}

.llm-card-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
  flex-wrap: wrap;
}

.llm-card-title {
  font-size: 15px;
  font-weight: 600;
}

.llm-card-desc {
  margin-top: 4px;
  font-size: 13px;
  color: var(--app-text-muted, #66645e);
}

.llm-form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
}

.llm-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.llm-field.span-2 {
  grid-column: span 2;
}

.llm-field-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 8px;
}

.llm-label {
  font-size: 13px;
  font-weight: 600;
  color: var(--app-text-secondary, #454440);
}

.llm-model-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 8px;
  align-items: start;
}

.llm-secret-readonly {
  padding: 10px 12px;
  border-radius: 6px;
  background: var(--app-page-bg, #f4f4f2);
  border: 1px solid var(--app-border, #e3e3de);
  font-size: 13px;
  color: var(--app-text-secondary, #454440);
  line-height: 1.5;
}

.llm-secret-hint {
  font-size: 12px;
  color: var(--app-text-muted, #66645e);
}

.llm-legacy-row {
  display: flex;
  align-items: center;
  gap: 10px;
}

.llm-legacy-copy {
  font-size: 13px;
  color: var(--app-text-secondary, #454440);
}

.llm-advanced {
  margin-top: 16px;
}

code {
  font-size: 12px;
  padding: 1px 5px;
  border-radius: 4px;
  background: var(--app-surface-subtle, #ecece9);
  color: var(--app-text-primary, #161615);
}

@media (max-width: 1024px) {
  .llm-connect-grid,
  .llm-layout,
  .llm-role-row {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 720px) {
  .llm-top-ledger {
    flex-direction: column;
    align-items: stretch;
    padding: 12px 14px;
  }

  .llm-ledger-cells,
  .llm-role-controls,
  .llm-form-grid {
    grid-template-columns: 1fr;
  }

  .llm-field.span-2 {
    grid-column: span 1;
  }

  .llm-ledger-actions {
    flex-wrap: wrap;
  }

  .llm-scroll-body {
    padding: 8px 4px 18px;
  }

  .llm-section {
    padding: 12px;
  }

  .llm-oauth-row {
    flex-direction: column;
  }
}
</style>
