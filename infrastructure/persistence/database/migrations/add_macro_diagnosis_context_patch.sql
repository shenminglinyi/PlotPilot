-- 静默注入：系统修正指令 + 触发时全书字数锚点（用于 5~10 万字间隔）
ALTER TABLE macro_diagnosis_results ADD COLUMN context_patch TEXT;
ALTER TABLE macro_diagnosis_results ADD COLUMN total_words_at_run INTEGER DEFAULT 0;
