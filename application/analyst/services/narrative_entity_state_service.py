"""Narrative Entity State Service - combines base + events + replay."""

from typing import Optional
from domain.novel.repositories.entity_base_repository import EntityBaseRepository
from domain.novel.repositories.narrative_event_repository import NarrativeEventRepository
from domain.novel.services.narrative_state_replay import replay_entity_state


class NarrativeEntityStateService:
    """
    Application service for querying entity state at a specific chapter.

    Combines entity base attributes with narrative events and replays them
    to compute the dynamic state at any point in the story.
    """

    def __init__(
        self,
        entity_base_repository: EntityBaseRepository,
        narrative_event_repository: NarrativeEventRepository
    ):
        """
        Initialize the service with required repositories.

        Args:
            entity_base_repository: Repository for entity base data
            narrative_event_repository: Repository for narrative events
        """
        self.entity_base_repository = entity_base_repository
        self.narrative_event_repository = narrative_event_repository

    def get_state(self, entity_id: str, chapter: int) -> Optional[dict]:
        """
        Get entity state at a specific chapter by replaying events.

        This method:
        1. Retrieves the entity base attributes
        2. Fetches all events up to the specified chapter
        3. Replays events to compute the final state

        Args:
            entity_id: The entity ID to query
            chapter: The chapter number (inclusive) to compute state for

        Returns:
            Dictionary of entity attributes at the specified chapter,
            or None if the entity does not exist
        """
        # Step 1: Get entity base
        entity = self.entity_base_repository.get_by_id(entity_id)
        if entity is None:
            return None

        # Step 2: Get events up to chapter
        novel_id = entity["novel_id"]
        events = self.narrative_event_repository.list_up_to_chapter(novel_id, chapter)

        # Step 3: Replay events on base attributes
        base_attributes = entity["core_attributes"]
        final_state = replay_entity_state(base_attributes, events, entity_id)

        return final_state
