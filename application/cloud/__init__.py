"""application.cloud — kernel-side cloud connection use cases.

连接器是内核唯一上云通道：广场+社交（浏览/妙/批注/追更/飞鸽/名帖/
灵感签/落笔事件）。纯客户端形态，零判定逻辑、零社交数据落内核。
"""
from application.cloud.connection_service import CloudConnectionService

__all__ = ["CloudConnectionService"]
