// Eseguire con NODE_PATH impostato alla cartella node_modules contenente jsdom.
const { JSDOM } = require('jsdom');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const documentHTML = `<div id="moderation-reports"></div><tbody id="unused"></tbody>
<table><tbody id="moderation-users"></tbody></table>
<p id="moderation-status"></p><p id="users-status"></p><input id="user-search">
<select id="moderation-filter"><option value="tutte">Tutte</option></select>
${['bulk-approve','bulk-reject','select-all-reports','moderation-next','users-next'].map(id => `<button id="${id}"></button>`).join('')}
<span id="selected-count"></span>`;
const dom = new JSDOM(documentHTML, { runScripts: 'outside-only' });
const { window } = dom;
const seenURLs = [];
const user = id => ({ id, nome: 'Nome', cognome: 'Cognome', email: `${id}@example.com`, stato: 'attivo', tipo_blocco: 'attivo' });
const pages = [
 { items: [user(30),user(29)], next_cursor: 29 },
 { items: [user(29),user(28)], next_cursor: 28 }, // pagina parzialmente sovrapposta
 { items: [user(29),user(28)], next_cursor: 28 }, // cursore bloccato e stessi utenti
 { items: [user(7)], next_cursor: null }, // nuova ricerca deve resettare gli ID
];
window.fetch = async url => {
 let result;
 if (url.startsWith('/api/moderazione/utenti')) { seenURLs.push(url); result = pages.shift(); }
 else result = url === '/api/stati' ? [] : { items: [], next_cursor: null };
 return { ok: true, json: async () => result };
};
window.eval(fs.readFileSync(path.join(__dirname, '../static/js/moderation.js'), 'utf8'));
const settle = () => new Promise(resolve => setTimeout(resolve, 10));
(async () => {
 const button = window.document.querySelector('#users-next');
 const count = () => window.document.querySelector('#moderation-users').children.length;
 await settle(); assert.equal(count(), 2);
 button.click(); button.click(); await settle();
 assert.equal(count(), 3); assert.equal(seenURLs.length, 2);
 assert.match(seenURLs[1], /cursor=29/);
 button.click(); await settle(); assert.equal(count(), 3); assert.equal(button.hidden, true);
 button.click(); await settle(); assert.equal(seenURLs.length, 3);
 const input = window.document.querySelector('#user-search'); input.value = 'rossi'; input.dispatchEvent(new window.Event('input'));
 await new Promise(resolve => setTimeout(resolve, 350));
 assert.equal(count(), 1); assert.match(seenURLs[3], /q=rossi/); assert.doesNotMatch(seenURLs[3], /cursor=/);
 dom.window.close(); console.log('Paginazione utenti: sovrapposizioni, cursore bloccato, click simultanei e ricerca verificati.');
})().catch(error => { console.error(error); process.exitCode = 1; dom.window.close(); });
