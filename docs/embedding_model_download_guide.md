# 本地向量模型下载指南

PlotPilot 默认使用 OpenAI 兼容的云端嵌入服务。本地离线运行时可下载 `bge-small-zh-v1.5`；模型目录约占数百 MB，推理依赖请通过 `requirements-local.txt` 安装。

## 方案 1：使用 ModelScope（推荐）

ModelScope 是阿里云提供的国内模型托管平台，速度快且稳定。

### 下载模型
在仓库根目录执行：

```bash
pip install modelscope
python scripts/utils/download_model_via_modelscope.py
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

## 不下载模型：使用 OpenAI 兼容 API

这是默认且最轻量的配置（与 `.env.example` 一致）：
```bash
EMBEDDING_SERVICE=openai
EMBEDDING_API_KEY=your_key_here
# 可选：OPENAI_API_KEY=your_key_here
```

## 验证模型是否可用

运行下载/校验脚本：
```bash
python scripts/utils/download_embedding_model.py
```

脚本会下载缺失文件、加载模型并输出测试向量维度。成功后再启动后端；若切换了运行中的嵌入配置，需要重启后端守护进程。

典型成功输出包含：
```
✓ 模型下载成功！
✓ 生成向量维度: (3, 512)
```
