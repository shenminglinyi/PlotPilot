-- SQLite — 业务数据均为关系列/子表，不在库内存 JSON 文本列（Bible 等文件存储另议）

CREATE TABLE IF NOT EXISTS novels (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    slug TEXT UNIQUE NOT NULL,
    author TEXT DEFAULT '未知作者',
    target_chapters INTEGER NOT NULL DEFAULT 0,
    premise TEXT DEFAULT '',
    autopilot_status TEXT DEFAULT 'stopped',
    auto_approve_mode INTEGER NOT NULL DEFAULT 0,
    current_stage TEXT DEFAULT 'planning',
    current_act INTEGER DEFAULT 0,
    current_chapter_in_act INTEGER DEFAULT 0,
    max_auto_chapters INTEGER DEFAULT 9999,
    current_auto_chapters INTEGER DEFAULT 0,
    last_chapter_tension INTEGER DEFAULT 0,
    consecutive_error_count INTEGER DEFAULT 0,
    current_beat_index INTEGER DEFAULT 0,
    last_audit_chapter_number INTEGER,
    last_audit_similarity REAL,
    last_audit_drift_alert INTEGER DEFAULT 0,
    last_audit_narrative_ok INTEGER DEFAULT 1,
    last_audit_at TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS chapters (
    id TEXT PRIMARY KEY,
    novel_id TEXT NOT NULL,
    number INTEGER NOT NULL,
    title TEXT,
    content TEXT,
    outline TEXT,
    status TEXT DEFAULT 'draft',
    tension_score REAL DEFAULT 50.0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (novel_id) REFERENCES novels(id) ON DELETE CASCADE,
    UNIQUE(novel_id, number)
);

-- 三元组主行（无 JSON 列）
CREATE TABLE IF NOT EXISTS triples (
    id TEXT PRIMARY KEY,
    novel_id TEXT NOT NULL,
    subject TEXT NOT NULL,
    predicate TEXT NOT NULL,
    object TEXT NOT NULL,
    chapter_number INTEGER,
    note TEXT,
    entity_type TEXT,
    importance TEXT,
    location_type TEXT,
    description TEXT,
    first_appearance INTEGER,
    confidence REAL,
    source_type TEXT,
    subject_entity_id TEXT,
    object_entity_id TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (novel_id) REFERENCES novels(id) ON DELETE CASCADE,
    FOREIGN KEY (novel_id, chapter_number) REFERENCES chapters(novel_id, number) ON DELETE SET NULL
);

-- 除主 chapter_number 外，另有关联章节（多对多）
CREATE TABLE IF NOT EXISTS triple_more_chapters (
    triple_id TEXT NOT NULL,
    novel_id TEXT NOT NULL,
    chapter_number INTEGER NOT NULL,
    PRIMARY KEY (triple_id, chapter_number),
    FOREIGN KEY (triple_id) REFERENCES triples(id) ON DELETE CASCADE,
    FOREIGN KEY (novel_id, chapter_number) REFERENCES chapters(novel_id, number) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS triple_tags (
    triple_id TEXT NOT NULL,
    tag TEXT NOT NULL,
    PRIMARY KEY (triple_id, tag),
    FOREIGN KEY (triple_id) REFERENCES triples(id) ON DELETE CASCADE
);

-- 扩展键值，值一律 TEXT（非 JSON）
CREATE TABLE IF NOT EXISTS triple_attr (
    triple_id TEXT NOT NULL,
    attr_key TEXT NOT NULL,
    attr_value TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (triple_id, attr_key),
    FOREIGN KEY (triple_id) REFERENCES triples(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS knowledge (
    id TEXT PRIMARY KEY,
    novel_id TEXT UNIQUE NOT NULL,
    version INTEGER DEFAULT 1,
    premise_lock TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (novel_id) REFERENCES novels(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS chapter_summaries (
    id TEXT PRIMARY KEY,
    knowledge_id TEXT NOT NULL,
    chapter_number INTEGER NOT NULL,
    summary TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (knowledge_id) REFERENCES knowledge(id) ON DELETE CASCADE,
    UNIQUE(knowledge_id, chapter_number)
);

CREATE INDEX IF NOT EXISTS idx_chapters_novel_id ON chapters(novel_id);
CREATE INDEX IF NOT EXISTS idx_chapters_number ON chapters(novel_id, number);
CREATE INDEX IF NOT EXISTS idx_triples_novel_id ON triples(novel_id);
CREATE INDEX IF NOT EXISTS idx_novels_autopilot_status ON novels(autopilot_status);
CREATE INDEX IF NOT EXISTS idx_novels_current_stage ON novels(current_stage);
CREATE INDEX IF NOT EXISTS idx_triples_subject ON triples(novel_id, subject);
CREATE INDEX IF NOT EXISTS idx_triples_predicate ON triples(predicate);

-- ========== Chapter Reviews（章节审阅记录：与工作台「审定」同源） ==========
CREATE TABLE IF NOT EXISTS chapter_reviews (
    novel_id TEXT NOT NULL,
    chapter_number INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft',
    memo TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (novel_id, chapter_number),
    FOREIGN KEY (novel_id, chapter_number) REFERENCES chapters(novel_id, number) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_chapter_reviews_novel ON chapter_reviews(novel_id);
CREATE INDEX IF NOT EXISTS idx_triples_entity_type ON triples(novel_id, entity_type);
CREATE INDEX IF NOT EXISTS idx_triples_chapter ON triples(novel_id, chapter_number);
CREATE INDEX IF NOT EXISTS idx_triples_source ON triples(novel_id, source_type);
CREATE INDEX IF NOT EXISTS idx_triple_more_chapters_triple ON triple_more_chapters(triple_id);
CREATE INDEX IF NOT EXISTS idx_triple_tags_triple ON triple_tags(triple_id);
CREATE INDEX IF NOT EXISTS idx_triple_attr_triple ON triple_attr(triple_id);
CREATE INDEX IF NOT EXISTS idx_chapter_summaries_knowledge_id ON chapter_summaries(knowledge_id);

-- 三元组溯源：关联 story_nodes / chapter_elements（推断证据链，非 JSON 列）
CREATE TABLE IF NOT EXISTS triple_provenance (
    id TEXT PRIMARY KEY,
    triple_id TEXT NOT NULL,
    novel_id TEXT NOT NULL,
    story_node_id TEXT,
    chapter_element_id TEXT,
    rule_id TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'primary',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (triple_id) REFERENCES triples(id) ON DELETE CASCADE,
    FOREIGN KEY (novel_id) REFERENCES novels(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_triple_provenance_triple ON triple_provenance(triple_id);
CREATE INDEX IF NOT EXISTS idx_triple_provenance_novel ON triple_provenance(novel_id);
CREATE INDEX IF NOT EXISTS idx_triple_provenance_story_node ON triple_provenance(story_node_id);

-- 同一三元组下同规则+章节节点+元素行只保留一条（INSERT OR IGNORE 依赖）
CREATE UNIQUE INDEX IF NOT EXISTS ux_triple_provenance_with_element
ON triple_provenance (triple_id, rule_id, story_node_id, chapter_element_id)
WHERE chapter_element_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS ux_triple_provenance_null_element
ON triple_provenance (triple_id, rule_id, IFNULL(story_node_id, ''))
WHERE chapter_element_id IS NULL;

-- 故事结构（知识图谱推断依赖；不设 characters/locations 外键以免缺表）
CREATE TABLE IF NOT EXISTS story_nodes (
    id TEXT PRIMARY KEY,
    novel_id TEXT NOT NULL,
    parent_id TEXT,
    node_type TEXT NOT NULL CHECK(node_type IN ('part', 'volume', 'act', 'chapter')),
    number INTEGER NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    order_index INTEGER NOT NULL,
    planning_status TEXT DEFAULT 'draft'
      CHECK(planning_status IN ('draft', 'ai_generated', 'user_edited', 'confirmed')),
    planning_source TEXT DEFAULT 'manual'
      CHECK(planning_source IN ('manual', 'ai_macro', 'ai_act')),
    chapter_start INTEGER,
    chapter_end INTEGER,
    chapter_count INTEGER DEFAULT 0,
    suggested_chapter_count INTEGER,
    content TEXT,
    outline TEXT,
    word_count INTEGER DEFAULT 0,
    status TEXT DEFAULT 'draft',
    themes TEXT,
    key_events TEXT,
    narrative_arc TEXT,
    conflicts TEXT,
    pov_character_id TEXT,
    timeline_start TEXT,
    timeline_end TEXT,
    metadata TEXT DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (novel_id) REFERENCES novels(id) ON DELETE CASCADE,
    FOREIGN KEY (parent_id) REFERENCES story_nodes(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_story_nodes_novel_id ON story_nodes(novel_id);

CREATE TABLE IF NOT EXISTS chapter_elements (
    id TEXT PRIMARY KEY,
    chapter_id TEXT NOT NULL,
    element_type TEXT NOT NULL CHECK(element_type IN ('character', 'location', 'item', 'organization', 'event')),
    element_id TEXT NOT NULL,
    relation_type TEXT NOT NULL CHECK(relation_type IN (
        'appears', 'mentioned', 'scene', 'uses', 'involved', 'occurs'
    )),
    importance TEXT DEFAULT 'normal' CHECK(importance IN ('major', 'normal', 'minor')),
    appearance_order INTEGER,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (chapter_id) REFERENCES story_nodes(id) ON DELETE CASCADE,
    UNIQUE(chapter_id, element_type, element_id, relation_type)
);

CREATE INDEX IF NOT EXISTS idx_chapter_elements_chapter ON chapter_elements(chapter_id);
CREATE INDEX IF NOT EXISTS idx_chapter_elements_element ON chapter_elements(element_type, element_id);

CREATE TABLE IF NOT EXISTS chapter_scenes (
    id TEXT PRIMARY KEY,
    chapter_id TEXT NOT NULL,
    scene_number INTEGER NOT NULL,
    location_id TEXT,
    timeline TEXT,
    summary TEXT,
    purpose TEXT,
    content TEXT,
    word_count INTEGER DEFAULT 0,
    characters TEXT,
    order_index INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (chapter_id) REFERENCES story_nodes(id) ON DELETE CASCADE,
    UNIQUE(chapter_id, scene_number)
);

CREATE INDEX IF NOT EXISTS idx_chapter_scenes_chapter ON chapter_scenes(chapter_id);

-- ========== Bible（自包含子表，外键仅指向 novels）==========
CREATE TABLE IF NOT EXISTS bibles (
    id TEXT PRIMARY KEY,
    novel_id TEXT NOT NULL UNIQUE,
    schema_version INTEGER NOT NULL DEFAULT 1,
    extensions TEXT NOT NULL DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (novel_id) REFERENCES novels(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_bibles_novel_id ON bibles(novel_id);

CREATE TABLE IF NOT EXISTS bible_characters (
    id TEXT PRIMARY KEY,
    novel_id TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    mental_state TEXT DEFAULT 'NORMAL',
    mental_state_reason TEXT DEFAULT '',
    verbal_tic TEXT DEFAULT '',
    idle_behavior TEXT DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (novel_id) REFERENCES novels(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_bible_characters_novel ON bible_characters(novel_id);

CREATE TABLE IF NOT EXISTS bible_character_relationships (
    id TEXT PRIMARY KEY,
    character_id TEXT NOT NULL,
    target_name TEXT NOT NULL,
    relation TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    FOREIGN KEY (character_id) REFERENCES bible_characters(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_bible_char_rels_character ON bible_character_relationships(character_id);

CREATE TABLE IF NOT EXISTS bible_world_settings (
    id TEXT PRIMARY KEY,
    novel_id TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    setting_type TEXT NOT NULL DEFAULT 'other',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (novel_id) REFERENCES novels(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_bible_world_novel ON bible_world_settings(novel_id);

CREATE TABLE IF NOT EXISTS bible_locations (
    id TEXT PRIMARY KEY,
    novel_id TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    location_type TEXT NOT NULL DEFAULT 'other',
    parent_id TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (novel_id) REFERENCES novels(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_bible_locations_novel ON bible_locations(novel_id);

CREATE TABLE IF NOT EXISTS bible_timeline_notes (
    id TEXT PRIMARY KEY,
    novel_id TEXT NOT NULL,
    event TEXT NOT NULL DEFAULT '',
    time_point TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (novel_id) REFERENCES novels(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_bible_timeline_novel ON bible_timeline_notes(novel_id, sort_order);

CREATE TABLE IF NOT EXISTS bible_style_notes (
    id TEXT PRIMARY KEY,
    novel_id TEXT NOT NULL,
    category TEXT NOT NULL,
    content TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (novel_id) REFERENCES novels(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_bible_style_novel ON bible_style_notes(novel_id);

-- ========== 故事线 + 里程碑 ==========
CREATE TABLE IF NOT EXISTS storylines (
    id TEXT PRIMARY KEY,
    novel_id TEXT NOT NULL,
    storyline_type TEXT NOT NULL,
    status TEXT NOT NULL,
    estimated_chapter_start INTEGER NOT NULL,
    estimated_chapter_end INTEGER NOT NULL,
    current_milestone_index INTEGER NOT NULL DEFAULT 0,
    extensions TEXT NOT NULL DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (novel_id) REFERENCES novels(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_storylines_novel ON storylines(novel_id);

CREATE TABLE IF NOT EXISTS storyline_milestones (
    id TEXT PRIMARY KEY,
    storyline_id TEXT NOT NULL,
    milestone_order INTEGER NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    target_chapter_start INTEGER NOT NULL,
    target_chapter_end INTEGER NOT NULL,
    prerequisite_list TEXT NOT NULL DEFAULT '',
    milestone_triggers TEXT NOT NULL DEFAULT '',
    FOREIGN KEY (storyline_id) REFERENCES storylines(id) ON DELETE CASCADE,
    UNIQUE(storyline_id, milestone_order)
);

CREATE INDEX IF NOT EXISTS idx_storyline_milestones_storyline ON storyline_milestones(storyline_id);

-- ========== 情节弧 + 剧情点（一书多弧，slug 区分卷/视角等；API 默认 slug=default）==========
CREATE TABLE IF NOT EXISTS plot_arcs (
    id TEXT PRIMARY KEY,
    novel_id TEXT NOT NULL,
    slug TEXT NOT NULL DEFAULT 'default',
    display_name TEXT NOT NULL DEFAULT '',
    extensions TEXT NOT NULL DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (novel_id) REFERENCES novels(id) ON DELETE CASCADE,
    UNIQUE(novel_id, slug)
);

CREATE INDEX IF NOT EXISTS idx_plot_arcs_novel ON plot_arcs(novel_id);
CREATE INDEX IF NOT EXISTS idx_plot_arcs_novel_slug ON plot_arcs(novel_id, slug);

CREATE TABLE IF NOT EXISTS plot_points (
    id TEXT PRIMARY KEY,
    plot_arc_id TEXT NOT NULL,
    sort_order INTEGER NOT NULL,
    chapter_number INTEGER NOT NULL,
    point_type TEXT NOT NULL,
    description TEXT NOT NULL,
    tension INTEGER NOT NULL,
    FOREIGN KEY (plot_arc_id) REFERENCES plot_arcs(id) ON DELETE CASCADE,
    UNIQUE(plot_arc_id, chapter_number)
);

CREATE INDEX IF NOT EXISTS idx_plot_points_arc ON plot_points(plot_arc_id, sort_order);

-- ========== 事件溯源架构（Event Sourcing）==========
-- entity_base：静态基座（core_attributes 为 JSON 文本）
CREATE TABLE IF NOT EXISTS entity_base (
    id TEXT PRIMARY KEY,
    novel_id TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    name TEXT NOT NULL,
    core_attributes TEXT NOT NULL DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (novel_id) REFERENCES novels(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_entity_base_novel ON entity_base(novel_id, entity_type);

-- narrative_events：章节事件流（mutations 为 JSON 文本数组）
CREATE TABLE IF NOT EXISTS narrative_events (
    event_id TEXT PRIMARY KEY,
    novel_id TEXT NOT NULL,
    chapter_number INTEGER NOT NULL,
    event_summary TEXT NOT NULL DEFAULT '',
    mutations TEXT NOT NULL DEFAULT '[]',
    tags TEXT NOT NULL DEFAULT '[]',
    timestamp_ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (novel_id) REFERENCES novels(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_narrative_events_novel_chapter
    ON narrative_events(novel_id, chapter_number);

-- ========== 文风金库（Voice Vault）==========
-- voice_vault：AI 原文与作者改稿样本对
CREATE TABLE IF NOT EXISTS voice_vault (
    sample_id TEXT PRIMARY KEY,
    novel_id TEXT NOT NULL,
    chapter_number INTEGER NOT NULL,
    scene_type TEXT,
    ai_original TEXT NOT NULL,
    author_refined TEXT NOT NULL,
    diff_analysis TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (novel_id) REFERENCES novels(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_voice_vault_novel ON voice_vault(novel_id, chapter_number);

-- voice_fingerprint：文风指纹（统计特征）
CREATE TABLE IF NOT EXISTS voice_fingerprint (
    fingerprint_id TEXT PRIMARY KEY,
    novel_id TEXT NOT NULL,
    pov_character_id TEXT,
    adjective_density REAL,
    avg_sentence_length REAL,
    sentence_count INTEGER,
    sample_count INTEGER,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (novel_id) REFERENCES novels(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_voice_fingerprint_novel ON voice_fingerprint(novel_id);

-- ========== 伏笔注册表 + 潜台词账本（单库 JSON 快照，替代文件 foreshadowings/*.json）==========
CREATE TABLE IF NOT EXISTS novel_foreshadow_registry (
    novel_id TEXT PRIMARY KEY,
    payload TEXT NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (novel_id) REFERENCES novels(id) ON DELETE CASCADE
);

-- ========== 文风漂移监控（Phase 5 Task 6）==========
-- 每章生成后与作者指纹的相似度评分（0~1），用于连续漂移告警
CREATE TABLE IF NOT EXISTS chapter_style_scores (
    score_id TEXT PRIMARY KEY,
    novel_id TEXT NOT NULL,
    chapter_number INTEGER NOT NULL,
    adjective_density REAL NOT NULL DEFAULT 0.0,
    avg_sentence_length REAL NOT NULL DEFAULT 0.0,
    sentence_count INTEGER NOT NULL DEFAULT 0,
    similarity_score REAL NOT NULL DEFAULT 0.0,
    computed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (novel_id) REFERENCES novels(id) ON DELETE CASCADE,
    UNIQUE(novel_id, chapter_number)
);

CREATE INDEX IF NOT EXISTS idx_chapter_style_scores_novel
    ON chapter_style_scores(novel_id, chapter_number);

-- ========== 语义化快照系统（战役三 Task 12）==========
-- Git-like 版本控制，只存指针不存正文深拷贝
CREATE TABLE IF NOT EXISTS novel_snapshots (
    id TEXT PRIMARY KEY,
    novel_id TEXT NOT NULL,
    parent_snapshot_id TEXT,
    branch_name TEXT NOT NULL DEFAULT 'main',
    trigger_type TEXT NOT NULL,  -- AUTO / MANUAL
    name TEXT NOT NULL,
    description TEXT,
    chapter_pointers TEXT NOT NULL,  -- JSON: 章节 ID 列表
    bible_state TEXT,  -- JSON: Bible 快照
    foreshadow_state TEXT,  -- JSON: 伏笔账本快照
    graph_state TEXT,  -- JSON: 知识图谱快照（可选）
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (novel_id) REFERENCES novels(id) ON DELETE CASCADE,
    FOREIGN KEY (parent_snapshot_id) REFERENCES novel_snapshots(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_novel_snapshots_novel ON novel_snapshots(novel_id);
CREATE INDEX IF NOT EXISTS idx_novel_snapshots_branch ON novel_snapshots(novel_id, branch_name);


-- ========== 提示词广场系统（Prompt Plaza）==========
-- 模板包：一组相关提示词的集合（如"内置"、"自定义工作流"）
CREATE TABLE IF NOT EXISTS prompt_templates (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    category TEXT NOT NULL DEFAULT 'user',  -- builtin / user / workflow
    version TEXT NOT NULL DEFAULT '1.0.0',
    author TEXT DEFAULT '',
    icon TEXT DEFAULT '📦',
    color TEXT DEFAULT '#6b7280',
    is_builtin INTEGER NOT NULL DEFAULT 0,
    metadata TEXT NOT NULL DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 提示词节点：单个提示词（有版本历史）
CREATE TABLE IF NOT EXISTS prompt_nodes (
    id TEXT PRIMARY KEY,
    template_id TEXT NOT NULL,
    node_key TEXT NOT NULL,           -- 唯一标识，如 "chapter-generation-main"
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    category TEXT NOT NULL DEFAULT 'generation',  -- generation/extraction/review/planning/world/creative
    source TEXT DEFAULT '',            -- 来源代码位置
    output_format TEXT DEFAULT 'text',  -- text / json
    contract_module TEXT,              -- Pydantic 合约模块
    contract_model TEXT,               -- Pydantic 合约模型名
    tags TEXT NOT NULL DEFAULT '[]',   -- JSON 数组
    variables TEXT NOT NULL DEFAULT '[]',  -- JSON: 变量定义列表
    system_file TEXT,                  -- 预留，可为空（正文在 prompt_versions.system_prompt）
    is_builtin INTEGER NOT NULL DEFAULT 0,
    sort_order INTEGER NOT NULL DEFAULT 0,
    active_version_id TEXT,            -- 当前激活版本 ID
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (template_id) REFERENCES prompt_templates(id) ON DELETE CASCADE
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_prompt_nodes_node_key ON prompt_nodes(node_key);
CREATE INDEX IF NOT EXISTS idx_prompt_nodes_template ON prompt_nodes(template_id);
CREATE INDEX IF NOT EXISTS idx_prompt_nodes_category ON prompt_nodes(category);

-- 提示词版本：每个节点的版本历史（支持回滚）
CREATE TABLE IF NOT EXISTS prompt_versions (
    id TEXT PRIMARY KEY,
    node_id TEXT NOT NULL,
    version_number INTEGER NOT NULL,
    system_prompt TEXT NOT NULL DEFAULT '',     -- System 角色提示词
    user_template TEXT NOT NULL DEFAULT '',      -- User 模板
    change_summary TEXT DEFAULT '',             -- 版本变更说明
    created_by TEXT DEFAULT 'system',           -- system / user
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (node_id) REFERENCES prompt_nodes(id) ON DELETE CASCADE,
    UNIQUE(node_id, version_number)
);

CREATE INDEX IF NOT EXISTS idx_prompt_versions_node ON prompt_versions(node_id);
CREATE INDEX IF NOT EXISTS idx_prompt_versions_node_ver ON prompt_versions(node_id, version_number DESC);


-- ========== 嵌入模型配置（Embedding Config）==========
-- 全局唯一的嵌入服务配置（本地模型 / OpenAI 云端）
CREATE TABLE IF NOT EXISTS embedding_config (
    id TEXT PRIMARY KEY DEFAULT 'default',
    mode TEXT NOT NULL DEFAULT 'local' CHECK(mode IN ('local', 'openai')),
    api_key TEXT NOT NULL DEFAULT '',
    base_url TEXT NOT NULL DEFAULT '',
    model TEXT NOT NULL DEFAULT 'text-embedding-3-small',
    use_gpu INTEGER NOT NULL DEFAULT 1,
    model_path TEXT NOT NULL DEFAULT 'BAAI/bge-small-zh-v1.5',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);


-- ========== LLM 控制面板配置（LLM Profiles）==========
-- 替代原 llm_profiles.json 本地文件存储，持久化到 SQLite。
-- active_profile_id 存储在 llm_config_meta 行中。

CREATE TABLE IF NOT EXISTS llm_config_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS llm_profiles (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL DEFAULT '',
    preset_key TEXT NOT NULL DEFAULT 'custom-openai-compatible',
    protocol TEXT NOT NULL DEFAULT 'openai' CHECK(protocol IN ('openai', 'anthropic', 'gemini')),
    base_url TEXT NOT NULL DEFAULT '',
    api_key TEXT NOT NULL DEFAULT '',
    model TEXT NOT NULL DEFAULT '',
    temperature REAL NOT NULL DEFAULT 0.7,
    max_tokens INTEGER NOT NULL DEFAULT 4096,
    timeout_seconds INTEGER NOT NULL DEFAULT 300,
    extra_headers TEXT NOT NULL DEFAULT '{}',
    extra_query TEXT NOT NULL DEFAULT '{}',
    extra_body TEXT NOT NULL DEFAULT '{}',
    notes TEXT NOT NULL DEFAULT '',
    use_legacy_chat_completions INTEGER NOT NULL DEFAULT 0,
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_llm_profiles_sort ON llm_profiles(sort_order);



