"""Self-test for engine pipeline"""
import sys
print('Python:', sys.version)

# Test 1: Import pipeline module
print('\n=== Test 1: Import pipeline ===')
from engine.pipeline import BaseStoryPipeline, PipelineContext, PipelineResult, StepResult
print('PASS')

# Test 2: Import runtime
print('\n=== Test 2: Import runtime ===')
from engine.runtime import StoryPipelineRunner, PolicyValidator
print('PASS')

# Test 3: Import examples
print('\n=== Test 3: Import examples ===')
from engine.examples import ShortDramaPipeline, WuxiaPipeline
print('PASS')

# Test 4: PipelineContext
print('\n=== Test 4: PipelineContext ===')
ctx = PipelineContext(novel_id='test', chapter_number=5)
ctx.inject(novel_repository='repo', llm_service='llm')
assert ctx.novel_id == 'test'
assert ctx.get_dep('novel_repository') == 'repo'
assert ctx.is_fully_equipped()
print(f'PASS: fully_equipped={ctx.is_fully_equipped()}')

# Test 5: BaseStoryPipeline
print('\n=== Test 5: BaseStoryPipeline ===')
pipeline = BaseStoryPipeline.__new__(BaseStoryPipeline)
pipeline.__init__()
print(f'PASS: log={pipeline.get_step_log()}')

# Test 6: StoryPipelineRunner
print('\n=== Test 6: StoryPipelineRunner ===')
runner = StoryPipelineRunner(novel_repository='repo', llm_service='llm')
assert runner.novel_repository == 'repo'
print('PASS')

# Test 7: ShortDramaPipeline
print('\n=== Test 7: ShortDramaPipeline ===')
short = ShortDramaPipeline()
assert short.DEFAULT_TARGET_WORDS == 1500
assert short.VOICE_REWRITE_THRESHOLD == 0.5
print(f'PASS: target={short.DEFAULT_TARGET_WORDS}')

# Test 8: WuxiaPipeline
print('\n=== Test 8: WuxiaPipeline ===')
wuxia = WuxiaPipeline()
assert wuxia.DEFAULT_TARGET_WORDS == 3000
print(f'PASS: target={wuxia.DEFAULT_TARGET_WORDS}')

# Test 9: PolicyValidator
print('\n=== Test 9: PolicyValidator ===')
validator = PolicyValidator()
report = validator.advise(text='test')
assert report.passed
print(f'PASS: score={report.overall_score}')

# Test 10: PipelineResult
print('\n=== Test 10: PipelineResult ===')
result = PipelineResult(success=True, chapter_number=5, tension=75,
    step_status={'find_next_chapter': 'ok'})
d = result.to_dict()
assert d['tension'] == 75
print('PASS')

# Test 11: StepResult
print('\n=== Test 11: StepResult ===')
assert StepResult.ok().passed
assert not StepResult.fail('bad').passed
assert StepResult.skip_step().skip
print('PASS')

# Test 12: Inheritance
print('\n=== Test 12: Inheritance ===')
assert issubclass(StoryPipelineRunner, BaseStoryPipeline)
assert issubclass(ShortDramaPipeline, BaseStoryPipeline)
assert issubclass(WuxiaPipeline, BaseStoryPipeline)
print('PASS')

# Test 13: _make_context
print('\n=== Test 13: _make_context ===')
runner2 = StoryPipelineRunner(novel_repository='r', llm_service='l',
    context_builder='cb', chapter_repository='cr')
ctx2 = runner2._make_context('n-123', chapter_number=3)
assert ctx2.novel_id == 'n-123'
assert ctx2.novel_repository == 'r'
assert ctx2.llm_service == 'l'
print(f'PASS: fully_equipped={ctx2.is_fully_equipped()}')

# Test 14: SPI deprecation warning
print('\n=== Test 14: SPI deprecation ===')
import warnings
with warnings.catch_warnings(record=True) as w:
    warnings.simplefilter("always")
    import engine.spi
    assert len(w) > 0 and issubclass(w[0].category, DeprecationWarning)
print('PASS: SPI deprecation warning works')

print('\n=== All 14 tests passed! ===')
