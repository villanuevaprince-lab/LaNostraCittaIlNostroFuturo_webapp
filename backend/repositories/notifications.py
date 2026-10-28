"""Notifiche interne persistenti: la destinazione deriva sempre dalla sessione."""
from backend.database import database_cursor


def notify(cursor, recipient, actor, report_id, kind, comment_id=None):
    if recipient and recipient != actor:
        cursor.execute("""INSERT INTO NOTIFICA
            (IdDestinatario, IdSegnalazione, IdCommento, Tipo) VALUES (%s,%s,%s,%s)""",
            (recipient, report_id, comment_id, kind))


def inbox(user_id, before=None, limit=20):
    with database_cursor() as cursor:
        cursor.execute("""SELECT IdNotifica AS id, IdSegnalazione AS report_id,
            IdCommento AS comment_id, Tipo AS tipo, Letta AS letta, DataCreazione AS data
            FROM NOTIFICA WHERE IdDestinatario=%s AND (%s IS NULL OR IdNotifica < %s)
            ORDER BY IdNotifica DESC LIMIT %s""", (user_id, before, before, limit + 1))
        rows = cursor.fetchall()
        cursor.execute("SELECT COUNT(*) AS n FROM NOTIFICA WHERE IdDestinatario=%s AND Letta=FALSE", (user_id,))
        unread = cursor.fetchone()['n']
    page = rows[:limit]
    for row in page:
        row['data'] = row['data'].isoformat(timespec='seconds')
    return dict(items=page, next_cursor=page[-1]['id'] if len(rows) > limit else None, non_lette=unread)


def mark_read(user_id, notification_id):
    with database_cursor(write=True) as cursor:
        cursor.execute("UPDATE NOTIFICA SET Letta=TRUE WHERE IdDestinatario=%s AND IdNotifica=%s", (user_id, notification_id))
