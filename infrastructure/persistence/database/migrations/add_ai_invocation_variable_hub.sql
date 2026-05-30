-- AI Invocation 与 Variable Hub 持久化底座。
-- 目标：把提示词资产、变量绑定、变量值、调用会话、尝试、采纳与提交结果落成可追溯事实源。

CREATE TABLE IF NOT EXISTS prompt_assets (
    id TEXT PRIMARY KEY,
    asset_key TEXT NOT NULL,
    asset_type TEXT NOT NULL DEFAULT 'system',
    slot TEXT NOT NULL DEFAULT 'system_main',
    scope TEXT NOT NULL DEFAULT 'global',
    name TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'draft',
    owner TEXT NOT NULL DEFAULT '',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(asset_key)
);

CREATE TABLE IF NOT EXISTS prompt_asset_versions (
    id TEXT PRIMARY KEY,
    asset_id TEXT NOT NULL,
    version_number INTEGER NOT NULL,
    body TEXT NOT NULL,
    body_hash TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft',
    change_summary TEXT NOT NULL DEFAULT '',
    created_by TEXT NOT NULL DEFAULT 'system',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY (asset_id) REFERENCES prompt_assets(id) ON DELETE CASCADE,
    UNIQUE(asset_id, version_number)
);

CREATE TABLE IF NOT EXISTS prompt_asset_link_sets (
    id TEXT PRIMARY KEY,
    node_key TEXT NOT NULL,
    node_version_id TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'draft',
    composition_hash TEXT NOT NULL DEFAULT '',
    created_by TEXT NOT NULL DEFAULT 'system',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS prompt_asset_links (
    id TEXT PRIMARY KEY,
    link_set_id TEXT NOT NULL,
    asset_version_id TEXT NOT NULL,
    slot TEXT NOT NULL DEFAULT 'system_main',
    priority INTEGER NOT NULL DEFAULT 50,
    required INTEGER NOT NULL DEFAULT 1,
    enabled INTEGER NOT NULL DEFAULT 1,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY (link_set_id) REFERENCES prompt_asset_link_sets(id) ON DELETE CASCADE,
    FOREIGN KEY (asset_version_id) REFERENCES prompt_asset_versions(id) ON DELETE RESTRICT,
    UNIQUE(link_set_id, slot, priority, asset_version_id)
);

CREATE TABLE IF NOT EXISTS prompt_asset_drafts (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    asset_key TEXT NOT NULL,
    base_asset_version_id TEXT NOT NULL DEFAULT '',
    slot TEXT NOT NULL DEFAULT 'system_main',
    body TEXT NOT NULL,
    body_hash TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS variable_definitions (
    id TEXT PRIMARY KEY,
    variable_key TEXT NOT NULL,
    display_name TEXT NOT NULL DEFAULT '',
    value_type TEXT NOT NULL DEFAULT 'string',
    scope_level TEXT NOT NULL DEFAULT 'global',
    required INTEGER NOT NULL DEFAULT 0,
    default_value_json TEXT,
    description TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'active',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(variable_key)
);

CREATE TABLE IF NOT EXISTS variable_values (
    id TEXT PRIMARY KEY,
    variable_key TEXT NOT NULL,
    scope_level TEXT NOT NULL DEFAULT 'global',
    scope_key TEXT NOT NULL DEFAULT 'global',
    value_json TEXT NOT NULL,
    value_hash TEXT NOT NULL DEFAULT '',
    version_number INTEGER NOT NULL DEFAULT 1,
    is_current INTEGER NOT NULL DEFAULT 1,
    source_session_id TEXT NOT NULL DEFAULT '',
    source_attempt_id TEXT NOT NULL DEFAULT '',
    source_trace_id TEXT NOT NULL DEFAULT '',
    source_node_key TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY (variable_key) REFERENCES variable_definitions(variable_key) ON DELETE CASCADE
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_variable_values_current
    ON variable_values(variable_key, scope_level, scope_key)
    WHERE is_current = 1;

CREATE INDEX IF NOT EXISTS idx_variable_values_lookup
    ON variable_values(variable_key, scope_level, scope_key, version_number DESC);

CREATE TABLE IF NOT EXISTS variable_lineage (
    id TEXT PRIMARY KEY,
    variable_value_id TEXT NOT NULL,
    source_session_id TEXT NOT NULL DEFAULT '',
    source_attempt_id TEXT NOT NULL DEFAULT '',
    source_trace_id TEXT NOT NULL DEFAULT '',
    source_node_key TEXT NOT NULL DEFAULT '',
    source_commit_id TEXT NOT NULL DEFAULT '',
    lineage_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (variable_value_id) REFERENCES variable_values(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS cpms_variable_binding_sets (
    id TEXT PRIMARY KEY,
    node_key TEXT NOT NULL,
    direction TEXT NOT NULL DEFAULT 'input',
    version_number INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL DEFAULT 'draft',
    is_active INTEGER NOT NULL DEFAULT 0,
    created_by TEXT NOT NULL DEFAULT 'system',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    UNIQUE(node_key, direction, version_number)
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_cpms_variable_binding_sets_active
    ON cpms_variable_binding_sets(node_key, direction)
    WHERE is_active = 1;

CREATE TABLE IF NOT EXISTS cpms_variable_bindings (
    id TEXT PRIMARY KEY,
    binding_set_id TEXT NOT NULL,
    node_key TEXT NOT NULL,
    direction TEXT NOT NULL DEFAULT 'input',
    alias TEXT NOT NULL,
    variable_key TEXT NOT NULL DEFAULT '',
    required INTEGER NOT NULL DEFAULT 0,
    default_value_json TEXT,
    source TEXT NOT NULL DEFAULT '',
    extractor_key TEXT NOT NULL DEFAULT '',
    enabled INTEGER NOT NULL DEFAULT 1,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY (binding_set_id) REFERENCES cpms_variable_binding_sets(id) ON DELETE CASCADE,
    UNIQUE(binding_set_id, direction, alias)
);

CREATE TABLE IF NOT EXISTS invocation_specs (
    id TEXT PRIMARY KEY,
    operation TEXT NOT NULL,
    node_key TEXT NOT NULL,
    spec_version INTEGER NOT NULL DEFAULT 1,
    prompt_node_version_id TEXT NOT NULL DEFAULT '',
    asset_link_set_id TEXT NOT NULL DEFAULT '',
    input_binding_set_id TEXT NOT NULL DEFAULT '',
    output_binding_set_id TEXT NOT NULL DEFAULT '',
    default_policy TEXT NOT NULL DEFAULT 'DIRECT',
    risk_level TEXT NOT NULL DEFAULT 'low',
    supports_stream INTEGER NOT NULL DEFAULT 0,
    continuation_handler_key TEXT NOT NULL DEFAULT '',
    commit_policy_key TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'published',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(operation, node_key, spec_version)
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_invocation_specs_active
    ON invocation_specs(operation, node_key)
    WHERE status = 'published';

CREATE TABLE IF NOT EXISTS ai_invocation_sessions (
    id TEXT PRIMARY KEY,
    operation TEXT NOT NULL,
    node_key TEXT NOT NULL,
    policy TEXT NOT NULL,
    status TEXT NOT NULL,
    context_json TEXT NOT NULL DEFAULT '{}',
    continuation_json TEXT NOT NULL DEFAULT '{}',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    prompt_snapshot_json TEXT NOT NULL DEFAULT '{}',
    variables_snapshot_json TEXT NOT NULL DEFAULT '{}',
    attempts_json TEXT NOT NULL DEFAULT '[]',
    trace_id TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_ai_invocation_sessions_lookup
    ON ai_invocation_sessions(operation, node_key, status, updated_at);

CREATE TABLE IF NOT EXISTS ai_invocation_prompt_drafts (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    draft_revision INTEGER NOT NULL DEFAULT 1,
    base_node_version_id TEXT NOT NULL DEFAULT '',
    user_template TEXT NOT NULL DEFAULT '',
    variable_overrides_json TEXT NOT NULL DEFAULT '{}',
    system_asset_draft_refs_json TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'draft',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY (session_id) REFERENCES ai_invocation_sessions(id) ON DELETE CASCADE,
    UNIQUE(session_id, draft_revision)
);

CREATE TABLE IF NOT EXISTS ai_invocation_attempts (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    status TEXT NOT NULL,
    prompt_snapshot_json TEXT NOT NULL DEFAULT '{}',
    content TEXT NOT NULL DEFAULT '',
    token_usage_json TEXT NOT NULL DEFAULT '{}',
    error TEXT NOT NULL DEFAULT '',
    trace_id TEXT NOT NULL DEFAULT '',
    started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY (session_id) REFERENCES ai_invocation_sessions(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_ai_invocation_attempts_session
    ON ai_invocation_attempts(session_id, status, started_at);

CREATE TABLE IF NOT EXISTS ai_adoption_decisions (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    attempt_id TEXT NOT NULL,
    decision TEXT NOT NULL DEFAULT 'accepted',
    accept_content INTEGER NOT NULL DEFAULT 1,
    commit_prompt_version INTEGER NOT NULL DEFAULT 0,
    commit_variable_outputs INTEGER NOT NULL DEFAULT 0,
    commit_variable_bindings INTEGER NOT NULL DEFAULT 0,
    accepted_content TEXT NOT NULL DEFAULT '',
    accepted_by TEXT NOT NULL DEFAULT '',
    accepted_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY (session_id) REFERENCES ai_invocation_sessions(id) ON DELETE CASCADE,
    FOREIGN KEY (attempt_id) REFERENCES ai_invocation_attempts(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_ai_adoption_decisions_session
    ON ai_adoption_decisions(session_id, decision, accepted_at);

CREATE TABLE IF NOT EXISTS ai_adoption_commits (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    decision_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    idempotency_key TEXT NOT NULL,
    result_json TEXT NOT NULL DEFAULT '{}',
    error TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES ai_invocation_sessions(id) ON DELETE CASCADE,
    FOREIGN KEY (decision_id) REFERENCES ai_adoption_decisions(id) ON DELETE CASCADE,
    UNIQUE(idempotency_key)
);

CREATE INDEX IF NOT EXISTS idx_ai_adoption_commits_session
    ON ai_adoption_commits(session_id, status, updated_at);

CREATE TABLE IF NOT EXISTS ai_adoption_commit_steps (
    id TEXT PRIMARY KEY,
    commit_id TEXT NOT NULL,
    step_name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    step_idempotency_key TEXT NOT NULL,
    result_json TEXT NOT NULL DEFAULT '{}',
    error TEXT NOT NULL DEFAULT '',
    started_at TEXT,
    finished_at TEXT,
    FOREIGN KEY (commit_id) REFERENCES ai_adoption_commits(id) ON DELETE CASCADE,
    UNIQUE(commit_id, step_name),
    UNIQUE(step_idempotency_key)
);
