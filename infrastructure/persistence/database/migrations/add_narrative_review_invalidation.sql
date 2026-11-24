-- Chapter writes come from the editor, daemon and imports. Publish the review
-- transition in the same SQLite transaction, including for direct SQL writes.
CREATE VIEW IF NOT EXISTS narrative_required_chapter_refs AS
WITH contracts AS NOT MATERIALIZED (
    SELECT novel_id, CASE WHEN json_valid(metadata) THEN
        CASE WHEN json_type(metadata, '$.narrative_progress') = 'object'
             THEN json_extract(metadata, '$.narrative_progress') END END AS plan
    FROM story_nodes
    WHERE node_type = 'volume' AND json_valid(metadata)
), items AS (
    SELECT novel_id, m.value AS item FROM contracts, json_each(plan, '$.milestones') AS m
    WHERE CASE WHEN m.type = 'object' THEN coalesce(json_extract(m.value, '$.required'), 1) END
    UNION ALL
    SELECT novel_id, m.value FROM contracts, json_each(plan, '$.ending_review') AS m
    WHERE m.key IN ('core_conflict', 'character_outcomes', 'ending') AND m.type = 'object'
    UNION ALL
    SELECT novel_id, m.value FROM contracts, json_each(plan, '$.ending_review.required_promises') AS m
    WHERE CASE WHEN m.type = 'object' THEN coalesce(json_extract(m.value, '$.required'), 1) END
)
SELECT novel_id, ref.value AS number,
       json_extract(item, '$.evidence_revisions."' || ref.value || '"') AS signed_revision
FROM items, json_each(item, '$.evidence_chapters') AS ref
WHERE ref.type = 'integer'
UNION ALL
SELECT novel_id, json_extract(plan, '$.ending_review.reviewed_through_chapter'),
       json_extract(plan, '$.ending_review.reviewed_through_revision') FROM contracts
WHERE json_type(plan, '$.ending_review.reviewed_through_chapter') = 'integer';

-- This view is a transaction-local event target; it stores no manuscript data.
CREATE VIEW IF NOT EXISTS narrative_manuscript_change AS
SELECT NULL AS novel_id, NULL AS number, NULL AS membership_changed WHERE 0;

CREATE TRIGGER IF NOT EXISTS reopen_reviewed_story
INSTEAD OF INSERT ON narrative_manuscript_change
BEGIN
    UPDATE novels
    SET current_stage = 'paused_for_review', autopilot_run_epoch = coalesce(autopilot_run_epoch, 0) + 1,
        last_audit_issues = json_insert(
            CASE WHEN (CASE WHEN json_valid(last_audit_issues) THEN json_type(last_audit_issues) END) = 'array'
                 THEN last_audit_issues ELSE '[]' END,
            '$[#]', json_object('code', 'narrative_progress_review_required', 'severity', 'high',
                'message', printf('第%d章的正文或归属已变更，请重新核验受影响的剧情证据和终局。', NEW.number))
        ), updated_at = CURRENT_TIMESTAMP
    WHERE id = NEW.novel_id AND current_stage = 'completed' AND autopilot_status = 'stopped'
      AND EXISTS (SELECT 1 FROM narrative_required_chapter_refs
                  WHERE novel_id = NEW.novel_id AND (NEW.membership_changed OR number = NEW.number));
END;

-- A writer can receive an old completion decision after the author's edit.
-- Compare the signed versions in the same transaction that finalizes the run.
CREATE TRIGGER IF NOT EXISTS recheck_evidence_on_story_completion
AFTER UPDATE OF current_stage, autopilot_status ON novels
WHEN NEW.current_stage = 'completed' AND NEW.autopilot_status = 'stopped'
    AND (OLD.current_stage <> 'completed' OR OLD.autopilot_status <> 'stopped')
BEGIN
    INSERT INTO narrative_manuscript_change
    SELECT NEW.id, ref.number, 0 FROM narrative_required_chapter_refs AS ref
    LEFT JOIN chapters AS c ON c.novel_id = NEW.id AND c.number = ref.number AND c.status = 'completed'
    WHERE ref.novel_id = NEW.id AND (c.manuscript_revision IS NULL OR c.manuscript_revision IS NOT ref.signed_revision)
    LIMIT 1;
END;

CREATE TRIGGER IF NOT EXISTS reopen_story_on_chapter_update
AFTER UPDATE OF manuscript_revision, status, number, novel_id ON chapters
WHEN ((OLD.status = 'completed' AND coalesce(OLD.manuscript_revision,'') <> '')
      OR (NEW.status = 'completed' AND coalesce(NEW.manuscript_revision,'') <> ''))
    AND (OLD.manuscript_revision IS NOT NEW.manuscript_revision OR OLD.status IS NOT NEW.status
        OR OLD.number <> NEW.number OR OLD.novel_id <> NEW.novel_id)
BEGIN
    INSERT INTO narrative_manuscript_change VALUES (
        OLD.novel_id, OLD.number, OLD.status IS NOT NEW.status OR OLD.number <> NEW.number
        OR OLD.novel_id <> NEW.novel_id OR (coalesce(OLD.manuscript_revision,'') = '') <> (coalesce(NEW.manuscript_revision,'') = '')
    );
    INSERT INTO narrative_manuscript_change SELECT NEW.novel_id, NEW.number, 1 WHERE OLD.novel_id <> NEW.novel_id;
END;

CREATE TRIGGER IF NOT EXISTS reopen_story_on_chapter_delete
AFTER DELETE ON chapters WHEN OLD.status = 'completed' AND coalesce(OLD.manuscript_revision,'') <> ''
BEGIN
    INSERT INTO narrative_manuscript_change VALUES (OLD.novel_id, OLD.number, 1);
END;

CREATE TRIGGER IF NOT EXISTS reopen_story_on_chapter_insert
AFTER INSERT ON chapters WHEN NEW.status = 'completed' AND coalesce(NEW.manuscript_revision,'') <> ''
BEGIN
    INSERT INTO narrative_manuscript_change VALUES (NEW.novel_id, NEW.number, 1);
END;
