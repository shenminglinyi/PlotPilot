from domain.knowledge.chapter_summary import ChapterSummary
from domain.knowledge.knowledge_triple import KnowledgeTriple
from domain.knowledge.story_knowledge import StoryKnowledge
from application.world.services.knowledge_service import KnowledgeService


class FakeKnowledgeRepository:
    def __init__(self, stored=None):
        self.stored = stored
        self.saved = []

    def get_by_novel_id(self, novel_id: str):
        return self.stored

    def save(self, knowledge: StoryKnowledge):
        self.saved.append(knowledge)
        self.stored = knowledge


class FakePrimaryMemory:
    def __init__(self, knowledge):
        self.knowledge = knowledge

    def load_knowledge(self, novel_id: str):
        assert novel_id == self.knowledge.novel_id
        return self.knowledge


def test_knowledge_service_prefers_obsidian_primary_memory_and_caches_it():
    sqlite_knowledge = StoryKnowledge(
        novel_id="novel-primary",
        premise_lock="旧知识库设定",
        facts=[
            KnowledgeTriple(
                id="sqlite-fact",
                subject="旧角色",
                predicate="旧关系",
                object="旧对象",
            )
        ],
    )
    obsidian_knowledge = StoryKnowledge(
        novel_id="novel-primary",
        premise_lock="Obsidian 主记忆设定",
        chapters=[ChapterSummary(chapter_id=1, summary="Obsidian 章节记忆")],
        facts=[
            KnowledgeTriple(
                id="obsidian-fact",
                subject="林夜",
                predicate="敌对",
                object="黑塔会",
                source_type="obsidian_primary",
            )
        ],
    )
    repo = FakeKnowledgeRepository(sqlite_knowledge)
    service = KnowledgeService(repo, primary_memory_service=FakePrimaryMemory(obsidian_knowledge))

    knowledge = service.get_knowledge("novel-primary")

    assert knowledge.premise_lock == "Obsidian 主记忆设定"
    assert knowledge.facts[0].id == "obsidian-fact"
    assert knowledge.chapters[0].summary == "Obsidian 章节记忆"
    assert repo.saved[-1] is obsidian_knowledge
