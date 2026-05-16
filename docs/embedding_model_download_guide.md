# 手动下载本地向量模型指南

由于网络问题无法直接从 HuggingFace 下载，提供以下手动下载方案：

## 方案 1：使用 ModelScope（推荐）

ModelScope 是阿里云提供的国内模型托管平台，速度快且稳定。

### 安装 ModelScope
```bash
pip install modelscope
```

### 下载模型
```python
from modelscope import snapshot_download

# 下载到默认缓存目录
model_dir = snapshot_download('AI-ModelScope/bge-small-zh-v1.5')
print(f"模型已下载到: {model_dir}")
```

### 使用下载的模型
在 `.env` 中配置：
```bash
EMBEDDING_SERVICE=local
EMBEDDING_MODEL_PATH=/path/to/downloaded/model
```

## 方案 2：使用 HF-Mirror（国内镜像）

### 设置环境变量
```bash
# Windows CMD
set HF_ENDPOINT=https://hf-mirror.com

# Windows PowerShell
$env:HF_ENDPOINT="https://hf-mirror.com"

# Linux/Mac
export HF_ENDPOINT=https://hf-mirror.com
```

### 下载模型
```bash
python scripts/utils/download_embedding_model.py
```

## 方案 3：手动下载文件

访问以下链接手动下载模型文件：
- https://hf-mirror.com/BAAI/bge-small-zh-v1.5

需要下载的文件：
- config.json
- pytorch_model.bin
- tokenizer_config.json
- vocab.txt
- special_tokens_map.json

将文件放到：`./.models/bge-small-zh-v1.5/`（与根目录 `.env.example` 中 `EMBEDDING_MODEL_PATH` 默认值一致；亦可使用任意绝对路径）

然后配置：
```bash
EMBEDDING_MODEL_PATH=./.models/bge-small-zh-v1.5
```

## 方案 4：暂时使用 OpenAI API

如果急需使用，可以先配置云端嵌入（与 `.env.example` 一致，二选一或都填由实现回退）：
```bash
EMBEDDING_SERVICE=openai
EMBEDDING_API_KEY=your_key_here
# 可选：OPENAI_API_KEY=your_key_here
```

## 当前状态

- 本地 embedding 与 OpenAI 兼容云端模式由 `EMBEDDING_SERVICE` 切换（见 `.env.example`）。
- 模型文件需按上文下载到 `EMBEDDING_MODEL_PATH` 所指目录后启动后端。

## 验证模型是否可用

运行下载/校验脚本：
```bash
python scripts/utils/download_embedding_model.py
```

如果成功，会显示：
```
✓ 模型下载成功！
✓ 生成向量维度: (3, 512)
```
