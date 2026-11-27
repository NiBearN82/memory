#!/usr/bin/env python3
"""尼貝爾直播紀錄館：從 YouTube Data API 抓最新的直播與 Shorts，更新 site/data.json。

需要環境變數 YT_API_KEY（放在 GitHub repo 的 Secrets）。
沒有金鑰時不會改動任何資料，網站維持原樣。
"""
import datetime as dt
import time
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import drive_covers  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "site", "data.json")
EXTRA = os.path.join(ROOT, "data", "extra.json")
TPE = dt.timezone(dt.timedelta(hours=8))
API = "https://www.googleapis.com/youtube/v3/"
KEY = os.environ.get("YT_API_KEY", "").strip()


# ---------- 小工具 ----------
def api(path, **params):
    params["key"] = KEY
    url = API + path + "?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def tpe_date(iso):
    return dt.datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(TPE).date().isoformat()


def iso_dur(s):
    m = re.fullmatch(r"P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?", s or "")
    if not m:
        return ""
    d, h, mi, se = (int(x or 0) for x in m.groups())
    h += d * 24
    return f"{h}:{mi:02d}:{se:02d}" if h else f"{mi}:{se:02d}"


def dur_secs(s):
    n = 0
    for p in (s or "0").split(":"):
        n = n * 60 + int(p or 0)
    return n


TS = re.compile(r"^\s*(\d{1,2}:\d{2}(?::\d{2})?)(?:\s+\d{1,2}:\d{2}(?::\d{2})?)?\s*[-–—｜|:：]?\s*(.+?)\s*$")


def chapters(desc):
    """把說明欄裡「時間 標題」的每一行抓成時間軸。少於 3 行的不算。"""
    out = []
    for line in (desc or "").splitlines():
        m = TS.match(line)
        if not m:
            continue
        t = re.sub(r"^0(\d:)", r"\1", m.group(1))       # 00:12 → 0:12、01:02:03 → 1:02:03
        t = re.sub(r"^0:(\d\d:\d\d)$", r"\1", t)          # 0:12:30 → 12:30
        out.append([t, m.group(2)])
    return out if len(out) >= 3 else []


def clean_short_title(t):
    t = re.sub(r"#\S+", "", t)
    t = re.sub(r"[【《〈]\s*[/／\s]*(?:Nibel|ニーベル|尼貝爾|vtuber|\s|/)*\s*[】》〉]", "", t, flags=re.I)
    return re.sub(r"\s{2,}", " ", t).strip() or "Shorts"


def short_cat(t):
    return "song" if re.search(r"歌ってみた|cover|翻唱|原創曲|original song|ringtone", t, re.I) else "clip"


def auto_book(title):
    """標題裡第一個《書名》和作者（作者寫在書名前面的「｜」後，或書名後面）。"""
    m = re.search(r"《([^》]+)》", title)
    if not m:
        return None
    before = re.search(r"[｜|]\s*([^｜|《》#]{2,30}?)\s*《", title[: m.end()])
    after = re.match(r"\s*([^【｜|#《》\s][^【｜|#《》]{1,29})", title[m.end():])
    author = ""
    if before and re.search(r"[\u4e00-\u9fff\u3040-\u30ff]", before.group(1)):
        author = before.group(1).strip()
    elif after and re.search(r"[\u4e00-\u9fff\u3040-\u30ff]", after.group(1)):
        author = after.group(1).strip()
    return m.group(1).strip(), author


PODCAST = re.compile(r"要不要聽聽尼在說什麼|^S\d+EP\d+|^EP\d+")


def auto_topic(title):
    title = re.sub(r"^【[^】]*】\s*", "", title)
    m = re.search(r"([^！？!?，,。、／/\s【】]{2,24}?)專題", title)
    return m.group(1) if m else None


# ---------- 書封（Google Books 公開資料） ----------
def book_key(t):
    t = re.sub(r"（[^）]*）|\([^)]*\)", "", t or "").lower()
    return re.sub(r"[\s・·．.、，,！!？?：:「」『』《》〈〉—\-／/]", "", t)


def google_cover(title, author):
    key = book_key(title)
    want = key[: min(len(key), 6)]
    queries = [f"intitle:{title}" + (f" inauthor:{author}" if author else ""), f"intitle:{title}", title]
    for q in queries:
        params = {"q": q, "maxResults": 10, "printType": "books"}
        if KEY:
            params["key"] = KEY  # 同一把金鑰，需在 Google Cloud 另外啟用 Books API
        url = "https://www.googleapis.com/books/v1/volumes?" + urllib.parse.urlencode(params)
        time.sleep(0.4)
        try:
            with urllib.request.urlopen(url, timeout=20) as r:
                res = json.loads(r.read().decode("utf-8"))
        except Exception as e:  # 書封抓不到不影響其他更新
            print("書封查詢失敗：", title, e)
            continue
        for it in res.get("items", []):
            vi = it.get("volumeInfo", {})
            img = vi.get("imageLinks", {})
            link = img.get("thumbnail") or img.get("smallThumbnail")
            if not link or want not in book_key(vi.get("title", "") + vi.get("subtitle", "")):
                continue
            return link.replace("http://", "https://").replace("&edge=curl", "")
    return ""


def update_covers(data, extra, limit=40):
    covers = data.get("covers", {})
    if extra.get("coverFolder"):  # 封面改由雲端硬碟提供，不再查 Google Books
        for k, v in extra.get("bookCovers", {}).items():
            covers[book_key(k)] = v
        data["covers"] = covers
        return
    over = {book_key(k): v for k, v in extra.get("bookCovers", {}).items()}
    seen, n, found = set(), 0, 0
    for _, title, author in data.get("books", []):
        k = book_key(title)
        if k in seen:
            continue
        seen.add(k)
        if k in over:
            covers[k] = over[k]
            continue
        if covers.get(k) or n >= limit:
            continue
        n += 1
        covers[k] = google_cover(re.sub(r"（[^）]*）", "", title), author)
        found += bool(covers[k])
    data["covers"] = covers
    print(f"書封：這次查了 {n} 本，找到 {found} 本；目前共有 {sum(1 for v in covers.values() if v)} 本有封面")


# ---------- 抓 YouTube ----------
def playlist_ids(pid):
    ids, token = [], None
    while True:
        p = {"part": "contentDetails", "playlistId": pid, "maxResults": 50}
        if token:
            p["pageToken"] = token
        r = api("playlistItems", **p)
        ids += [it["contentDetails"]["videoId"] for it in r.get("items", [])]
        token = r.get("nextPageToken")
        if not token:
            return ids


def intro_text(desc):
    """說明欄的介紹段：遇到時間軸就停，去掉連結、hashtag、固定宣傳行。"""
    out = []
    for line in (desc or "").splitlines():
        t = line.strip()
        if re.match(r"^[🎵🎶♪]?\s*(\d{1,2}:)?\d{1,2}:\d{2}", t):
            break
        if re.search(r"時間軸|章節|TIMESTAMP|━━|───|＝＝|==|-{4,}|【我們是由|尼好，我是創傷劇團|^🎭|謝幕|尼在這裡|參考資料|參考文獻|References", t, re.I):
            if out:
                break
            continue
        if re.search(r"https?://|^#|^@|訂閱|斗內|抖內|贊助|會員|綠界|商業合作|聯絡|優惠碼|折扣碼|優惠券|使用期限|結帳|全館|^※|折扣|限時|^nibel\\d|本集合作|^—$|^-$|搜集了很多人的理想|努力不懈留著汗水|夢想站上更大的舞台|站在這裡的理由|為了自己勇敢前進", t):
            continue
        out.append(t)
    text = re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip()
    body = re.sub(r"📖.*|《[^》]*》|\s", "", text)
    if len(body) < 20:  # 只剩書名或宣傳碼，不算介紹
        return ""
    return text[:900]

def fetch(handle):
    ch = api("channels", part="contentDetails", forHandle=handle)
    if not ch.get("items"):
        sys.exit(f"找不到頻道 {handle}")
    cid = ch["items"][0]["id"]
    uploads = ch["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
    ids = playlist_ids(uploads)
    try:  # UUSH… 是頻道的 Shorts 清單（YouTube 沒有正式文件，抓不到就改用片長判斷）
        shorts_set = set(playlist_ids("UUSH" + cid[2:]))
    except urllib.error.HTTPError:
        shorts_set = None
    videos = []
    for i in range(0, len(ids), 50):
        r = api("videos", part="snippet,contentDetails,liveStreamingDetails", id=",".join(ids[i:i + 50]), maxResults=50)
        videos += r.get("items", [])
    return videos, shorts_set


# ---------- 主程式 ----------
def main():
    if not KEY:
        print("沒有設定 YT_API_KEY，這次不更新資料。")
        return
    data = json.load(open(DATA, encoding="utf-8"))
    extra = json.load(open(EXTRA, encoding="utf-8"))
    hide = set(extra.get("hide", []))
    no_ch = set(extra.get("noChapters", []))

    videos, shorts_set = fetch(extra["channelHandle"])
    streams = {s[1]: s for s in data["streams"]}
    order = {s[1]: i for i, s in enumerate(data["streams"])}
    shorts = {s[1]: s for s in data["shorts"]}
    chs = data.get("chapters", {})
    n_new_v = n_new_s = 0
    descs = {}

    for v in videos:
        vid, sn = v["id"], v["snippet"]
        if vid in hide or sn.get("liveBroadcastContent") in ("live", "upcoming"):
            continue
        dur = iso_dur(v.get("contentDetails", {}).get("duration"))
        live = v.get("liveStreamingDetails", {})
        is_short = (vid in shorts_set) if shorts_set is not None else (0 < dur_secs(dur) <= 180 and not live)
        if is_short:
            if vid not in shorts:
                n_new_s += 1
                shorts[vid] = [tpe_date(sn["publishedAt"]), vid, short_cat(sn["title"]), clean_short_title(sn["title"])]
            continue
        # 直播、Podcast、翻唱 MV 等一般影片都收進來，網站會依標題自動分類
        if vid not in streams:
            n_new_v += 1
        streams[vid] = [tpe_date(live.get("actualStartTime") or sn["publishedAt"]), vid, dur, sn["title"]]
        descs[vid] = sn.get("description") or ""
        c = chapters(sn.get("description"))
        if c and vid not in no_ch:
            chs[vid] = c

    # 套用人工整理的資料
    for vid, cat in extra.get("shortCats", {}).items():
        if vid in shorts:
            shorts[vid][2] = cat
    for vid, t in extra.get("shortTitles", {}).items():
        if vid in shorts:
            shorts[vid][3] = t
    since = extra.get("shortsSince", "")
    for vid in [k for k, v in shorts.items() if v[0] < since]:
        shorts.pop(vid)
    for vid in hide:
        streams.pop(vid, None)
        shorts.pop(vid, None)
        chs.pop(vid, None)

    books = {b[0]: b for b in extra.get("books", [])}
    news = dict(extra.get("news", {}))
    for s in streams.values():
        if ("尼看什麼" in s[3] or PODCAST.search(s[3])) and s[1] not in books:
            b = auto_book(s[3])
            if b:
                books[s[1]] = [s[1], b[0], b[1]]
        if "新聞久一點" in s[3] and s[1] not in news:
            t = auto_topic(s[3])
            if t:
                news[s[1]] = t

    before = json.dumps({k: v for k, v in data.items() if k != "updated"}, ensure_ascii=False, sort_keys=True)
    # 新的在前；同一天的直播維持原本順序，新抓到的排最前面
    data["streams"] = sorted(streams.values(), key=lambda s: (s[0], -order.get(s[1], -1)), reverse=True)
    data["shorts"] = sorted(shorts.values(), key=lambda s: s[0], reverse=True)
    data["chapters"] = {k: v for k, v in chs.items() if k in streams}
    data["books"] = [books[s[1]] for s in data["streams"] if s[1] in books]
    intros = data.get("intros", {})
    for b in data["books"]:
        if b[0] in descs:
            t = intro_text(descs[b[0]])
            if t:
                intros[b[0]] = t
            else:
                intros.pop(b[0], None)
    data["intros"] = {k: v for k, v in intros.items() if k in books}
    data["news"] = news
    data["setlists"] = extra.get("setlists", {})
    data["shortSource"] = extra.get("shortSource", {})
    data["recCovers"] = extra.get("recordCovers", {})
    data["songLang"] = extra.get("songLang", {})
    update_covers(data, extra)
    drive_covers.sync(data, extra)
    after = json.dumps({k: v for k, v in data.items() if k != "updated"}, ensure_ascii=False, sort_keys=True)
    if after == before:
        print("沒有新的直播或 Shorts，資料不變。")
        return
    data["updated"] = dt.datetime.now(TPE).isoformat(timespec="minutes")
    json.dump(data, open(DATA, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    print(f"完成：直播 {len(data['streams'])} 場（新增 {n_new_v}）、Shorts {len(data['shorts'])} 支（新增 {n_new_s}）、時間軸 {len(data['chapters'])} 場")


if __name__ == "__main__":
    main()
