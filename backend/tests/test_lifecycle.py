"""Regressioni su autorizzazioni, merge, rollback e separazione dei tipi."""
from unittest.mock import Mock
import pytest
from backend.tests.test_database import fake_mysql
from backend.repositories.lifecycle import merge_reports
from backend.repositories.reports import change_report_state, add_comment, set_support


def row(kind='segnalazione', duplicate=None, visibility='pubblica'):
    return dict(Tipo=kind, duplicate_of_id=duplicate, Visibilita=visibility)


def test_merge_same_content_rejected():
    with pytest.raises(ValueError):
        merge_reports(4, 4, 9, 'Duplicato')


@pytest.mark.parametrize('target', [None, row('proposta'), row(duplicate=3), row(visibility='rimossa')])
def test_invalid_merge_rolls_back(fake_mysql, target):
    connection, cursor = fake_mysql
    cursor.fetchone.side_effect = [row(), target]
    with pytest.raises(ValueError):
        merge_reports(4, 5, 9, 'Stesso luogo')
    connection.rollback.assert_called_once()
    assert not any('UPDATE COMMENTO' in c.args[0] for c in cursor.execute.call_args_list)


def test_merge_locks_sorted_deduplicates_and_preserves_audit(fake_mysql):
    connection, cursor = fake_mysql
    cursor.fetchone.side_effect = [row(), row(), None]
    assert merge_reports(8, 4, 9, 'Stesso disservizio') == 4
    calls = cursor.execute.call_args_list
    assert calls[0].args[1] == (4,)
    assert calls[1].args[1] == (8,)
    queries = [c.args[0] for c in calls]
    assert any('ON DUPLICATE KEY UPDATE DataRitiro=NULL' in q for q in queries)
    assert any('UPDATE COMMENTO' in q for q in queries)
    assert any('SET duplicate_of_id' in q for q in queries)
    assert any('unione_duplicato' in q for q in queries)
    assert not any('DELETE FROM' in q for q in queries)
    connection.commit.assert_called_once()


def test_proposal_cannot_use_report_resolution_state(fake_mysql):
    _, cursor = fake_mysql
    cursor.fetchone.side_effect = [dict(Stato='in_valutazione', Tipo='proposta'), {'1': 1}]
    assert change_report_state(4, 9, 'risolta') is None
    assert not any('UPDATE SEGNALAZIONE' in c.args[0] for c in cursor.execute.call_args_list)


def test_racing_merge_prevents_writing_into_duplicate(fake_mysql):
    _, cursor = fake_mysql
    cursor.fetchone.return_value = row(duplicate=4)
    assert add_comment(8, 9, 'test') is None
    assert set_support(8, 9, True) is None


def test_lifecycle_type_catalog(client):
    states = {s['codice']: s for s in client.get('/api/stati').get_json()}
    assert states['inviata']['tipi'] == ['segnalazione']
    assert states['in_valutazione']['tipi'] == ['proposta']
    assert 'nuova' not in states and 'chiusa' not in states


def test_merge_requires_authentication(client):
    assert client.post('/api/moderazione/segnalazioni/4/duplicato', json={}).status_code in (400, 401)
