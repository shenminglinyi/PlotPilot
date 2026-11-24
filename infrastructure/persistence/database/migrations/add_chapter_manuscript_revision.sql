-- The content and its revision change in the same SQLite transaction, including
-- direct SQL, UPSERT and queued writes. Empty/whitespace-only plans use ''.
BEGIN IMMEDIATE;
ALTER TABLE chapters ADD COLUMN manuscript_revision TEXT;

CREATE TRIGGER chapter_revision_after_insert
AFTER INSERT ON chapters WHEN NEW.manuscript_revision IS NULL
BEGIN
    UPDATE chapters SET manuscript_revision = CASE
        WHEN trim(NEW.content, char(9,10,11,12,13,28,29,30,31,32,133,160,5760,8192,8193,8194,8195,8196,8197,8198,8199,8200,8201,8202,8232,8233,8239,8287,12288)) <> ''
        THEN lower(hex(randomblob(16))) ELSE '' END
    WHERE rowid = NEW.rowid;
END;

CREATE TRIGGER chapter_revision_after_edit
AFTER UPDATE OF content ON chapters WHEN NEW.content IS NOT OLD.content
BEGIN
    UPDATE chapters SET manuscript_revision = CASE
        WHEN trim(NEW.content, char(9,10,11,12,13,28,29,30,31,32,133,160,5760,8192,8193,8194,8195,8196,8197,8198,8199,8200,8201,8202,8232,8233,8239,8287,12288)) <> ''
        THEN lower(hex(randomblob(16))) ELSE '' END
    WHERE rowid = NEW.rowid;
END;

UPDATE chapters SET manuscript_revision = CASE
    WHEN trim(content, char(9,10,11,12,13,28,29,30,31,32,133,160,5760,8192,8193,8194,8195,8196,8197,8198,8199,8200,8201,8202,8232,8233,8239,8287,12288)) <> ''
    THEN lower(hex(randomblob(16))) ELSE '' END
WHERE manuscript_revision IS NULL;
COMMIT;
