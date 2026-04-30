"""写作手法知识库仓储接口。"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from domain.style_bible.entities import (
    StyleProfile,
    StyleSample,
    StyleSampleChunk,
    StyleTechniqueCard,
)


class StyleBibleRepository(ABC):
    """写作手法知识库仓储。"""

    @abstractmethod
    def save_sample(
        self,
        sample: StyleSample,
        chunks: list[StyleSampleChunk],
    ) -> StyleSample:
        pass

    @abstractmethod
    def list_samples(
        self,
        novel_id: Optional[str] = None,
        profile_id: Optional[str] = None,
    ) -> list[StyleSample]:
        pass

    @abstractmethod
    def get_sample(self, sample_id: str) -> Optional[StyleSample]:
        pass

    @abstractmethod
    def save_profile(self, profile: StyleProfile) -> StyleProfile:
        pass

    @abstractmethod
    def list_profiles(
        self,
        novel_id: Optional[str] = None,
        status: Optional[str] = None,
    ) -> list[StyleProfile]:
        pass

    @abstractmethod
    def get_profile(self, profile_id: str) -> Optional[StyleProfile]:
        pass

    @abstractmethod
    def save_technique_cards(
        self,
        profile_id: str,
        cards: list[StyleTechniqueCard],
    ) -> list[StyleTechniqueCard]:
        pass

    @abstractmethod
    def list_technique_cards(
        self,
        profile_id: str,
        enabled: Optional[bool] = None,
    ) -> list[StyleTechniqueCard]:
        pass

    @abstractmethod
    def get_technique_card(self, card_id: str) -> Optional[StyleTechniqueCard]:
        pass

    @abstractmethod
    def update_technique_card(self, card: StyleTechniqueCard) -> StyleTechniqueCard:
        pass
