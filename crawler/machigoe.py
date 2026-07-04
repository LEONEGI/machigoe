#!/usr/bin/env python3
"""マチゴエ収集クローラ v1

sources.yaml に定義されたソース（RSS / HTML一覧ページ）を巡回し、
パブリックコメント・縦覧の募集情報を抽出して docs/data.json と
docs/calendar.ics を生成する。

設計原則:
- ルールベースのみ（LLM API 不使用、ランニングコスト0円）
- robots.txt 遵守、1.5秒/リクエスト、UAに運営者連絡先を明記
- ソース単位で失敗を隔離（1ソースの障害が全体を止めない）
- 出力に鮮度情報を含め、フロント側で「最終更新」を表示できるようにする
"""
import hashlib
import json
import re
import sys
import time
from datetime import datetime, date, timedelta, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib import robotparser

import requests
import feedparser
import yaml
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
STATE_FILE = Path(__file__).resolve().parent / "state.json"
SOURCES_FILE = Path(__file__).resolve().parent / "sources.yaml"

UA = "MachigoeBot/1.0 (+https://leb-plus.co.jp/pubcome/; contact: watch@leb-plus.co.jp)"
DELAY_SEC = 1.5
TIMEOUT = 30
MAX_ENRICH_PER_SOURCE = 15  # 1回の実行でソースごとに詳細ページを見に行く新規件数の上限
JST = timezone(timedelta(hours=9))

KEYWORDS = re.compile(r"パブリックコメント|パブコメ|意見公募|意見募集|意見を募集|ご意見を|縦覧|意見書の提出")
EXCLUDE = re.compile(
    r"結果|実施状況|とは$|について学ぶ"
    r"|(令和|平成)[0-9０-９元・年平成令和\s]*年度$"   # 「令和7年度」「平成31年・令和元年度」等の年度別アーカイブ
    r"|年度中に決定|決定・変更した"          # 過去の決定一覧
    r"|ホームページ$|のページ$|制度のページ"  # 汎用ページリンク
)

# サイト共通ナビや汎用カテゴリリンクの除去（no_filterソースでも適用）
NAV_EXCLUDE = re.compile(
    r"^(トップページ|ホーム|サイトマップ|サイトポリシー|プライバシー.*|アクセシビリティ|"
    r"Multilingual|English|中文|한국어?|よくある質問|お問い?合わせ|組織.*|各課.*|"
    r"くらし.*|防災.*|子育て.*|健康.*|観光.*|区政情報|市政情報|環境・まちづくり|"
    r"まちづくり・都市計画|都市計画決定・変更|意見公募（パブリックコメント）|パブリックコメント|"
    r"ご意見を募集している案件)$"
    r"|本文へ移動|文字拡大|音声読み上げ|色合い|携帯サイト|RSSについて|ページの先頭"
)

_session = requests.Session()
_session.headers["User-Agent"] = UA
_robots_cache: dict[str, robotparser.RobotFileParser] = {}
_last_fetch = 0.0


def robots_ok(url: str) -> bool:
    host = urlparse(url).scheme + "://" + urlparse(url).netloc
    rp = _robots_cache.get(host)
    if rp is None:
        rp = robotparser.RobotFileParser()
        try:
            rp.set_url(host + "/robots.txt")
            rp.read()
        except Exception:
            rp = None  # robots.txt が読めないサイトは許可扱い（一般的解釈）
        _robots_cache[host] = rp
    return rp is None or rp.can_fetch(UA, url)


def fetch(url: str) -> requests.Response | None:
    global _last_fetch
    if not robots_ok(url):
        print(f"  [robots] disallowed: {url}")
        return None
    wait = DELAY_SEC - (time.time() - _last_fetch)
    if wait > 0:
        time.sleep(wait)
    _last_fetch = time.time()
    try:
        r = _session.get(url, timeout=TIMEOUT)
        if r.status_code == 200:
            return r
        print(f"  [http {r.status_code}] {url}")
    except requests.RequestException as e:
        print(f"  [error] {url}: {e}")
    return None


# ---------- 日付抽出 ----------

DATE_PAT = re.compile(
    r"(?:令和\s*(\d{1,2})|(\d{4}))\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日"
)
SLASH_PAT = re.compile(r"(\d{4})/(\d{1,2})/(\d{1,2})")  # e-Gov形式「受付締切日時：2026/08/03 23:59」
MD_PAT = re.compile(r"(\d{1,2})\s*月\s*(\d{1,2})\s*日")


def _to_date(reiwa, yyyy, m, d) -> date | None:
    try:
        year = 2018 + int(reiwa) if reiwa else int(yyyy)
        return date(year, int(m), int(d))
    except ValueError:
        return None


def extract_dates(text: str, base: date) -> list[date]:
    """テキスト中の日付を全て抽出。年なしの「M月D日」は直近未来と解釈する。"""
    found = []
    for m in DATE_PAT.finditer(text):
        dt = _to_date(m.group(1), m.group(2), m.group(3), m.group(4))
        if dt:
            found.append(dt)
    for m in SLASH_PAT.finditer(text):
        dt = _to_date(None, m.group(1), m.group(2), m.group(3))
        if dt:
            found.append(dt)
    # 年つきが1つも無いときだけ年なしパターンを解釈（誤検出防止）
    if not found:
        for m in MD_PAT.finditer(text):
            try:
                dt = date(base.year, int(m.group(1)), int(m.group(2)))
                if dt < base - timedelta(days=14):
                    dt = date(base.year + 1, dt.month, dt.day)
                found.append(dt)
            except ValueError:
                continue
    return found


def guess_deadline(text: str, today: date) -> str | None:
    """締切らしい日付を推定。近傍に締切語がある日付を優先、なければ本文中の最大未来日。"""
    candidates: list[date] = []
    for m in re.finditer(r".{0,25}?(締め?切り?|期限|まで|受付期間|募集期間|提出期限).{0,40}", text):
        candidates += extract_dates(m.group(0), today)
    if not candidates:
        candidates = extract_dates(text[:6000], today)
    future = [d for d in candidates if today - timedelta(days=3) <= d <= today + timedelta(days=180)]
    if not future:
        return None
    return max(future).isoformat()


# ---------- 収集 ----------

def item_id(source_id: str, url: str, title: str) -> str:
    return hashlib.sha1(f"{source_id}|{url}|{title}".encode()).hexdigest()[:16]


def collect_rss(src: dict) -> list[dict]:
    r = fetch(src["url"])
    if r is None:
        raise RuntimeError("fetch failed: " + src["url"])  # 取得失敗は「0件成功」ではなく障害として数える
    feed = feedparser.parse(r.content)
    items = []
    for e in feed.entries[:80]:
        title = (e.get("title") or "").strip()
        link = e.get("link") or ""
        if not title or not link:
            continue
        summary = e.get("summary") or ""
        if not src.get("no_filter") and not KEYWORDS.search(title + " " + summary):
            continue
        if EXCLUDE.search(title):
            continue
        items.append({"title": title, "url": link, "summary": re.sub(r"<[^>]+>", " ", summary)[:1000]})
    return items


def collect_html_list(src: dict) -> list[dict]:
    r = fetch(src["url"])
    if r is None:
        raise RuntimeError("fetch failed: " + src["url"])
    r.encoding = r.apparent_encoding or r.encoding
    soup = BeautifulSoup(r.text, "html.parser")
    scope = soup.select_one(src["selector"]) if src.get("selector") else None
    scope = scope or soup.find("main") or soup.body or soup
    items, seen = [], set()
    src_host = urlparse(src["url"]).netloc
    for a in scope.find_all("a", href=True):
        text = a.get_text(" ", strip=True)
        raw = a["href"].split("#")[0]
        if not raw or raw.lower().startswith(("javascript:", "mailto:")):
            continue
        href = urljoin(src["url"], raw)
        if href == src["url"]:
            continue
        # 既定では同一ドメインのみ（外部の法令DB・関連リンク等への迷子を防ぐ）
        if urlparse(href).netloc != src_host and not src.get("allow_external"):
            continue
        if not text or len(text) < 8 or href in seen:
            continue
        if NAV_EXCLUDE.search(text):
            continue
        # リンク文言か、その親要素のテキストにキーワードがあるものを候補に
        context = text
        if a.parent is not None:
            context += " " + a.parent.get_text(" ", strip=True)[:200]
        if src.get("no_filter") or KEYWORDS.search(context):
            if EXCLUDE.search(text):
                continue
            seen.add(href)
            items.append({"title": text[:120], "url": href})
    return items[:60]


def enrich(item: dict, today: date) -> dict:
    """詳細ページを1回だけ見て締切を拾う。失敗しても致命傷にしない。"""
    if item["url"].lower().endswith((".pdf", ".xls", ".xlsx", ".doc", ".docx", ".zip")):
        item["deadline"] = guess_deadline(item["title"], today)
        return item
    r = fetch(item["url"])
    if r is not None:
        r.encoding = r.apparent_encoding or r.encoding
        text = BeautifulSoup(r.text, "html.parser").get_text(" ", strip=True)[:8000]
        item["deadline"] = guess_deadline(text, today)
    else:
        item["deadline"] = guess_deadline(item["title"], today)
    return item


# ---------- 出力 ----------

def ics_escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def write_ics(items: list[dict]) -> None:
    now = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//machigoe//pubcome-calendar//JP",
        "X-WR-CALNAME:マチゴエ｜パブコメ・縦覧の締切",
        "X-WR-TIMEZONE:Asia/Tokyo",
    ]
    for it in items:
        if not it.get("deadline"):
            continue
        d = it["deadline"].replace("-", "")
        lines += [
            "BEGIN:VEVENT",
            f"UID:{it['id']}@machigoe",
            f"DTSTAMP:{now}",
            f"DTSTART;VALUE=DATE:{d}",
            f"SUMMARY:{ics_escape('【締切】' + it['title'][:60] + '（' + it['area'] + '）')}",
            f"DESCRIPTION:{ics_escape(it['url'])}",
            f"URL:{it['url']}",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    (DOCS / "calendar.ics").write_text("\r\n".join(lines) + "\r\n", encoding="utf-8")


def main() -> int:
    today = datetime.now(JST).date()
    sources = yaml.safe_load(SOURCES_FILE.read_text(encoding="utf-8"))
    state = json.loads(STATE_FILE.read_text(encoding="utf-8")) if STATE_FILE.exists() else {"items": {}, "sources": {}}
    items_state: dict = state["items"]
    src_state: dict = state["sources"]

    for src in sources:
        if not src.get("enabled", True):
            continue
        sid = src["id"]
        print(f"[source] {sid} ({src['type']})")
        try:
            raw = collect_rss(src) if src["type"] == "rss" else collect_html_list(src)
            enriched = 0
            for it in raw:
                iid = item_id(sid, it["url"], it["title"])
                if iid in items_state:
                    items_state[iid]["last_seen"] = today.isoformat()
                    continue
                if src.get("no_enrich"):
                    # 詳細ページを見に行かないソース（e-Gov等、ボット遮断があるサイト）。
                    # RSSのdescription内の締切表記から抽出する
                    it["deadline"] = guess_deadline(it["title"] + " " + it.get("summary", ""), today)
                elif enriched < MAX_ENRICH_PER_SOURCE:
                    it = enrich(it, today)
                    enriched += 1
                else:
                    it["deadline"] = guess_deadline(it["title"] + " " + it.get("summary", ""), today)
                items_state[iid] = {
                    "id": iid, "source": sid, "area": src["area"], "kind": src["kind"],
                    "title": it["title"], "url": it["url"], "deadline": it.get("deadline"),
                    "first_seen": today.isoformat(), "last_seen": today.isoformat(),
                }
            src_state[sid] = {"name": src["name"], "area": src["area"], "fails": 0,
                              "last_success": datetime.now(JST).isoformat(), "items_seen": len(raw)}
            print(f"  ok: {len(raw)} items ({enriched} enriched)")
        except Exception as e:  # ソース単位で隔離し、連続失敗回数を記録（自己修復の検知材料）
            st = src_state.get(sid) or {"name": src["name"], "area": src["area"]}
            st["fails"] = int(st.get("fails", 0)) + 1
            st["last_error"] = str(e)[:200]
            src_state[sid] = st
            print(f"  [FAIL] {sid} (連続{st['fails']}回): {e}")

    # 掃除: 締切から60日経過、または締切不明のまま180日経過した項目を落とす
    def alive(v: dict) -> bool:
        if v.get("deadline"):
            return date.fromisoformat(v["deadline"]) >= today - timedelta(days=60)
        return date.fromisoformat(v["first_seen"]) >= today - timedelta(days=180)

    items_state = {k: v for k, v in items_state.items() if alive(v)}
    state = {"items": items_state, "sources": src_state}
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")

    # 出力（締切昇順、締切なしは後ろ）
    out_items = sorted(
        items_state.values(),
        key=lambda v: (v.get("deadline") is None, v.get("deadline") or "9999", v["first_seen"]),
    )
    DOCS.mkdir(exist_ok=True)
    # 健康状態レポート: 3回連続で失敗したソース＝修復が必要（Actionsが検知してIssue化、
    # ローカルの定期メンテナンスAIが修理を試みる）
    failing = [
        {"id": k, "name": v.get("name"), "area": v.get("area"),
         "fails": v.get("fails", 0), "last_error": v.get("last_error"),
         "last_success": v.get("last_success")}
        for k, v in src_state.items() if int(v.get("fails", 0)) >= 3
    ]
    (DOCS / "health.json").write_text(json.dumps({
        "generated_at": datetime.now(JST).isoformat(),
        "failing": failing,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    if failing:
        print(f"[health] 修復が必要なソース: {len(failing)}件 -> docs/health.json")
    (DOCS / "data.json").write_text(json.dumps({
        "generated_at": datetime.now(JST).isoformat(),
        "sources": src_state,
        "items": out_items,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    write_ics(out_items)
    print(f"[done] {len(out_items)} items -> docs/data.json, docs/calendar.ics")
    return 0


if __name__ == "__main__":
    sys.exit(main())
