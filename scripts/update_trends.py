import json
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
import os
import re

DATA_FILE = "data/products.json"
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
# 高速・高精度かつ無料枠が広い gemini-2.5-flash を使用
GEMINI_MODEL = "gemini-2.5-flash"

# 巡回する世界＆国内のトレンド情報源（必要に応じて自由に追加可能）
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
    """各RSSフィードから生のトレンドタイトルを収集する"""
    raw_topics = []
    headers = {'User-Agent': 'Mozilla/5.0 (compatible; WarakuPicksBot/2.0)'}

    for feed in FEEDS:
        try:
            req = urllib.request.Request(feed["url"], headers=headers)
            with urllib.request.urlopen(req, timeout=12) as response:
                xml_data = response.read()
                root = ET.fromstring(xml_data)

                # Atom形式 (Reddit等)
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
                    # RSS 1.0/2.0形式 (はてなブックマーク等)
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
    """Gemini APIを使って、生トピックから購買意欲をそそる日本語の商品紹介JSONを生成する"""
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
3. 以下のJSON配列フォーマットのみを出力すること（Markdownのコードブロック記号は不要）。

[
  {{
    "title": "購買意欲を刺激する魅力的な日本語商品名（22〜38文字程度。例：【一生モノ】プロが愛用する超軽量チタン製マルチタンブラー）",
    "category": "以下から最も適するものを1つ選択しつつ、最低2個は『世界の新着トレンド』にすること: ['世界の新着トレンド', 'ガジェット・デスク', 'キッチン・料理道具', '睡眠・ヘルスケア', '食品・ご褒美グルメ', 'ホビー・知育']",
    "emoji": "商品の魅力を象徴する絵文字1文字",
    "badge": "短い注目バッジ（例: '海外で話題沸騰', '一生モノ名品', 'SNS急上昇', '時短の神アイテム'）",
    "description": "商品の特徴や、なぜ今世界・日本で注目されているのかを伝える魅力的な解説文（70〜100文字程度）",
    "appeal_point": "『これを買うと生活がどう劇的に良くなるか』を一言で刺す推しコメント（40〜60文字程度）",
    "search_keyword": "日本のAmazon.co.jpで検索した際に、購買率の高い優良商品がズラリと並ぶ最適な日本語検索キーワード（スペース区切りで2〜4語）",
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
                print(f"[Success] Gemini APIで {len(generated_items)} 件の魅力的な商品紹介を生成しました！")
                return generated_items
    except Exception as e:
        print(f"[Error] Gemini API 呼び出しエラー ({e})。フォールバック処理に切り替えます。")

    return fallback_transform(raw_topics)

def fallback_transform(raw_topics):
    """APIキー未設定時やエラー時の安全な代替処理"""
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

def main():
    if not os.path.exists(DATA_FILE):
        print(f"[Error] {DATA_FILE} が見つかりません。")
        return

    with open(DATA_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    # 1. 手動で登録した厳選マスター商品（"is_ai_generated": True が付いていないもの）を保護
    master_items = [
        item for item in data.get("items", [])
        if not item.get("is_ai_generated", False) and item.get("category") != "世界の新着トレンド"
    ]

    # 2. 世界と日本のトレンドRSSを収集
    raw_topics = fetch_raw_topics()

    # 3. Gemini APIで購買意欲をそそる日本語カードに変換
    ai_items = generate_picks_with_gemini(raw_topics)
    for item in ai_items:
        item["is_ai_generated"] = True  # 次回更新時に自動で入れ替わるようフラグを付与

    # 4. 最新AIトレンド商品を先頭に配置して鮮度とクリック率を最大化（その後に定番マスター商品を配置）
    JST = timezone(timedelta(hours=9))
    now_str = datetime.now(JST).strftime("%Y-%m-%d %H:%M JST")

    data["updated_at"] = now_str
    data["items"] = ai_items + master_items

    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"[Done] {DATA_FILE} を更新しました ({now_str})")

if __name__ == "__main__":
    main()
