-- CPMS Phase 1: 新增 prompt_workflows / prompt_bindings / variable_registry 表
-- 用于支持工作流绑定和全局变量注册表
-- 日期: 2026-05-09

-- ========== 提示词工作流定义 ==========
CREATE TABLE IF NOT EXISTS prompt_workflows (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    is_builtin INTEGER NOT NULL DEFAULT 0,
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ========== 提示词工作流绑定 ==========
-- 一个工作流可绑定多个提示词节点，按槽位和优先级组装
CREATE TABLE IF NOT EXISTS prompt_bindings (
    id TEXT PRIMARY KEY,
    workflow_id TEXT NOT NULL,
    node_key TEXT NOT NULL,
    slot TEXT NOT NULL DEFAULT 'system_main',     -- system_main / system_rules / system_lock / user_beat / user_main
    priority INTEGER NOT NULL DEFAULT 50,          -- 小数字优先
    is_required INTEGER NOT NULL DEFAULT 0,
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (workflow_id) REFERENCES prompt_workflows(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_prompt_bindings_workflow ON prompt_bindings(workflow_id);
CREATE INDEX IF NOT EXISTS idx_prompt_bindings_node ON prompt_bindings(node_key);
CREATE UNIQUE INDEX IF NOT EXISTS ux_prompt_bindings_wf_node_slot
    ON prompt_bindings(workflow_id, node_key, slot);

-- ========== 全局变量注册表 ==========
-- 所有提示词模板中使用的变量都有统一的注册和 Schema 定义
CREATE TABLE IF NOT EXISTS variable_registry (
    name TEXT PRIMARY KEY,
    display_name TEXT NOT NULL DEFAULT '',
    type TEXT NOT NULL DEFAULT 'string',           -- string / integer / float / boolean / enum / object / list
    scope TEXT NOT NULL DEFAULT 'chapter',         -- global / novel / chapter / scene / beat
    is_required INTEGER NOT NULL DEFAULT 0,
    default_value TEXT,                            -- JSON 格式的默认值
    description TEXT DEFAULT '',
    source TEXT DEFAULT '',                        -- 数据来源（如 "bible.character.name"）
    enum_values TEXT DEFAULT '[]',                 -- JSON 数组（当 type=enum 时）
    examples TEXT DEFAULT '[]',                    -- JSON 数组，示例值
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_variable_registry_scope ON variable_registry(scope);
CREATE INDEX IF NOT EXISTS idx_variable_registry_type ON variable_registry(type);

-- ========== 提示词调试日志（单节点调试 / COT 展示） ==========
CREATE TABLE IF NOT EXISTS prompt_debug_logs (
    id TEXT PRIMARY KEY,
    node_key TEXT NOT NULL,
    workflow_id TEXT,                              -- 可选：属于哪个工作流
    variables_json TEXT DEFAULT '{}',              -- 渲染时传入的变量快照
    rendered_system TEXT DEFAULT '',
    rendered_user TEXT DEFAULT '',
    llm_response TEXT DEFAULT '',                  -- LLM 原始响应
    cot_trace TEXT DEFAULT '',                     -- Chain-of-Thought 追踪
    token_usage TEXT DEFAULT '{}',                 -- JSON: Token 使用统计
    duration_ms INTEGER DEFAULT 0,                 -- 渲染 + 调用耗时
    status TEXT DEFAULT 'pending',                 -- pending / success / error
    error_message TEXT DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_prompt_debug_node ON prompt_debug_logs(node_key);
CREATE INDEX IF NOT EXISTS idx_prompt_debug_workflow ON prompt_debug_logs(workflow_id);
CREATE INDEX IF NOT EXISTS idx_prompt_debug_status ON prompt_debug_logs(status);
CREATE INDEX IF NOT EXISTS idx_prompt_debug_created ON prompt_debug_logs(created_at DESC);

-- ========== prompt_nodes 表增强：新增 node_type 和 asset_layer 字段 ==========
-- 标识提示词节点的类型和资产层级

-- 添加 node_type 列（如果不存在）
-- node_type: core / agent / skill / rule / contract
-- asset_layer: layer1_json / layer2_hardcoded / layer3_agent / layer4_rule / layer5_skill / layer6_contract

ALTER TABLE prompt_nodes ADD COLUMN node_type TEXT DEFAULT 'core';
ALTER TABLE prompt_nodes ADD COLUMN asset_layer TEXT DEFAULT 'layer1_json';
