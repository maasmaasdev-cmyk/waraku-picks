import json
import urllib.request
import urllib.error
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
import os
import re

DATA_FILE = "data/products.json"
SNS_POST_FILE = "data/sns_post.txt"
SITEMAP_FILE = "sitemap.xml"
ROBOTS_FILE = "robots.txt"

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = "gemini-2.5-flash"

def get_site_base_url():
    repo_full = os.environ.get("GITHUB_REPOSITORY", "")
    if "/" in repo_full:
        owner, repo = repo_full.split("/", 1)
        if repo.lower() == f"{owner.lower()}.github.io":
            return f"https://{owner}.github.io"
        return f"https://{owner}.github.io/{repo}"
    return "https://example.github.io/waraku-picks"

# 金融・投資・ライフスタイルのトレンドRSSに変更
FEEDS = [
    {
        "url": "https://b.hatena.ne.jp/hotentry/economics.rss",
        "source": "経済・マネートレンド"
    },
    {
        "url": "https://www.reddit.com/r/personalfinance/hot/.rss?limit=5",
        "source": "海外パーソナルファイナンス (PersonalFinance)"
    },
    {
        "url": "https://b.hatena.ne.jp/hotentry/life.rss",
        "source": "国内暮らしトレンド"
    }
]

def fetch_raw_topics():
    raw_topics = []
    headers = {'User-Agent': 'Mozilla/5.0 (compatible; WarakuFinBot/2.0)'}

    for feed in FEEDS:
        try:
            req = urllib.request.Request(feed["url"], headers=headers)
            with urllib.request.urlopen(req, timeout=12) as response:
                xml_data = response.read()
                root = ET.fromstring(xml_data)

                entries = root.findall('.//{http://www.w3.org/2005/Atom}entry')
                if entries:
                    for entry in entries[:4]:
                        title_el = entry.find('{http://www.w3.org/2005/Atom}title')
                        if title_el is not None and title_el.text:
                            raw_topics.append({
                                "source": feed["source"],
                                "raw_title": title_el.text.strip()
                            })
                else:
                    items = root.findall('.//{http://purl.org/rss/1.0/}item') or root.findall('.//item')
                    for item in items[:4]:
                        title_el = item.find('{http://purl.org/rss/1.0/}title')
                        if title_el is None:
                            title_el = item.find('title')
                        if title_el is not None and title_el.text:
                            raw_topics.append({
                                "source": feed["source"],
                                "raw_title": title_el.text.strip()
                            })
        except Exception as e:
            print(f"[Warning] Feed fetch skipped ({feed['source']}): {e}")

    return raw_topics

def generate_picks_with_gemini(raw_topics):
    if not GEMINI_API_KEY:
        print("[Info] GEMINI_API_KEY が未設定のため、フォールバック処理を実行します。")
        return fallback_transform(raw_topics)

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"

    prompt = f"""
あなたは「和楽百貨 (WARAKU PICKS)」という和モダン・キュレーションサイトのファイナンシャルプランナー兼カリスマコピーライターです。
以下の「最新の経済・投資・ライフスタイルトレンド一覧」から、日本のユーザーが「新NISAや資産運用、賢い家計管理を始めよう！」と強く惹かれる具体的な金融サービスや投資・節約アイテムを **6個** 厳選・連想して紹介カードを作成してください。

【トレンドトピック一覧】
{json.dumps(raw_topics, ensure_ascii=False, indent=2)}

【作成ルール】
1. すべて自然で魅力的な**日本語**に変換すること。
2. 資産運用初心者や新NISAを検討している人が「これなら自分も始められる」と感じる具体的な解説にすること。
3. カテゴリは必ず ['金融・投資', '睡眠・ヘルスケア', 'キッチン・料理道具', 'ガジェット・デスク', '食品・ご褒美グルメ', 'ホビー・知育'] から選択すること。
4. 以下のJSON配列フォーマットのみを出力すること。

[
  {{
    "title": "読者の投資・節約意欲を刺激する魅力的な日本語商品名（22〜38文字程度）",
    "category": "金融・投資",
    "emoji": "象徴する絵文字1文字",
    "badge": "短い注目バッジ（例: '新NISA必須', '高額還元', 'プロ推奨', '資産形成の第一歩'）",
    "description": "なぜ今このサービスや投資手法が注目されているのかを伝える魅力的な解説文（70〜100文字程度）",
    "appeal_point": "『これを始めることで将来の不安がどう解消されるか』を一言で刺す推しコメント（40〜60文字程度）",
    "search_keyword": "日本のAmazonまたはWEB検索で優良な比較情報や関連本が見つかる最適な日本語検索キーワード",
    "tags": ["新NISA", "資産運用", "マネーハック"]
  }}
]
"""

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.7,
            "responseMimeType": "application/json"
        }
    }

    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=30) as response:
            res_body = json.loads(response.read().decode("utf-8"))
            text_content = res_body["candidates"][0]["content"]["parts"][0]["text"]
            generated_items = json.loads(text_content)
            if isinstance(generated_items, list) and len(generated_items) > 0:
                print(f"[Success] Gemini APIで {len(generated_items)} 件の金融・投資紹介を生成しました！")
                return generated_items
    except Exception as e:
        print(f"[Error] Gemini API 呼び出しエラー ({e})。フォールバック処理に切り替えます。")

    return fallback_transform(raw_topics)

def fallback_transform(raw_topics):
    fallback_items = []
    for t in raw_topics[:4]:
        clean = re.sub(r'\[.*?\]', '', t["raw_title"]).strip()
        short_title = clean[:40] + ("..." if len(clean) > 40 else "")
        fallback_items.append({
            "title": f"【マネートレンド】{short_title}",
            "category": "金融・投資",
            "emoji": "💡",
            "badge": "注目ニュース",
            "description": f"{t['source']}で現在注目を集めている経済・お金に関する最新トピックです。",
            "appeal_point": "賢い資産形成や家計見直しのヒントとしてチェックしておきたい話題です。",
            "search_keyword": "新NISA 資産運用 おすすめ書籍",
            "tags": ["マネー情報", "経済トレンド", "資産形成"]
        })
    return fallback_items

def generate_sns_posts(ai_items, base_url, today_iso):
    top3 = ai_items[:3] if len(ai_items) >= 3 else ai_items
    top1 = top3[0] if top3 else {"title": "新NISA・資産形成の極意", "emoji": "📈", "appeal_point": "将来の安心をつくる第一歩"}

    x_post_summary = (
        f"【{today_iso} マネー・資産形成特選💡】\n"
        f"新NISAやネット証券の活用法、今チェックしておきたいお金のトレンド情報を更新しました！\n\n"
        f"{'\n'.join([f'{item.get(\"emoji\", \"✨\")} {item.get(\"title\")}' for item in top3])}\n\n"
        f"👇詳細・比較カタログはこちら\n"
        f"{base_url}/\n"
        f"#新NISA #資産運用 #マネーハック #投資初心者"
    )

    full_text_output = (
        f"=========================================\n"
        f"📅 {today_iso} 金融・投資特選 SNSポスト\n"
        f"=========================================\n\n"
        f"{x_post_summary}\n"
    )

    with open(SNS_POST_FILE, "w", encoding="utf-8") as f:
        f.write(full_text_output)

    return {"x_summary": x_post_summary, "x_single": x_post_summary, "note_md": ""}

def generate_seo_files(base_url, today_iso, categories):
    urls_xml = f"""  <url>
    <loc>{base_url}/</loc>
    <lastmod>{today_iso}</lastmod>
    <changefreq>daily</changefreq>
    <priority>1.0</priority>
  </url>\n"""

    for cat in categories:
        encoded_cat = urllib.parse.quote(cat)
        urls_xml += f"""  <url>
    <loc>{base_url}/?cat={encoded_cat}</loc>
    <lastmod>{today_iso}</lastmod>
    <changefreq>daily</changefreq>
    <priority>0.8</priority>
  </url>\n"""

    sitemap_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
{urls_xml}</urlset>
"""
    with open(SITEMAP_FILE, "w", encoding="utf-8") as f:
        f.write(sitemap_content)

    robots_content = f"""User-agent: *
Allow: /

Sitemap: {base_url}/sitemap.xml
"""
    with open(ROBOTS_FILE, "w", encoding="utf-8") as f:
        f.write(robots_content)

def main():
    if not os.path.exists(DATA_FILE):
        return

    with open(DATA_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    master_items = [
        item for item in data.get("items", [])
        if not item.get("is_ai_generated", False) and item.get("category") != "金融・投資"
    ]

    raw_topics = fetch_raw_topics()
    ai_items = generate_picks_with_gemini(raw_topics)
    for item in ai_items:
        item["is_ai_generated"] = True

    JST = timezone(timedelta(hours=9))
    now_dt = datetime.now(JST)
    now_str = now_dt.strftime("%Y-%m-%d %H:%M JST")
    today_iso = now_dt.strftime("%Y-%m-%d")

    base_url = get_site_base_url()
    sns_posts = generate_sns_posts(ai_items, base_url, today_iso)

    all_items = ai_items + master_items
    data["updated_at"] = now_str
    data["sns_posts"] = sns_posts
    data["items"] = all_items

    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    categories = sorted(list(set(item.get("category", "") for item in all_items if item.get("category"))))
    generate_seo_files(base_url, today_iso, categories)

    print(f"[Done] 金融特化の自動更新が完了しました ({now_str})")

if __name__ == "__main__":
    main()
