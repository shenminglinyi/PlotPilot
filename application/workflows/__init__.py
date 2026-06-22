"""工作流层"""

__all__ = ["AutoNovelGenerationWorkflow"]


def __getattr__(name):
    if name == "AutoNovelGenerationWorkflow":
        from application.workflows.auto_novel_generation_workflow import AutoNovelGenerationWorkflow

        return AutoNovelGenerationWorkflow
    raise AttributeError(name)
