-- 世界观构建表（Worldbuilding）
CREATE TABLE IF NOT EXISTS worldbuilding (
    id TEXT PRIMARY KEY,
    novel_id TEXT NOT NULL UNIQUE,

    -- 1. 核心法则与底层逻辑
    power_system TEXT DEFAULT '',           -- 力量体系/科技树
    physics_rules TEXT DEFAULT '',          -- 物理规律
    magic_tech TEXT DEFAULT '',             -- 魔法/科技机制

    -- 2. 地理与生态环境
    terrain TEXT DEFAULT '',                -- 地形
    climate TEXT DEFAULT '',                -- 气候
    resources TEXT DEFAULT '',              -- 资源分布
    ecology TEXT DEFAULT '',                -- 生态链

    -- 3. 社会结构与权力分配
    politics TEXT DEFAULT '',               -- 政治体制
    economy TEXT DEFAULT '',                -- 经济模式
    class_system TEXT DEFAULT '',           -- 阶级系统

    -- 4. 历史、信仰与文化
    history TEXT DEFAULT '',                -- 关键历史事件
    religion TEXT DEFAULT '',               -- 宗教信仰
    taboos TEXT DEFAULT '',                 -- 文化禁忌

    -- 5. 沉浸感细节
    food_clothing TEXT DEFAULT '',          -- 衣食住行
    language_slang TEXT DEFAULT '',         -- 俚语口音
    entertainment TEXT DEFAULT '',          -- 娱乐方式

    schema_version INTEGER NOT NULL DEFAULT 1,
    dimensions TEXT NOT NULL DEFAULT '{}',

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (novel_id) REFERENCES novels(id) ON DELETE CASCADE
);
