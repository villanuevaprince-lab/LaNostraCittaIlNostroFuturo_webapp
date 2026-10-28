"""Inbox personale e ritiro dei propri commenti."""
from flask import Blueprint, g, jsonify, render_template, request
from backend.database import database_cursor
from backend.repositories.notifications import inbox, mark_read
from backend.security import login_required

community = Blueprint('community', __name__)


@community.get('/notifiche')
@login_required
def notifications_page():
    return render_template('notifications.html')


@community.get('/api/notifiche')
@login_required
def notifications():
    raw = request.args.get('cursor')
    if raw is not None and (not raw.isdigit() or not 1 <= int(raw) <= 18446744073709551615):
        return jsonify(error='Cursore non valido.'), 400
    return jsonify(inbox(g.user['id'], int(raw) if raw else None))


@community.patch('/api/notifiche/<int:notification_id>')
@login_required
def read_notification(notification_id):
    mark_read(g.user['id'], notification_id)
    return jsonify(ok=True)


@community.delete('/api/commenti/<int:comment_id>')
@login_required
def delete_own_comment(comment_id):
    with database_cursor(write=True) as cursor:
        cursor.execute("SELECT IdAutore, Visibilita FROM COMMENTO WHERE IdCommento=%s FOR UPDATE", (comment_id,))
        row = cursor.fetchone()
        if not row or row['IdAutore'] != g.user['id']:
            return jsonify(error='Commento non trovato.'), 404
        if row['Visibilita'] != 'rimossa':
            # Conserva l'ID del nodo per non cancellare le risposte altrui.
            cursor.execute("UPDATE COMMENTO SET Testo='', Visibilita='rimossa' WHERE IdCommento=%s", (comment_id,))
            cursor.execute("""INSERT INTO EVENTO_LOG (IdEsecutore, TipoAzione, Esito, Dettagli, IdCommento)
                VALUES (%s,'ritiro_commento','successo','Commento eliminato dal suo autore',%s)""", (g.user['id'], comment_id))
    return jsonify(ok=True)
