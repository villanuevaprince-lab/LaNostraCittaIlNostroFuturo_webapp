export async function writeAudit(connection, event) {
  const [result] = await connection.execute(
    `INSERT INTO EVENTO_LOG (
       IdEsecutore, TipoAzione, Esito, Dettagli, IdUtenteBersaglio,
       IdSegnalazione, IdCommento, IdAllegato, IdSostegno, IdBlocco, IdVerifica
     ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
    [
      event.executorId ?? null,
      event.type,
      event.outcome ?? 'successo',
      event.details,
      event.targetUserId ?? null,
      event.reportId ?? null,
      event.commentId ?? null,
      event.attachmentId ?? null,
      event.supportId ?? null,
      event.blockId ?? null,
      event.verificationId ?? null
    ]
  );
  return result.insertId;
}
