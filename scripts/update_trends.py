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
    """GitHub Actions環境から自動で公開URLを特定する"""
    repo_full = os.environ.get("GITHUB_REPOSITORY", "")
    if "/" in repo_full:
        owner, repo = repo_full.split("/", 1)
        if repo.lower() == f"{owner.lower()}.github.io":
            return f"https://{owner}.github.io"
        return f"https://{owner}.github.io/{repo}"
    return "https://example.github.io/waraku-picks"

FEEDS = [
    {
        "url": "https://www.reddit.com/r/BuyItForLife/hot/.rss?limit=6",
        "source": "Reddit 一生モノ名品 (BuyItForLife)"
    },
    {
        "url": "https://www.reddit.com/r/gadgets/hot/.rss?limit=6",
        "source": "Reddit 最新ガジェット (Gadgets)"
    },
    {
        "url": "https://b.hatena.ne.jp/hotentry/life.rss",
        "source": "国内 暮らし・ライフスタイルトレンド"
    }
]

def fetch_raw_topics():
    raw_topics = []
    headers = {'User-Agent': 'Mozilla/5.0 (compatible; WarakuPicksBot/2.0)'}

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
あなたは「和楽百貨 (WARAKU PICKS)」という和モダン・キュレーションサイトのカリスマバイヤー兼コピーライターです。
以下の「海外および国内の最新トレンドトピック一覧」から、日本のAmazon.co.jpで購入可能で、読者が「これ欲しい！今すぐチェックしたい！」と強く惹かれる具体的な商品・アイテムを **6個** 厳選・連想して紹介カードを作成してください。

【トレンドトピック一覧】
{json.dumps(raw_topics, ensure_ascii=False, indent=2)}

【作成ルール】
1. 英語のトピックであっても、すべて自然で魅力的な**日本語**に変換すること。
2. トピックが抽象的なニュースや雑談の場合は、そこから連想される「日本のAmazonで買える具体的な名品・便利グッズ」に昇華させること。
3. 以下のJSON配列フォーマットのみを出力すること。

[
  {{
    "title": "購買意欲を刺激する魅力的な日本語商品名（22〜38文字程度）",
    "category": "以下から1つ選択しつつ最低2個は『世界の新着トレンド』にすること: ['世界の新着トレンド', 'ガジェット・デスク', 'キッチン・料理道具', '睡眠・ヘルスケア', '食品・ご褒美グルメ', 'ホビー・知育']",
    "emoji": "商品の魅力を象徴する絵文字1文字",
    "badge": "短い注目バッジ（例: '海外で話題沸騰', '一生モノ名品', 'SNS急上昇', '時短の神アイテム'）",
    "description": "商品の特徴や、なぜ今注目されているのかを伝える魅力的な解説文（70〜100文字程度）",
    "appeal_point": "『これを買うと生活がどう劇的に良くなるか』を一言で刺す推しコメント（40〜60文字程度）",
    "search_keyword": "日本のAmazon.co.jpで検索した際に優良商品が並ぶ最適な日本語検索キーワード（スペース区切りで2〜4語）",
    "tags": ["関連タグ1", "関連タグ2", "関連タグ3"]
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
                print(f"[Success] Gemini APIで {len(generated_items)} 件の商品紹介を生成しました！")
                return generated_items
    except Exception as e:
        print(f"[Error] Gemini API 呼び出しエラー ({e})。フォールバック処理に切り替えます。")

    return fallback_transform(raw_topics)

def fallback_transform(raw_topics):
    fallback_items = []
    for t in raw_topics[:4]:
        clean = re.sub(r'\[.*?\]', '', t["raw_title"]).strip()
        short_title = clean[:40] + ("..." if len(clean) > 40 else "")
        words = re.findall(r'\b[A-Z][a-zA-Z0-9]{2,}\b', clean)
        kw = " ".join(words[:3]) if words else "便利グッズ おすすめ ランキング"
        fallback_items.append({
            "title": f"【注目トレンド】{short_title}",
            "category": "世界の新着トレンド",
            "emoji": "🌍",
            "badge": "本日急上昇",
            "description": f"{t['source']}で現在大きな注目を集めているホットトピックです。",
            "appeal_point": "話題のアイテムや関連する暮らしの名品をAmazonですぐに比較・チェックできます。",
            "search_keyword": kw,
            "tags": ["トレンド巡回", "話題沸騰", "注目アイテム"]
        })
    return fallback_items

def generate_sns_posts(ai_items, base_url, today_iso):
    """本日生成されたトレンド商品から、X(旧Twitter)およびnote用のコピペ宣伝文を生成する"""
    top3 = ai_items[:3] if len(ai_items) >= 3 else ai_items
    top1 = top3[0] if top3 else {"title": "世界のトレンド名品", "emoji": "🎁", "appeal_point": "毎日の暮らしが劇的に整う逸品"}

    # パターン1: X(Twitter) まとめ紹介型（最もクリック率が高い王道フォーマット）
    bullets = "\n".join([f"{item.get('emoji', '✨')} {item.get('title')}" for item in top3])
    x_post_summary = (
        f"【{today_iso} 世界と日本のトレンド特選🍵】\n"
        f"海外の「一生モノ名品」や国内ライフスタイルトレンドから、今すぐ欲しくなる注目アイテムを更新しました！\n\n"
        f"{bullets}\n\n"
        f"👇1秒で探せる特選カタログ＆Amazon口コミはこちら\n"
        f"{base_url}/\n"
        f"#買ってよかった #便利グッズ #ガジェット #暮らしを整える"
    )

    # パターン2: X(Twitter) 1点突破・共感フック型
    x_post_single = (
        f"いま海外・SNSのトレンドで注目されているこれ、暮らしの質が一段上がる名品です👇\n\n"
        f"{top1.get('emoji', '🔥')} {top1.get('title')}\n"
        f"💡 {top1.get('appeal_point', '')}\n\n"
        f"他にも時短キッチン道具や睡眠ケアなど本日の特選ラインナップを公開中！\n"
        f"{base_url}/\n"
        f"#Amazonおすすめ #QOL向上 #一生モノ"
    )

    # パターン3: note / ブログ記事末尾・つぶやき用Markdownテンプレート
    note_lines = [
        f"## 🍵 本日の「和楽百貨 (WARAKU PICKS)」世界トレンド特選（{today_iso} 更新）",
        "",
        "海外のガジェット・一生モノ名品コミュニティ（Reddit等）や国内の暮らしトレンドから、本日特に注目度が高いアイテムをピックアップしました。",
        ""
    ]
    for idx, item in enumerate(top3, 1):
        note_lines.append(f"### {idx}. {item.get('emoji', '🎁')} {item.get('title')} （{item.get('badge', '注目')}）")
        note_lines.append(f"- **特徴**: {item.get('description', '')}")
        note_lines.append(f"- **推しポイント**: {item.get('appeal_point', '')}")
        note_lines.append("")

    note_lines.append(f"👉 **[全ジャンルの検索・Amazonでの詳細や口コミチェックはこちら（和楽百貨）]({base_url}/)**")
    note_markdown = "\n".join(note_lines)

    # テキストファイル(data/sns_post.txt)へわかりやすく保存
    full_text_output = (
        f"=========================================\n"
        f"📅 {today_iso} 自動生成 SNS・note 宣伝コピペ帳\n"
        f"=========================================\n\n"
        f"--- 【1】X (旧Twitter) 王道まとめポスト（コピペ用） ---\n"
        f"{x_post_summary}\n\n"
        f"--- 【2】X (旧Twitter) 1点突破・QOL訴求ポスト（コピペ用） ---\n"
        f"{x_post_single}\n\n"
        f"--- 【3】note・ブログ・メルマガ貼り付け用 (Markdown) ---\n"
        f"{note_markdown}\n"
    )

    with open(SNS_POST_FILE, "w", encoding="utf-8") as f:
        f.write(full_text_output)

    print(f"[SNS] {SNS_POST_FILE} に本日のコピペ用宣伝ポストを自動生成しました。")

    return {
        "x_summary": x_post_summary,
        "x_single": x_post_single,
        "note_md": note_markdown
    }

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

    print(f"[SEO] {SITEMAP_FILE} と {ROBOTS_FILE} を最新日時 ({today_iso}) で自動生成しました。")

def main():
    if not os.path.exists(DATA_FILE):
        print(f"[Error] {DATA_FILE} が見つかりません。")
        return

    with open(DATA_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    master_items = [
        item for item in data.get("items", [])
        if not item.get("is_ai_generated", False) and item.get("category") != "世界の新着トレンド"
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

    # SNS宣伝文を生成し、テキストファイル保存＆JSON内にも格納
    sns_posts = generate_sns_posts(ai_items, base_url, today_iso)

    all_items = ai_items + master_items
    data["updated_at"] = now_str
    data["sns_posts"] = sns_posts
    data["items"] = all_items

    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    categories = sorted(list(set(item.get("category", "") for item in all_items if item.get("category"))))
    generate_seo_files(base_url, today_iso, categories)

    print(f"[Done] すべての自動更新が完了しました ({now_str})")

if __name__ == "__main__":
    main()
