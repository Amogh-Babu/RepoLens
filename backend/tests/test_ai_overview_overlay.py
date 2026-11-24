"""AI overview enhancement must stay cache-only and preserve deterministic order."""

from repolens.api.app import _apply_cached_summaries


def test_cached_ai_text_replaces_only_matching_entries() -> None:
    overview = {
        'entryPoints': [
            {'path': 'app.py', 'summary': 'Static app.'},
            {'path': 'other.py', 'summary': 'Static other.'},
        ],
        'coreFiles': [{'path': 'app.py', 'summary': 'Static app.'}],
        'tour': [{'path': 'app.py', 'summary': 'Static app.'}],
    }
    _apply_cached_summaries(overview, {'app.py': 'Explains the startup flow.'})
    assert [x['path'] for x in overview['entryPoints']] == ['app.py', 'other.py']
    assert overview['entryPoints'][0]['summary'] == 'Explains the startup flow.'
    assert overview['entryPoints'][0]['summarySource'] == 'ai'
    assert overview['entryPoints'][1]['summary'] == 'Static other.'
    assert overview['entryPoints'][1]['summarySource'] == 'static'
    assert overview['coreFiles'][0]['summarySource'] == 'ai'
    assert overview['tour'][0]['summarySource'] == 'ai'


def test_no_cached_ai_text_preserves_deterministic_descriptions() -> None:
    overview = {'entryPoints': [{'path': 'app.py', 'summary': 'Static app.'}], 'coreFiles': [], 'tour': []}
    _apply_cached_summaries(overview, {})
    assert overview['entryPoints'][0] == {
        'path': 'app.py', 'summary': 'Static app.', 'summarySource': 'static',
    }
