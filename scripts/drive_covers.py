#!/usr/bin/env python3
"""從 Google 雲端硬碟資料夾抓書封、專輯封面，存到 site/covers/，並寫進 site/data.json 的 coverFiles。

資料夾結構（名稱含「書」的子資料夾放書封，含「專輯／唱片／歌」的放專輯封面）：
    直播紀錄館封面/
      書籍/  反脆弱.jpg、我想把這個世界讀給你聽_李尚龍.png …
      專輯/  群青_YOASOBI.jpg …
檔名底線前面是書名或歌名，後面的作者／歌手可省略；網頁端會用同樣的比對規則配對。

認證二選一（都放在 GitHub Secrets）：
  GDRIVE_SA_JSON  服務帳戶的 JSON 金鑰。資料夾共享給服務帳戶的信箱（檢視者）即可，資料夾不用公開。
  YT_API_KEY      同一把金鑰也開了 Drive API 時，可以讀「知道連結的人可檢視」的資料夾。
資料夾 ID 寫在 data/extra.json 的 coverFolder（貼整個連結也可以）。
"""
import io
import json
import os
import re
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "site", "covers")
DRIVE = "https://www.googleapis.com/drive/v3/files"
IMG = re.compile(r"\.(jpe?g|png|webp|gif|avif)$", re.I)


def _auth():
    sa = os.environ.get("GDRIVE_SA_JSON", "").strip()
    if sa:
        from google.oauth2 import service_account
        from google.auth.transport.requests import Request
        cred = service_account.Credentials.from_service_account_info(
            json.loads(sa), scopes=["https://www.googleapis.com/auth/drive.readonly"])
        cred.refresh(Request())
        return {"Authorization": "Bearer " + cred.token}, {}
    key = os.environ.get("YT_API_KEY", "").strip()
    return ({}, {"key": key}) if key else (None, None)


def _get(url, headers, params, raw=False):
    req = urllib.request.Request(url + "?" + urllib.parse.urlencode(params), headers=headers)
    with urllib.request.urlopen(req, timeout=60) as r:
        b = r.read()
    return b if raw else json.loads(b.decode("utf-8"))


def _list(folder, headers, extra):
    files, token = [], None
    while True:
        p = dict(extra, q=f"'{folder}' in parents and trashed=false", pageSize=1000,
                 fields="nextPageToken,files(id,name,mimeType,md5Checksum,modifiedTime)",
                 supportsAllDrives="true", includeItemsFromAllDrives="true")
        if token:
            p["pageToken"] = token
        res = _get(DRIVE, headers, p)
        files += res.get("files", [])
        token = res.get("nextPageToken")
        if not token:
            return files


def _kind(name):
    if "書" in name or "book" in name.lower():
        return "books"
    if re.search(r"專輯|专辑|唱片|歌|album|music|record", name, re.I):
        return "records"
    return None


def _save(blob, path):
    """裁掉白邊或單色邊、轉成 JPEG，長邊最多 1000px，讓封面能滿版。"""
    from PIL import Image, ImageChops
    im = Image.open(io.BytesIO(blob))
    im = im.convert("RGBA") if im.mode in ("P", "LA") else im
    if im.mode == "RGBA":
        bg = Image.new("RGB", im.size, (255, 255, 255))
        bg.paste(im, mask=im.split()[3])
        im = bg
    im = im.convert("RGB")
    corner = im.getpixel((0, 0))
    diff = ImageChops.difference(im, Image.new("RGB", im.size, corner)).convert("L").point(lambda v: 255 if v > 18 else 0)
    box = diff.getbbox()
    if box and (box[2] - box[0]) * (box[3] - box[1]) >= 0.25 * im.size[0] * im.size[1]:
        im = im.crop(box)
    im.thumbnail((1000, 1000))
    im.save(path, "JPEG", quality=86, optimize=True)


def folder_id(v):
    m = re.search(r"folders/([\w-]+)|[?&]id=([\w-]+)", v or "")
    return (m.group(1) or m.group(2)) if m else (v or "").strip()


def sync(data, extra):
    folder = folder_id(extra.get("coverFolder", ""))
    if not folder:
        return
    headers, params = _auth()
    if headers is None:
        print("封面：沒有雲端硬碟憑證，略過")
        return
    old = data.get("coverFiles", {})
    meta = {f["id"]: f for kind in ("books", "records") for f in old.get(kind, [])}
    new = {"books": [], "records": []}
    got = 0
    try:
        top = _list(folder, headers, params)
    except Exception as e:  # 權限或網路問題時保留上次的封面
        print("封面：讀不到雲端硬碟資料夾 →", e)
        return
    todo = []
    for f in top:
        if f["mimeType"] == "application/vnd.google-apps.folder" and _kind(f["name"]):
            todo += [(_kind(f["name"]), x) for x in _list(f["id"], headers, params)]
    for kind, f in todo:
        if not IMG.search(f["name"]) and not f["mimeType"].startswith("image/"):
            continue
        rel = f"covers/{kind}/{f['id']}.jpg"
        path = os.path.join(ROOT, "site", rel)
        stem = IMG.sub("", f["name"]).strip()
        prev = meta.get(f["id"])
        if not (prev and prev.get("md5") == f.get("md5Checksum") and os.path.exists(path)):
            os.makedirs(os.path.dirname(path), exist_ok=True)
            blob = _get(f"{DRIVE}/{f['id']}", headers, dict(params, alt="media", supportsAllDrives="true"), raw=True)
            try:
                _save(blob, path)
            except Exception as e:
                print("封面：這張圖讀不了，略過 →", f["name"], e)
                continue
            got += 1
        new[kind].append({"id": f["id"], "name": stem, "src": rel, "md5": f.get("md5Checksum", "")})
    keep = {x["src"] for k in new for x in new[k]}
    for kind in ("books", "records"):
        d = os.path.join(OUT, kind)
        for fn in os.listdir(d) if os.path.isdir(d) else []:
            rel = f"covers/{kind}/{fn}"
            if re.fullmatch(r"[\w-]{20,}\.jpg", fn) and rel not in keep:
                os.remove(os.path.join(d, fn))  # 雲端硬碟刪掉的圖，網站也拿掉
    for k in new:
        new[k].sort(key=lambda x: x["name"])
    data["coverFiles"] = new
    print(f"封面：書 {len(new['books'])} 張、專輯 {len(new['records'])} 張，這次新下載 {got} 張")
