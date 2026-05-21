"""StoryPipeline 可观测 telemetry 常量单测."""

from engine.pipeline.telemetry import STORY_PIPELINE_WAVE_TOTAL, story_pipeline_wave_meta


def test_wave_meta_boundary():
    assert story_pipeline_wave_meta(0) is None
    assert story_pipeline_wave_meta(11) is None


def test_wave_generate():
    m = story_pipeline_wave_meta(4)
    assert m is not None
    assert m["story_pipeline_wave_index"] == 4
    assert m["story_pipeline_wave_id"] == "generate"
    assert m["story_pipeline_wave_total"] == STORY_PIPELINE_WAVE_TOTAL
