# PR: 添加 LLM 设置页面和 Ark/DashScope 支持

## 功能概述

本次 PR 为 PlotPilot 项目添加了完整的 LLM 大模型配置管理功能，支持 Anthropic Claude 和阿里 DashScope 两个提供商，并提供了一个直观的 Web 界面来管理所有 LLM 参数。

## 主要功能

### 1. 新增 LLM 设置页面

**文件**: `frontend/src/views/LLMSettings.vue`

- 提供商选择：Anthropic Claude / 阿里 DashScope / Mock 模式
- API Key 配置：密码输入框，支持显示/隐藏
- Base URL 配置：可自定义 API 地址
- 模型名称：纯文本输入，支持任意模型名称
- Max Tokens：滑块调节 (256-8192)
- Temperature：滑块调节 (0-2)
- Timeout：输入框设置超时时间 (10-600秒)
- 保存设置：保存到 `.env` 文件
- 测试连接：实时测试 API 连接状态

### 2. 后端 API 支持

**文件**: `interfaces/api/v1/core/llm_settings.py`

新增三个 API 端点：
- `GET /api/v1/llm-settings` - 获取当前 LLM 配置
- `POST /api/v1/llm-settings` - 保存 LLM 配置到 `.env` 文件
- `POST /api/v1/llm-settings/test` - 测试 LLM 连接

### 3. Ark/DashScope 提供商支持

**文件**: `infrastructure/ai/providers/ark_provider.py`

- 实现 OpenAI 兼容格式的 Ark/DashScope API 客户端
- 支持同步和异步文本生成
- 支持流式生成
- 自动处理 Claude 模型名称转换（当使用 Ark 时自动替换为 Ark 模型）
- 修复 OpenAI 客户端 `proxies` 参数兼容性问题

### 4. 自动提供商选择

**文件**: `infrastructure/ai/llm_client.py`

自动检测环境变量并选择合适的提供商：
1. `ANTHROPIC_API_KEY` → AnthropicProvider
2. `ARK_API_KEY` → ArkProvider
3. 无 API Key → MockProvider

### 5. 菜单入口

**文件**: `frontend/src/components/stats/StatsSidebar.vue`

- 在左侧边栏新增 "设置" 区域
- 添加 "LLM 模型" 按钮，点击跳转到设置页面

### 6. 路由配置

**文件**: `frontend/src/router/index.ts`

- 添加 `/settings/llm` 路由

**文件**: `interfaces/main.py`

- 注册 LLM 设置 API 路由

## 技术细节

### 模型名称处理

ArkProvider 会自动处理模型名称：
```python
# 如果 config.model 是 Claude 模型，则使用 DEFAULT_MODEL
model = config.model
if not model or "claude" in model.lower():
    model = DEFAULT_MODEL  # 从环境变量 ARK_MODEL 读取
```

### 环境变量持久化

设置保存时会：
1. 读取现有的 `.env` 文件
2. 更新 LLM 相关配置
3. 按提供商分组写入文件
4. 同步更新当前进程的环境变量

### 日志查看工具

**文件**: `view_logs.py`

提供实时日志查看功能，方便调试 LLM 生成过程。

## 使用说明

1. 打开前端页面，点击左侧 "LLM 模型" 按钮
2. 选择提供商（阿里 DashScope 或 Anthropic Claude）
3. 填写 API Key 和其他参数
4. 点击 "测试连接" 验证配置
5. 点击 "保存设置" 保存配置

配置会立即保存到 `.env` 文件并生效。

## 兼容性

- 支持阿里 DashScope 所有模型（qwen-turbo, qwen-max, qwen-plus 等）
- 支持 Anthropic Claude 所有模型
- 支持自定义模型名称
- 向后兼容：无配置时自动使用 Mock 模式

## 测试

- [x] 后端 API 测试通过
- [x] 前端页面正常显示
- [x] 配置保存功能正常
- [x] LLM 连接测试正常
- [x] 世界观生成功能正常

## 相关文件变更

```
interfaces/api/v1/core/llm_settings.py          # 新增
interfaces/main.py                               # 修改：注册路由
infrastructure/ai/providers/ark_provider.py      # 修改：模型名称处理
frontend/src/views/LLMSettings.vue               # 新增
frontend/src/router/index.ts                     # 修改：添加路由
frontend/src/components/stats/StatsSidebar.vue   # 修改：添加菜单入口
view_logs.py                                     # 新增（调试工具）
```

## 注意事项

1. 后端服务需要重启才能加载新的 API 路由
2. 模型名称现在完全由用户自定义输入，不再提供预设选项
3. 建议先测试连接再保存设置
