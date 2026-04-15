import logging
from ddgs import DDGS

logger = logging.getLogger(__name__)

class WebSearchTool:
    """轻量级的网络搜索工具，供 Agent 查证资料使用"""
    
    @staticmethod
    def search(query: str, max_results: int = 5) -> str:
        """
        搜索指定关键词并返回组合后的文本结果。
        失败时返回友好的错误提示而非崩溃。
        """
        logger.info(f"Executing web search for: '{query}'")
        try:
            results = []
            with DDGS() as ddgs:
                # 默认搜索中文网页
                for r in ddgs.text(query, region='wt-wt', max_results=max_results):
                    title = r.get("title", "")
                    body = r.get("body", "")
                    results.append(f"【{title}】\n{body}")
                    
            if not results:
                return "未能搜索到相关资料。"
                
            return "\n\n".join(results)
        except Exception as e:
            logger.error(f"Web search failed for query '{query}': {e}")
            return f"搜索失败（{e}）。"
