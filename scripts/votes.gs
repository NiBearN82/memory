/**
 * 尼貝爾直播紀錄館：觀眾「安可／復仇」點播計數
 * 使用方式（只要做一次）：
 * 1. 開一個新的 Google 試算表 → 選單「擴充功能 → Apps Script」
 * 2. 把這整個檔案貼進去取代原本內容，存檔
 * 3. 右上角「部署 → 新增部署作業」→ 類型選「網頁應用程式」
 *    執行身分：我；誰可以存取：所有人 → 部署 → 授權
 * 4. 複製「網頁應用程式網址」（https://script.google.com/macros/s/.../exec）
 *    貼到 site/index.html 的 VOTE_URL
 * 票數會記在試算表的「votes」工作表：A 欄歌曲代號、B 欄安可、C 欄復仇。
 */
const SHEET = 'votes';

function doGet() {
  return out(read());
}

function doPost(e) {
  let body = {};
  try { body = JSON.parse(e.postData.contents); } catch (err) { return out({ error: 'bad json' }); }
  const k = String(body.k || '').slice(0, 80);
  const col = body.t === 'r' ? 3 : 2;
  if (!k) return out({ error: 'no key' });
  const lock = LockService.getScriptLock();
  lock.waitLock(5000);
  try {
    const sh = sheet();
    const keys = sh.getLastRow() ? sh.getRange(1, 1, sh.getLastRow(), 1).getValues().map(r => r[0]) : [];
    let row = keys.indexOf(k) + 1;
    if (!row) { sh.appendRow([k, 0, 0]); row = sh.getLastRow(); }
    const cell = sh.getRange(row, col);
    cell.setValue((Number(cell.getValue()) || 0) + 1);
  } finally {
    lock.releaseLock();
  }
  return out(read());
}

function read() {
  const sh = sheet();
  if (!sh.getLastRow()) return {};
  const o = {};
  sh.getRange(1, 1, sh.getLastRow(), 3).getValues().forEach(r => {
    if (r[0]) o[r[0]] = [Number(r[1]) || 0, Number(r[2]) || 0];
  });
  return o;
}

function sheet() {
  const ss = SpreadsheetApp.getActive();
  return ss.getSheetByName(SHEET) || ss.insertSheet(SHEET);
}

function out(o) {
  return ContentService.createTextOutput(JSON.stringify(o)).setMimeType(ContentService.MimeType.JSON);
}
