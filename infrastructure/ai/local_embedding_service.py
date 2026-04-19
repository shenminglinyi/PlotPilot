# infrastructure/ai/local_embedding_service.py
"""
本地 Embedding 服务（基于 sentence-transformers）

⚠️ 重要：本模块采用懒加载（Lazy Import）策略。
  sentence-transformers / torch / faiss 均不在模块顶层导入，
  而是在 __init__ 中按需导入。这样即使未安装 requirements-local.txt
  的用户，import 本模块也不会崩溃。

本地 sentence-transformers 向量模型（具体权重路径或 HuggingFace ID 由配置提供）。
支持 GPU 加速。优先使用本地目录，避免联网下载。
"""

import os
from typing import List

# 设置离线模式（不触发网络请求）
os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['TRANSFORMERS_OFFLINE'] = '1'
os.environ['HF_DATASETS_OFFLINE'] = '1'
if os.getenv('DISABLE_SSL_VERIFY', 'false').lower() == 'true':
    os.environ['CURL_CA_BUNDLE'] = ''
    os.environ['REQUESTS_CA_BUNDLE'] = ''
    import logging as _l
    _l.getLogger(__name__).warning("SSL certificate verification is DISABLED via DISABLE_SSL_VERIFY=true")

import logging
from pathlib import Path
from domain.ai.services.embedding_service import EmbeddingService

logger = logging.getLogger(__name__)


class LocalEmbeddingService(EmbeddingService):
    """本地 Embedding 服务（基于 sentence-transformers）。

    所有重依赖（torch, sentence_transformers）均在 __init__ 中懒加载，
    确保未安装 local 扩展包时 import 不崩溃。
    """

    def __init__(self, model_name: str = None, use_gpu: bool = True):
        """
        初始化本地 Embedding 服务

        Args:
            model_name: 模型名称或本地路径（如果为 None，从环境变量读取）
            use_gpu: 是否使用 GPU 加速（默认 True，自动检测）

        Raises:
            ImportError: 未安装 sentence-transformers / torch 等依赖
            FileNotFoundError: 本地模型文件不存在
        """
        # ════════════════════════════════════════════
        # 懒加载：仅在实例化时才导入重依赖
        # ════════════════════════════════════════════
        try:
            import torch
            from sentence_transformers import SentenceTransformer
        except ImportError as e:
            raise ImportError(
                "检测到您正在尝试使用本地向量模型（LocalEmbedding），"
                "但缺少必要的依赖包！\n\n"
                "请选择以下任一方式解决：\n"
                "  方式 A — 安装扩展依赖（~2GB）：\n"
                "    pip install -r requirements-local.txt\n\n"
                "  方式 B — 切换到 OpenAI API 模式（推荐，无需下载大包）：\n"
                "    在设置页面将「嵌入模式」改为「openai」,\n"
                "    并填写 EMBEDDING_API_KEY 和 EMBEDDING_BASE_URL\n\n"
                f"原始错误: {e}"
            ) from e

        # 解析模型路径：参数优先，否则读环境变量；不在代码中写死具体模型 ID
        if model_name is None or not str(model_name).strip():
            model_path = (os.getenv("EMBEDDING_MODEL_PATH") or "").strip()
        else:
            model_path = str(model_name).strip()

        if not model_path:
            raise ValueError(
                "未配置本地嵌入模型：请在嵌入设置中填写 model_path，或设置环境变量 EMBEDDING_MODEL_PATH。"
            )

        # 判断是否为 HuggingFace 模型 ID（含 "/" 的短字符串且非本机绝对路径）
        _original_model_name = model_path
        _is_hf_model_id = "/" in model_path and not Path(model_path).is_absolute()

        # 将路径转为绝对路径（相对路径基于项目根目录）
        _resolved = Path(model_path)
        if not _resolved.is_absolute():
            _resolved = (Path(__file__).parent.parent.parent / model_path).resolve()

        if _resolved.exists():
            model_name = str(_resolved)
            logger.info(f"Using local model path: {model_name}")
        else:
            # 尝试将 HuggingFace model-id 映射到 .models/<basename>
            _basename = Path(model_path).name  # e.g. "bge-small-zh-v1.5"
            _fallback = (Path(__file__).parent.parent.parent / ".models" / _basename).resolve()
            if _fallback.exists():
                model_name = str(_fallback)
                logger.info(f"Using local model path (auto-resolved): {model_name}")
            elif _is_hf_model_id:
                # 看起来像 HuggingFace 模型 ID，保留原始值让 SentenceTransformer 从缓存加载
                model_name = _original_model_name
                logger.info(f"Using HuggingFace model ID (cached): {model_name}")
            else:
                raise FileNotFoundError(
                    f"Local model not found at '{_resolved}' or '{_fallback}'.\n\n"
                    f"请先下载模型文件到该路径，或运行:\n"
                    f"  python scripts/utils/download_embedding_model.py\n\n"
                    f"或者切换到 OpenAI API 模式以跳过本地模型。"
                )

        # 检测设备
        if use_gpu and torch.cuda.is_available():
            device = 'cuda'
            logger.info(f"Using GPU: {torch.cuda.get_device_name(0)}")
        else:
            device = 'cpu'
            logger.info("Using CPU")

        # 加载模型 - 使用 trust_remote_code=False 避免执行远程代码
        # 使用 local_files_only=True 确保只从本地加载
        self.model = SentenceTransformer(
            model_name,
            device=device,
            trust_remote_code=False,
            local_files_only=True,
        )
        self._dimension = self.model.get_sentence_embedding_dimension()
        self.device = device

        logger.info(f"Loaded local embedding model: {model_name}, dimension: {self._dimension}, device: {device}")

    async def embed(self, text: str) -> List[float]:
        """
        将文本转换为向量

        Args:
            text: 输入文本

        Returns:
            向量表示（List[float]）
        """
        try:
            # sentence-transformers 的 encode 是同步的
            embedding = self.model.encode(text, convert_to_numpy=True)
            return embedding.tolist()
        except Exception as e:
            raise Exception(f"Failed to generate embedding: {str(e)}")

    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """
        批量将文本转换为向量（GPU 加速时性能提升明显）

        Args:
            texts: 输入文本列表

        Returns:
            向量列表
        """
        try:
            # 批量处理在 GPU 上效率更高
            embeddings = self.model.encode(
                texts,
                convert_to_numpy=True,
                batch_size=32,  # GPU 可以使用更大的 batch size
                show_progress_bar=len(texts) > 100  # 大批量时显示进度
            )
            return embeddings.tolist()
        except Exception as e:
            raise Exception(f"Failed to generate batch embeddings: {str(e)}")

    def get_dimension(self) -> int:
        """
        获取嵌入向量的维度

        Returns:
            向量维度（整数）
        """
        return self._dimension
