import json
import os

import pytest

from scripts.verify_narrative_progress import verify_test_copy


def marker(copy, source, **extra):
    payload={'purpose':'plotpilot-narrative-progress-test-copy','copy_db':str(copy),
             'source_db':str(source),'novel_id':'fixture',**extra}
    (copy.parent/'narrative-test-copy.json').write_text(json.dumps(payload),encoding='utf-8')


def files(tmp_path):
    production=tmp_path/'production';production.mkdir()
    test=tmp_path/'sandbox';test.mkdir()
    source=production/'plotpilot.db';source.write_bytes(b'original')
    copy=test/'plotpilot.db';copy.write_bytes(b'copy')
    return source,copy


def test_accepts_explicit_separate_test_copy(tmp_path):
    source,copy=files(tmp_path);marker(copy,source)
    assert verify_test_copy(copy)['novel_id']=='fixture'


def test_refuses_original_database_even_with_marker(tmp_path):
    source,_=files(tmp_path);marker(source,source)
    with pytest.raises(ValueError,match='original'):
        verify_test_copy(source)


def test_refuses_hard_link_to_production_database(tmp_path):
    source,copy=files(tmp_path);copy.unlink();os.link(source,copy);marker(copy,source)
    with pytest.raises(ValueError,match='original'):
        verify_test_copy(copy)


def test_refuses_wrong_marker_or_unmarked_database(tmp_path):
    source,copy=files(tmp_path)
    with pytest.raises(FileNotFoundError):verify_test_copy(copy)
    marker(copy,source,purpose='not-a-test')
    with pytest.raises(ValueError,match='marked'):verify_test_copy(copy)
