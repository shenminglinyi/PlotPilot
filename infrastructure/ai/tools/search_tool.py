import logging
from ddgs.ddgs import DDGS
import time

logger = logging.getLogger(__name__)

class WebSearchTool:
    """轻量级的网络搜索工具，供 Agent 查证资料使用"""
    
    @staticmethod
    def search(query: str, max_results: int = 5) -> str:
        """
        搜索指定关键词并返回组合后的文本结果。
        失败时返回友好的错误提示而非崩溃。
        """
        start = time.time()
        logger.info(f"Executing web search for: '{query}'")
        try:
            results = WebSearchTool.search_raw(query, max_results=max_results)
            if not results:
                return "未能搜索到相关资料。"

            parts = []
            for r in results:
                title = r.get("title", "")
                href = r.get("href", "")
                body = r.get("body", "")
                if href:
                    parts.append(f"【{title}】\nURL: {href}\n{body}")
                else:
                    parts.append(f"【{title}】\n{body}")

            logger.info(f"Web search done for: '{query}', results={len(results)}, elapsed={time.time() - start:.2f}s")
            return "\n\n".join(parts)
        except Exception as e:
            logger.error(f"Web search failed for query '{query}' (elapsed={time.time() - start:.2f}s): {e}")
            return f"搜索失败（{e}）。"

    @staticmethod
    def search_raw(query: str, max_results: int = 5) -> list[dict]:
        start = time.time()
        logger.info(f"Executing web search(raw) for: '{query}'")
        try:
            results: list[dict] = []
            with DDGS(timeout=8) as ddgs:
                # 默认搜索中文网页
                for r in ddgs.text(query, region='wt-wt', max_results=max_results):
                    if isinstance(r, dict):
                        results.append(
                            {
                                "title": r.get("title", "") or "",
                                "href": r.get("href", "") or "",
                                "body": r.get("body", "") or "",
                            }
                        )
            logger.info(f"Web search(raw) done for: '{query}', results={len(results)}, elapsed={time.time() - start:.2f}s")
            return results
        except Exception as e:
            logger.error(f"Web search(raw) failed for query '{query}' (elapsed={time.time() - start:.2f}s): {e}")
            return []
