## 变更类型

<!-- 勾选适用项 -->
- [ ] `feat` 新功能
- [ ] `fix` Bug 修复
- [ ] `refactor` 重构（不影响功能）
- [ ] `perf` 性能优化
- [ ] `docs` 文档
- [ ] `chore` 构建/工具链

---

## 变更说明

<!-- 用 1-3 句话说明：做了什么、为什么做、解决了什么问题 -->

---

## 架构影响

<!-- 新增文件请说明放在哪一层，为什么放这里 -->
- 涉及层级：`domain` / `application` / `infrastructure` / `interfaces` / `frontend` / `scripts`（删除不适用项）
- 是否新增数据库表/字段：是 / 否（如是，请附 migration 说明）
- 是否修改现有 API 契约（路径/字段/类型变更）：是 / 否

---

## 测试

```bash
# 后端单测（必填，粘贴你实际跑的命令和结果摘要）
pytest tests/unit/... -q

# 前端构建（如改了前端必填）
cd frontend && npm run build
```

- [ ] 新增/修改的逻辑有对应单测
- [ ] 本地后端启动正常（`python -m uvicorn ...`）
- [ ] 本地前端启动正常（`npm run dev`）

---

## 风险说明

<!-- 没有风险也请写"无" -->
- 潜在风险：
- 回滚方式：
