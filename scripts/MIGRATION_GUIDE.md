# Checkpoint to Snapshot Migration Scripts

## Overview

These scripts migrate data from the `checkpoints` table to the `novel_snapshots` table as part of unifying the Checkpoint and Snapshot systems for the Story Evolution Tab feature.

## Files Created

1. **scripts/migrate_checkpoints_to_snapshots.py** - Main migration script
2. **scripts/verify_migration.py** - Verification script
3. **scripts/test_migration_scripts.py** - Integration test script

## Migration Mapping

The migration maps `checkpoints` fields to `novel_snapshots` fields:

| Checkpoint Field | Snapshot Field | Notes |
|-----------------|----------------|-------|
| `id` | `id` | Direct copy |
| `story_id` | `novel_id` | Field renamed |
| `parent_id` | `parent_snapshot_id` | Field renamed |
| `trigger_type` | `trigger_type` | Values mapped: chapter/act/milestone → AUTO, manual → MANUAL |
| `trigger_reason` | `name` | Field renamed |
| `story_state` | `story_state` | Engine state field |
| `character_masks` | `character_masks` | Engine state field |
| `emotion_ledger` | `emotion_ledger` | Engine state field |
| `active_foreshadows` | `active_foreshadows` | Engine state field |
| `outline` | `outline` | Engine state field |
| `recent_chapters_summary` | `recent_chapters_summary` | Engine state field |

Additional fields in `novel_snapshots`:
- `branch_name`: Always set to 'main'
- `chapter_pointers`: Set to '[]' (checkpoints don't store chapter pointers)
- `bible_state`: Set to '{}' (checkpoints don't store bible state)
- `foreshadow_state`: Set to '{}' (checkpoints don't store foreshadow state)

## Usage

### 1. Pre-Migration Verification

Before running the migration, verify the current state:

```bash
python scripts/verify_migration.py --db path/to/database.db
```

Or using environment:

```bash
python scripts/verify_migration.py --env development
```

This will check:
- Checkpoints table structure
- Novel_snapshots table structure (including engine state fields from Task 1)
- Data integrity
- Engine state data format

### 2. Dry Run (Recommended)

Test the migration without modifying the database:

```bash
python scripts/migrate_checkpoints_to_snapshots.py --db path/to/database.db --dry-run
```

This will show what would be migrated without actually making changes.

### 3. Run Migration

Execute the actual migration:

```bash
python scripts/migrate_checkpoints_to_snapshots.py --db path/to/database.db
```

The script will:
1. Backup the checkpoints table to a timestamped file
2. Migrate all active checkpoints to novel_snapshots
3. Verify migration integrity
4. Generate statistics and report

### 4. Post-Migration Verification

After migration, run verification again:

```bash
python scripts/verify_migration.py --db path/to/database.db --output migration_report.json
```

This will verify:
- All active checkpoints were migrated
- No orphaned checkpoints exist
- Engine state data is valid JSON
- Data integrity is maintained

### 5. Testing

Run the integration test to verify the scripts work correctly:

```bash
python scripts/test_migration_scripts.py
```

This creates a temporary test database and runs through the complete migration flow.

## Safety Features

1. **Backup**: Creates a backup of the checkpoints table before migration
2. **Dry-run**: Test mode to preview changes
3. **Idempotent**: Can be run multiple times safely (skips already migrated checkpoints)
4. **Verification**: Built-in verification after migration
5. **Detailed logging**: Comprehensive logging of all operations

## Important Notes

⚠️ **DO NOT run these scripts on a production database without:**
1. Taking a full database backup
2. Running in dry-run mode first
3. Testing on a development database
4. Reviewing the verification output

⚠️ **These scripts are NOT part of automatic schema migrations**
- They must be run manually
- They are data migration scripts, not schema migrations
- Schema migrations are in `infrastructure/persistence/database/migrations/`

## Prerequisites

Before running migration:
1. Task 1 must be completed: `novel_snapshots` table must have engine state fields
2. Run `infrastructure/persistence/database/migrations/add_engine_state_to_snapshots.sql`

## Output Examples

### Migration Script Output

```
============================================================
开始 Checkpoint -> Snapshot 迁移
============================================================
已连接数据库: test.db
✓ novel_snapshots 表包含所有必需的引擎状态字段
开始备份 checkpoints 表到: checkpoints_backup_20260510_212922.db
✓ checkpoints 表已备份到: checkpoints_backup_20260510_212922.db
找到 2 条活跃 checkpoint 记录
开始迁移 2 条 checkpoint 记录...
[1/2] 迁移 checkpoint-1
[2/2] 迁移 checkpoint-2
✓ 事务已提交
============================================================
迁移统计:
  找到 checkpoint: 2
  成功迁移: 2
  跳过已存在: 0
  错误数量: 0
============================================================
✓ 迁移成功完成!
============================================================
```

### Verification Script Output

```
============================================================
验证报告总结
============================================================
checkpoints 表结构: ✓ 通过
novel_snapshots 表结构: ✓ 通过
数据完整性: ✓ 通过
引擎状态数据: ✓ 通过
============================================================
✓✓✓ 所有验证项目通过!
============================================================
```

## Troubleshooting

### Error: "novel_snapshots 表缺少引擎状态字段"

**Solution**: Run Task 1 migration first:
```bash
sqlite3 database.db < infrastructure/persistence/database/migrations/add_engine_state_to_snapshots.sql
```

### Error: "数据库文件不存在"

**Solution**: Specify database path with --db flag:
```bash
python scripts/migrate_checkpoints_to_snapshots.py --db path/to/database.db
```

### Warning: "发现孤立 checkpoint"

**Cause**: Checkpoints reference a story_id that doesn't exist in novels table.

**Solution**: Review the checkpoints and decide whether to:
- Delete orphaned checkpoints
- Create missing novel records
- Skip migration for orphaned checkpoints

## Next Steps

After successful migration:
1. Verify application functionality
2. Test Story Evolution Tab features
3. Monitor for any data inconsistencies
4. Eventually remove checkpoints table (in future cleanup task)
