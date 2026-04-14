# infrastructure/ai/local_embedding_service.py

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

    def __init__(self, model_name: str = None, use_gpu: bool = True):
        """
        初始化本地 Embedding 服务

        Args:
            model_name: 模型名称或本地路径（如果为 None，从环境变量读取）
            use_gpu: 是否使用 GPU 加速（默认 True，自动检测）
        """
        try:
            from sentence_transformers import SentenceTransformer
            
            # 优先使用环境变量配置的本地路径
            if model_name is None:
                model_path = os.getenv("EMBEDDING_MODEL_PATH", "./.models/bge-small-zh-v1.5")
                # 转换为绝对路径
                model_path = str(Path(model_path).resolve())

                # 检查本地路径是否存在
                if os.path.exists(model_path):
                    model_name = model_path
                    logger.info(f"Using local model path: {model_path}")
                else:
                    # 如果本地路径不存在，报错而不是尝试下载
                    raise FileNotFoundError(f"Local model not found at {model_path}. Please download the model first.")

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
