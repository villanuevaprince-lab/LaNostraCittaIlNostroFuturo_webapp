from datetime import datetime
from unittest.mock import Mock
import pytest
from backend.tests.test_database import fake_mysql
from backend.tests.conftest import csrf_token
from backend.repositories.reports import add_comment, report_comments
from backend.repositories.notifications import notify, mark_read, inbox


def test_self_notification_is_suppressed(fake_mysql):
    _, cursor = fake_mysql
    notify(cursor, 7, 7, 1, 'risposta_commento', 2)
    cursor.execute.assert_not_called()


def test_reply_inserts_parent_and_notifies_unique_recipients(fake_mysql):
    connection, cursor = fake_mysql
    cursor.fetchone.side_effect = [
        {'Visibilita': 'pubblica', 'duplicate_of_id': None, 'IdAutore': 8},
        {'Visibilita': 'pubblica', 'IdSegnalazione': 10, 'IdAutore': 8},
        {'data': datetime(2026, 10, 28), 'autore': 'Autore'},
    ]
    result = add_comment(10, 7, 'Sono d’accordo', 12)
    assert result['parent_id'] == 12 and result['autore_id'] == 7
    notifications = [c for c in cursor.execute.call_args_list if 'INSERT INTO NOTIFICA' in c.args[0]]
    assert len(notifications) == 1
    assert notifications[0].args[1] == (8, 10, 42, 'risposta_commento')
    connection.commit.assert_called_once()


@pytest.mark.parametrize('parent', [None, {'IdSegnalazione': 99, 'Visibilita': 'pubblica'}, {'IdSegnalazione': 10, 'Visibilita': 'rimossa'}])
def test_reply_cannot_cross_reports_or_target_removed_comment(fake_mysql, parent):
    connection, cursor = fake_mysql
    cursor.fetchone.side_effect = [{'Visibilita': 'pubblica', 'duplicate_of_id': None}, parent]
    with pytest.raises(ValueError):
        add_comment(10, 7, 'Risposta', 12)
    connection.rollback.assert_called_once()
    assert not any('INSERT INTO COMMENTO' in c.args[0] for c in cursor.execute.call_args_list)


def test_notification_mark_is_scoped_to_recipient(fake_mysql):
    _, cursor = fake_mysql
    mark_read(7, 40)
    sql, params = cursor.execute.call_args.args
    assert 'IdDestinatario=%s AND IdNotifica=%s' in sql and params == (7, 40)


def test_inbox_uses_keyset_and_unread_owner_filter(fake_mysql):
    _, cursor = fake_mysql
    cursor.fetchall.return_value = [dict(id=i, data=datetime(2026, 10, 28)) for i in (9, 8, 7)]
    cursor.fetchone.return_value = {'n': 3}
    page = inbox(6, 10, limit=2)
    assert page['next_cursor'] == 8 and page['non_lette'] == 3
    assert cursor.execute.call_args_list[0].args[1] == (6, 10, 10, 3)


def test_own_comment_delete_preserves_thread(client, logged_in, fake_mysql):
    _, cursor = fake_mysql
    cursor.fetchone.return_value = {'IdAutore': 101, 'Visibilita': 'pubblica'}
    response = client.delete('/api/commenti/12', headers={'X-CSRFToken': csrf_token(client)})
    assert response.status_code == 200
    queries = [c.args[0] for c in cursor.execute.call_args_list]
    assert any("SET Testo='', Visibilita='rimossa'" in q for q in queries)
    assert not any('DELETE FROM COMMENTO' in q for q in queries)


def test_cannot_delete_someone_elses_comment(client, logged_in, fake_mysql):
    _, cursor = fake_mysql
    cursor.fetchone.return_value = {'IdAutore': 999, 'Visibilita': 'pubblica'}
    response = client.delete('/api/commenti/12', headers={'X-CSRFToken': csrf_token(client)})
    assert response.status_code == 404
    assert not any('UPDATE COMMENTO' in c.args[0] for c in cursor.execute.call_args_list)


def test_comment_delete_requires_csrf(client, logged_in):
    assert client.delete('/api/commenti/12').status_code == 400


def test_notification_inbox_uses_session_user(client, logged_in, monkeypatch):
    from backend import community
    query = Mock(return_value=dict(items=[], next_cursor=None, non_lette=0))
    monkeypatch.setattr(community, 'inbox', query)
    assert client.get('/api/notifiche?user_id=999&cursor=20').status_code == 200
    query.assert_called_once_with(101, 20)
    assert client.get('/api/notifiche?cursor=invalid').status_code == 400


def test_notifications_require_login(client):
    assert client.get('/api/notifiche').status_code == 401
