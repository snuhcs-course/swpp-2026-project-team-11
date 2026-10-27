"""Regression tests for task evidence, native usage formats and guarded Sheets writes."""
import contextlib
from copy import deepcopy
import io
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from tools import harness, worklog, sheets

START, END, T = '2026-10-27T00:00:00Z', '2026-10-27T01:00:00Z', '2026-10-27T00:10:00Z'
HEADERS = ['Iter', 'ID', 'DESCRIPTION', 'HUMAN\nHOURS', 'AGENT\nHOURS', 'TOKENS USAGE',
           'STATUS', 'ACTUAL\nEND DATE', 'FINAL COMMIT ID', 'Alice']


def snapshot():
    return {'spreadsheet_id': 'test-id', 'sheet_id': 7, 'sheet_title': 'Renamed schedule',
            'values': [HEADERS, [3, 'P3', 'Harness', '', '', '', '', '', '', 'Worker']],
            'allowed_values': {'6': ['Completed', 'Hold']}}


def counts(i, o, cached=0):
    return dict(input_tokens=i, output_tokens=o, cached_input_tokens=cached, reasoning_output_tokens=o)


def token(total, last, at=T):
    return dict(timestamp=at, type='event_msg', payload=dict(type='token_count',
                info=dict(total_token_usage=total, last_token_usage=last)))


def source(root, tool, events, name='session'):
    path = root / (name + '.jsonl')
    meta = dict(type='session_meta', payload={'id': 's1'}) if tool == 'codex' else {'sessionId': 's1'}
    path.write_text('\n'.join(json.dumps(e) for e in [meta, *events]) + '\n')
    return dict(tool=tool, path=str(path), session_id='s1', since=START, until=END)


def cli(root, *args):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = harness.main(args, root)
    return code, json.loads(out.getvalue() or err.getvalue())


@pytest.fixture
def project(tmp_path):
    subprocess.run(['git', 'init', '-q', str(tmp_path)], check=True)
    (tmp_path / 'README.md').write_text('Test repository\n')
    subprocess.run(['git', '-C', str(tmp_path), 'add', '.'], check=True)
    subprocess.run(['git', '-C', str(tmp_path), '-c', 'user.name=Test', '-c', 'user.email=test@example.invalid',
                    'commit', '-qm', 'initial'], check=True)
    (tmp_path / '.env.harness').write_text('METCHU_SCHEDULE_URL=https://docs.google.com/spreadsheets/d/test-id/edit#gid=7\n')
    return SimpleNamespace(root=tmp_path, task=worklog.task(tmp_path, 'i3-P3', 'Alice'))


def test_task_resume_notes_and_explicit_fields(project):
    for _ in range(2):
        assert cli(project.root, 'task', '--note', 'Tests passed', '--ref', 'saved output')[0] == 0
    value = worklog.task(project.root)
    assert len(value['notes']) == 1 and value['fields'] == {}
    with pytest.raises(ValueError):
        worklog.task(project.root, 'i3-P3', 'Bob')
    assert cli(project.root, 'task', '--set', 'human_hours=0.5', '--set', 'commit=HEAD')[0] == 0
    assert len(worklog.task(project.root)['fields']['commit']) == 40


@pytest.mark.parametrize('identifier', ['../secret', 'P3', 'i0-P2', 'i3-p3'])
def test_invalid_id(project, identifier):
    with pytest.raises(ValueError):
        worklog.task(project.root, identifier, 'Alice')


@pytest.mark.parametrize('hours', ['nan', 'inf', '-1'])
def test_invalid_hours(project, hours):
    with pytest.raises(ValueError):
        worklog.task(project.root, fields={'human_hours': hours})


def test_private_output_and_gitignore(project):
    root = project.root
    (root / '.gitignore').write_text((harness.ROOT / '.gitignore').read_text())
    path = root / '.harness/google-token.json'
    worklog.write_json(path, {'synthetic': True})
    if __import__('os').name != 'nt':
        assert path.stat().st_mode & 0o777 == 0o600
    for name in ('.harness/google-token.json', '.harness/tasks/i3-P3.json', '.env.harness'):
        assert subprocess.run(['git', '-C', str(root), 'check-ignore', '-q', name]).returncode == 0
    assert subprocess.run(['git', '-C', str(root), 'check-ignore', '-q', '.env.harness.example']).returncode != 0


def test_codex_inherited_totals_duplicates_and_subsets(project):
    s = source(project.root, 'codex', [token(counts(1000000, 50000), counts(100, 10)),
        token(counts(1000100, 50020, 80), counts(100, 20, 80), '2026-10-27T00:11:00Z'),
        token(counts(1000100, 50020, 80), counts(100, 20, 80), '2026-10-27T00:12:00Z')])
    result = worklog.collect([s, s])
    assert (result['total_tokens'], result['cached_input_tokens']) == (230, 80)


def test_codex_interval_and_reset(project):
    s = source(project.root, 'codex', [token(counts(1000, 50), counts(1000, 50), '2026-10-26T23:59:00Z'),
        token(counts(1100, 60), counts(100, 10)), token(counts(2000, 70), counts(900, 10), END)])
    assert worklog.collect([s])['total_tokens'] == 110
    s = source(project.root, 'codex', [token(counts(100, 20), counts(100, 20)),
        token(counts(10, 2), counts(10, 2), '2026-10-27T00:12:00Z')])
    with Path(s['path']).open('a') as f:
        f.write('not-json-with-private-text\n')
    result = worklog.collect([s])
    assert result['total_tokens'] == 132 and len(result['warnings']) == 2
    assert 'private-text' not in str(result)


def test_claude_streaming_and_cache_accounting(project):
    event = dict(type='assistant', timestamp=T, sessionId='s1', requestId='r1', message=dict(id='m1',
        usage=dict(input_tokens=10, cache_read_input_tokens=100, cache_creation_input_tokens=20,
                   cache_creation={'ephemeral_5m_input_tokens': 20}, output_tokens=5)))
    final = deepcopy(event)
    final['message']['usage']['output_tokens'] = 15
    result = worklog.collect([source(project.root, 'claude', [event, final, final])])
    assert (result['total_tokens'], result['usage_records'], result['turn_wall_seconds']) == (145, 1, None)


def test_usage_is_recomputed_and_cross_task_overlap_rejected(project):
    s = source(project.root, 'codex', [token(counts(100, 10), counts(100, 10))])
    worklog.attach(project.root, project.task, 'codex', s['path'], START, END)
    assert cli(project.root, 'usage')[1]['total_tokens'] == cli(project.root, 'usage')[1]['total_tokens'] == 110
    value = worklog.task(project.root)
    worklog.attach(project.root, value, 'codex', s['path'], START, END)
    assert 'usage' not in worklog.task(project.root)
    other = worklog.task(project.root, 'i3-P4', 'Alice')
    with pytest.raises(ValueError, match='overlaps'):
        worklog.attach(project.root, other, 'codex', s['path'], T, END)
    worklog.attach(project.root, other, 'codex', s['path'], END, '2026-10-27T02:00:00Z')


def test_empty_usage_and_overlapping_wall_time(project):
    project.task['usage'] = worklog.collect([source(project.root, 'codex', [])])
    assert sheets.make_plan(snapshot(), project.task)['changes'] == []
    events = [dict(timestamp=T, type='event_msg', payload=dict(type='task_complete',
        started_at=f'2026-10-27T00:0{a}:00Z', completed_at=f'2026-10-27T00:0{b}:00Z')) for a, b in [(1, 3), (2, 4)]]
    s = source(project.root, 'codex', events)
    assert worklog.collect([s, s])['turn_wall_seconds'] == 180


def test_verbatim_prompts_exclude_tool_results_and_metadata(project):
    s = source(project.root, 'codex', [dict(type='event_msg', timestamp=T,
        payload={'type': 'user_message', 'message': '원문\n그대로 기록해'})])
    c = source(project.root, 'claude', [dict(type='user', timestamp=T, sessionId='s1',
        message={'content': [{'type': 'tool_result', 'content': 'private output'}]}),
        dict(type='user', timestamp=T, isMeta=True, message={'content': 'generated'})], 'claude')
    prompts = worklog.input_prompts([s, s, c])['prompts']
    assert [p['text'] for p in prompts] == ['원문\n그대로 기록해']


def test_row_discovery_and_duplicate_ids():
    s = snapshot()
    s['values'] = [['Title'], list(reversed(s['values'][0])), list(reversed(s['values'][1]))]
    assert sheets.find_row(s, 'i3-P3')['assignees'] == {'alice': 'Worker'}
    s['values'].append(s['values'][-1])
    with pytest.raises(ValueError):
        sheets.find_row(s, 'i3-P3')


def test_plan_whitelist_dates_formulas_and_validation(project):
    project.task['fields'] = dict(human_hours=0.5, end_date='2026-10-27', pr='https://github.com/a/b/pull/1')
    plan = sheets.make_plan(snapshot(), project.task)
    assert [c['field'] for c in plan['changes']] == ['end_date', 'human_hours']
    assert isinstance(plan['changes'][0]['after'], int)
    for field, value, cell in [('human_hours', 1, '=SUM(A1:A3)'), ('status', 'MadeUp', '')]:
        s = snapshot()
        s['values'][1][3] = cell
        project.task['fields'] = {field: value}
        with pytest.raises(ValueError):
            sheets.make_plan(s, project.task)


@pytest.mark.parametrize('change', ['row', 'position', 'validation'])
def test_changed_sheet_aborts(project, change):
    project.task['fields'] = {'status': 'Completed'}
    plan, altered = sheets.make_plan(snapshot(), project.task), snapshot()
    if change == 'row': altered['values'][1][2] = 'Another edit'
    if change == 'position': altered['values'].insert(1, [3, 'P2'])
    if change == 'validation': altered['allowed_values']['6'] = ['Hold']
    with pytest.raises(ValueError):
        sheets.check_plan(altered, plan)


def test_apply_rebuilds_requests_verifies_and_does_not_repeat(project):
    project.task['fields'] = {'human_hours': 1}
    plan, applied = sheets.make_plan(snapshot(), project.task), snapshot()
    applied['values'][1][3] = 1
    client = sheets.GoogleSheet.__new__(sheets.GoogleSheet)
    client.snapshot, client.request = Mock(side_effect=[snapshot(), applied, applied]), Mock()
    assert client.apply(project.task, plan)['result'] == 'verified'
    assert client.apply(project.task, plan)['result'] == 'already_applied'
    assert client.request.call_count == 1
    request = client.request.call_args.kwargs['json']['requests'][0]['updateCells']
    assert request['start'] == {'sheetId': 7, 'rowIndex': 1, 'columnIndex': 3}
    assert request['fields'] == 'userEnteredValue' and request['rows'][0]['values'][0] == {'userEnteredValue': {'numberValue': 1}}
    plan['changes'][0]['after'] = 99
    client.snapshot.return_value, client.snapshot.side_effect = snapshot(), None
    with pytest.raises(ValueError): client.apply(project.task, plan)
    assert client.request.call_count == 1


def test_cli_preview_preserves_sheet_and_rejects_changed_task(project):
    client = sheets.GoogleSheet.__new__(sheets.GoogleSheet)
    client.snapshot, client.request = Mock(return_value=snapshot()), Mock()
    with patch('tools.harness.sheets.GoogleSheet', return_value=client):
        cli(project.root, 'task', '--set', 'human_hours=0.5')
        assert len(cli(project.root, 'sheet')[1]['changes']) == 1
        cli(project.root, 'task', '--set', 'human_hours=1')
        assert cli(project.root, 'sheet', '--apply')[0] == 1
        client.request.assert_not_called()


def test_setup_and_bundle(project):
    with patch.dict('os.environ', {'METCHU_SCHEDULE_URL': 'https://example.invalid/spreadsheets/d/test-id'}):
        with pytest.raises(ValueError): sheets.config(project.root)
    with pytest.raises(ValueError, match='sheet --login'): sheets.GoogleSheet(project.root)
    assert harness.parser().parse_args(['sheet', '--login', 'client.json']).login == 'client.json'
    worklog.task(project.root, 'i2-P3', 'Alice')
    code, result = cli(project.root, 'bundle', '3')
    assert code == 0 and result['tasks'] == ['i3-P3']
    assert (Path(result['directory']) / 'input-prompts.private.json').exists()


def test_legacy_claude_launch(project):
    (project.root / 'AGENTS.md').write_text('Shared instructions')
    with patch('tools.harness.subprocess.run', return_value=SimpleNamespace(returncode=0)) as run:
        assert cli(project.root, 'launch', 'claude')[0] == 0
        assert run.call_args.args[0] == ['claude', '--append-system-prompt', 'Shared instructions']
        assert run.call_args.kwargs['cwd'] == project.root


def test_remote_metadata_and_range_validation():
    client = sheets.GoogleSheet.__new__(sheets.GoogleSheet)
    client.spreadsheet_id, client.gid = 'test-id', 7
    metadata = {'sheets': [{'properties': dict(sheetId=7, title='Renamed schedule', sheetType='GRID',
                                               gridProperties={'rowCount': 100, 'columnCount': 10})}]}
    details = {'sheets': [{'data': [{'startColumn': 6, 'rowData': [{'values': [{'dataValidation': {
        'condition': {'type': 'ONE_OF_RANGE', 'values': [{'userEnteredValue': '=Config!A1:A2'}]}}}]}]}]}]}
    client.request = Mock(side_effect=[metadata, details])
    client.values = Mock(side_effect=[[HEADERS], snapshot()['values'], [['Completed'], ['Hold']]])
    assert client.snapshot('i3-P3')['allowed_values'] == {'6': ['Completed', 'Hold']}
    assert client.values.call_args.args[0] == 'Config!A1:A2'


def test_numeric_warning_and_strict_rule(project):
    s = snapshot()
    s['validation_rules'] = {'3': {'condition': {'type': 'NUMBER_GREATER', 'values': [{'userEnteredValue': '0'}]}},
                             '7': {'condition': {'type': 'DATE_IS_VALID'}}}
    project.task['fields'] = {'human_hours': 0, 'end_date': '2026-10-27'}
    assert len(sheets.make_plan(s, project.task)['validation_notices']) == 1
    s['validation_rules']['3']['strict'] = True
    with pytest.raises(ValueError, match='numeric'): sheets.make_plan(s, project.task)


def test_native_codex_usage_preferred_and_deduplicated(project):
    native = dict(type='token_usage_record', timestamp=T, payload=dict(response_id='response-1', usage=counts(100, 10, 80)))
    s = source(project.root, 'codex', [token(counts(999999, 1000), counts(9000, 1000)), native, native])
    result = worklog.collect([s, s])
    assert (result['total_tokens'], result['cached_input_tokens'], result['usage_records']) == (110, 80, 1)


def test_aborted_and_open_turns_exclude_gaps(project):
    events = [dict(type='event_msg', timestamp=T, payload=dict(type=kind, turn_id=turn, **data)) for kind, turn, data in [
        ('task_started', 'a', {'started_at': '2026-10-27T00:01:00Z'}),
        ('turn_aborted', 'a', {'started_at': '2026-10-27T00:01:00Z', 'completed_at': '2026-10-27T00:03:00Z'}),
        ('task_started', 'b', {'started_at': '2026-10-27T00:10:00Z'})]]
    result = worklog.collect([source(project.root, 'codex', events)])
    assert result['turn_wall_seconds'] == 3120 and result['open_turns'] == 1


def test_modern_codex_input_prompts(project):
    e = dict(type='response_item', timestamp=T, payload=dict(type='message', role='user',
             content=[dict(type='input_text', text='Actual input')]))
    result = worklog.input_prompts([source(project.root, 'codex', [e])])
    assert [p['text'] for p in result['prompts']] == ['Actual input']


@pytest.mark.parametrize('before', ['', 1234567])
def test_token_numeric_value_and_grouping_written_together(project, before):
    project.task['usage'] = {'usage_records': 1, 'warnings': [], 'total_tokens': 1234567}
    initial = snapshot()
    initial['values'][1][5] = before
    plan = sheets.make_plan(initial, project.task)
    assert sheets.check_plan(initial, plan) == 'ready'
    after = deepcopy(initial)
    after['values'][1][5] = 1234567
    after['number_formats'] = {'5': {'type': 'NUMBER', 'pattern': '#,##0'}}
    client = sheets.GoogleSheet.__new__(sheets.GoogleSheet)
    client.snapshot, client.request = Mock(side_effect=[initial, after, after]), Mock()
    assert client.apply(project.task, plan)['result'] == 'verified'
    assert client.apply(project.task, plan)['result'] == 'already_applied'
    request = client.request.call_args.kwargs['json']['requests'][0]['updateCells']
    assert request['rows'][0]['values'][0] == {'userEnteredValue': {'numberValue': 1234567},
        'userEnteredFormat': {'numberFormat': {'type': 'NUMBER', 'pattern': '#,##0'}}}
    assert request['fields'] == 'userEnteredValue,userEnteredFormat.numberFormat'
    assert client.request.call_count == 1


def test_existing_custom_token_format_is_preserved(project):
    project.task['usage'] = {'usage_records': 1, 'warnings': [], 'total_tokens': 1234567}
    s = snapshot()
    s['number_formats'] = {'5': {'type': 'NUMBER', 'pattern': '#,##0.0'}}
    assert 'number_format' not in sheets.make_plan(s, project.task)['changes'][0]
