import pytest

from domain.structure.narrative_progress import NarrativeProgressError, NarrativeProgressPolicy
from domain.structure.story_node import NodeType, StoryNode


def review(n, **extra):
    return {'id': 'goal', 'description': '关键转折兑现', 'status': 'resolved',
            'evidence_chapters': [n], 'evidence_revisions': {str(n): f'r{n}'}, **extra}


def book(counts=(2,2,2), budgets=(2,2,2), verified=True):
    nodes, revisions, number = [], {}, 0
    for index, (count, budget) in enumerate(zip(counts, budgets), 1):
        volume = StoryNode(f'v{index}', 'n', NodeType.VOLUME, index, f'卷{index}', index)
        act = StoryNode(f'a{index}', 'n', NodeType.ACT, index, f'幕{index}', index, parent_id=volume.id)
        nodes.extend([volume, act])
        for _ in range(count):
            number += 1
            # Reproduce PlotPilot: structural rows remain draft, manuscripts are committed separately.
            nodes.append(StoryNode(f'c{number}', 'n', NodeType.CHAPTER, number, '章', number, parent_id=act.id))
            revisions[number] = f'r{number}'
        volume.metadata['narrative_progress'] = {'chapter_budget': budget}
        if verified and count:
            volume.metadata['narrative_progress']['milestones'] = [review(number)]
    return nodes, revisions


def add_ending(nodes, n):
    volume = [node for node in nodes if node.node_type == NodeType.VOLUME][-1]
    volume.metadata['narrative_progress']['ending_review'] = {
        'reviewed_through_chapter': n,
        'reviewed_through_revision': f'r{n}',
        'core_conflict': review(n), 'character_outcomes': review(n), 'ending': review(n),
    }


def test_actual_250_chapter_failure_is_budget_finished_but_story_unfinished():
    nodes, revisions = book((250,0,0), (80,80,90), verified=False)
    report = NarrativeProgressPolicy(nodes,250,revisions).report()
    assert report['generation_finished'] is True
    assert report['story_finished'] is False
    assert report['volumes'][0]['written_chapters'] == list(range(1,251))
    assert any('超过' in i for i in report['issues'])
    assert any('尚无已完成正文' in i for i in report['issues'])


def test_budget_boundary_transitions_to_next_volume_after_evidence_review():
    nodes, revisions = book((2,0,0))
    destination = NarrativeProgressPolicy(nodes,6,revisions).next_volume('v1')
    assert destination.node.id == 'v2'
    assert destination.remaining == 2


def test_unverified_volume_exit_stops_even_when_all_mode_is_automatic():
    nodes, revisions = book((2,0,0), verified=False)
    with pytest.raises(NarrativeProgressError,match='必达剧情节点'):
        NarrativeProgressPolicy(nodes,6,revisions).next_volume('v1')


def test_planned_empty_chapters_do_not_consume_budget():
    nodes, revisions = book((1,0,0))
    nodes.append(StoryNode('planned','n',NodeType.CHAPTER,2,'空白目录',2,parent_id='a1'))
    assert NarrativeProgressPolicy(nodes,6,revisions).next_volume('v1').remaining == 1


def test_all_volumes_and_explicit_ending_are_required_for_completion():
    nodes, revisions = book()
    assert NarrativeProgressPolicy(nodes,6,revisions).report()['story_finished'] is False
    add_ending(nodes,6)
    assert NarrativeProgressPolicy(nodes,6,revisions).report()['story_finished'] is True


def test_rewritten_manuscript_invalidates_milestone_and_ending_evidence():
    nodes, revisions = book()
    add_ending(nodes,6)
    revisions[6] = 'rewritten'
    report = NarrativeProgressPolicy(nodes,6,revisions).report()
    assert report['story_finished'] is False
    assert any('证据已失效' in i for i in report['issues'])


@pytest.mark.parametrize('refs', [[251], [True], [], [0]])
def test_missing_future_or_boolean_evidence_cannot_close_a_goal(refs):
    nodes, revisions = book((2,0,0))
    nodes[0].metadata['narrative_progress']['milestones'][0]['evidence_chapters'] = refs
    assert NarrativeProgressPolicy(nodes,6,revisions).volumes[0].issues


def test_review_cannot_use_evidence_from_another_volume():
    nodes, revisions = book()
    nodes[0].metadata['narrative_progress']['milestones'] = [review(6)]
    assert NarrativeProgressPolicy(nodes,6,revisions).volumes[0].issues


def test_mismatched_total_budget_and_orphaned_manuscript_fail_closed():
    nodes, revisions = book((1,0,0), (1,1,1))
    revisions[4] = 'r4'
    policy = NarrativeProgressPolicy(nodes,6,revisions)
    with pytest.raises(NarrativeProgressError,match='预算之和'):
        policy.next_volume('v1')
    assert policy.unassigned == [4]


def test_existing_same_volume_plan_cannot_write_past_budget():
    nodes, revisions = book((2,0,0))
    nodes.append(StoryNode('c3','n',NodeType.CHAPTER,3,'错误的续章',3,parent_id='a1'))
    with pytest.raises(NarrativeProgressError,match='预算已用尽'):
        NarrativeProgressPolicy(nodes,6,revisions).ensure_can_write(3)


def test_next_volume_cannot_bypass_unreviewed_predecessor():
    nodes, revisions = book((2,0,0), verified=False)
    nodes.append(StoryNode('c3','n',NodeType.CHAPTER,3,'过早进入下一卷',3,parent_id='a2'))
    with pytest.raises(NarrativeProgressError,match='进入'):
        NarrativeProgressPolicy(nodes,6,revisions).ensure_can_write(3)


def test_volume_order_is_hierarchical_when_numbers_restart_in_each_part():
    p1 = StoryNode('p1','n',NodeType.PART,1,'部一',0)
    p2 = StoryNode('p2','n',NodeType.PART,2,'部二',1)
    v1 = StoryNode('v1','n',NodeType.VOLUME,1,'一部一卷',0,parent_id='p1')
    v2 = StoryNode('v2','n',NodeType.VOLUME,2,'一部二卷',1,parent_id='p1')
    v3 = StoryNode('v3','n',NodeType.VOLUME,1,'二部一卷',0,parent_id='p2')
    policy = NarrativeProgressPolicy([p2,v3,p1,v2,v1],9,{})
    assert [v.node.id for v in policy.volumes] == ['v1','v2','v3']


def test_missing_budget_is_explicitly_reported_as_estimate():
    nodes, revisions = book((0,0,0))
    for node in nodes:
        node.metadata.clear()
    policy = NarrativeProgressPolicy(nodes,250,revisions)
    assert sum(v.budget for v in policy.volumes) == 250
    assert all(v.estimated_budget for v in policy.volumes)
