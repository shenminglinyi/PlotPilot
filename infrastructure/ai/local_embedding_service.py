# infrastructure/ai/local_embedding_service.py

# 必须在任何 HuggingFace/SentenceTransformer 导入前设置离线模式
import os
os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['TRANSFORMERS_OFFLINE'] = '1'
os.environ['HF_DATASETS_OFFLINE'] = '1'
if os.getenv('DISABLE_SSL_VERIFY', 'false').lower() == 'true':
    os.environ['CURL_CA_BUNDLE'] = ''
    os.environ['REQUESTS_CA_BUNDLE'] = ''
    import logging as _l
    _l.getLogger(__name__).warning("SSL certificate verification is DISABLED via DISABLE_SSL_VERIFY=true")

from typing import List
import logging
import torch
from pathlib import Path
from domain.ai.services.embedding_service import EmbeddingService

logger = logging.getLogger(__name__)


class LocalEmbeddingService(EmbeddingService):
    """本地 Embedding 服务（基于 sentence-transformers）

    使用 BAAI/bge-small-zh-v1.5 模型进行中文文本向量化。
    支持 GPU 加速。
    优先使用本地模型路径，避免从 HuggingFace 下载。
    """

    def __init__(self, model_name: str = None, use_gpu: bool = True, allow_remote: bool = False):
        """
        初始化本地 Embedding 服务

        Args:
            model_name: 模型名称或本地路径（如果为 None，从环境变量读取）
            use_gpu: 是否使用 GPU 加速（默认 True，自动检测）
            allow_remote: 当本地不存在时是否允许联网拉取远端模型（默认 False）
        """
        try:
            from sentence_transformers import SentenceTransformer
            
            # 优先使用显式参数；其次使用环境变量
            if model_name is None:
                # 兼容历史变量 EMBEDDING_MODEL_PATH，同时支持更语义化的 EMBEDDING_LOCAL_MODEL
                model_name = (
                    os.getenv("EMBEDDING_MODEL_PATH")
                    or os.getenv("EMBEDDING_LOCAL_MODEL")
                    or "./.models/bge-small-zh-v1.5"
                )

            # 检测设备
            if use_gpu and torch.cuda.is_available():
                device = 'cuda'
                logger.info(f"Using GPU: {torch.cuda.get_device_name(0)}")
            else:
                device = 'cpu'
                logger.info("Using CPU")

            # 路径存在则视为本地目录；否则按模型名处理（是否允许联网由 allow_remote 控制）
            local_files_only = True
            path_candidate = Path(model_name).resolve()
            if path_candidate.exists():
                model_name = str(path_candidate)
                logger.info(f"Using local model path: {model_name}")
            else:
                local_files_only = not allow_remote
                if local_files_only:
                    logger.info(
                        "Using model id in local-only mode: %s (set EMBEDDING_ALLOW_REMOTE=true to allow download)",
                        model_name,
                    )
                else:
                    logger.info(f"Using remote-capable model id: {model_name}")
            # 加载模型 - 使用 trust_remote_code=False 避免执行远程代码
            # 使用 local_files_only=True 确保只从本地加载
            self.model = SentenceTransformer(
                model_name,
                device=device,
                trust_remote_code=False,
                local_files_only=True,
            )
            _dim_fn = getattr(self.model, "get_embedding_dimension", None)
            if callable(_dim_fn):
                self._dimension = _dim_fn()
            else:
                self._dimension = self.model.get_sentence_embedding_dimension()
            self.device = device

            logger.info(f"Loaded local embedding model: {model_name}, dimension: {self._dimension}, device: {device}")
        except Exception as e:
            logger.error(f"Failed to load local embedding model: {e}")
            raise

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
