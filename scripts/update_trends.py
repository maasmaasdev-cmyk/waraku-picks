import json
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
import os
import re

DATA_FILE = "data/products.json"

# 世界と日本のトレンド情報源（RSS）
FEEDS = [
    {
        "url": "https://www.reddit.com/r/BuyItForLife/hot/.rss?limit=5",
        "source": "Reddit一生モノ名品",
        "emoji": "🌍"
    },
    {
        "url": "https://b.hatena.ne.jp/hotentry/life.rss",
        "source": "国内暮らしトレンド",
        "emoji": "✨"
    }
]

def clean_title(text):
    # 不要な記号や英語の定型文を整理して検索キーワードを抽出
    text = re.sub(r'\[.*?\]', '', text).strip()
    return text[:45] + ("..." if len(text) > 45 else "")

def fetch_trends():
    new_trends = []
    headers = {'User-Agent': 'Mozilla/5.0 (compatible; WarakuPicksBot/1.0)'}

    for feed in FEEDS:
        try:
            req = urllib.request.Request(feed["url"], headers=headers)
            with urllib.request.urlopen(req, timeout=10) as response:
                xml_data = response.read()
                root = ET.fromstring(xml_data)

                # Atom (Reddit) または RSS 1.0/2.0 のタイトル取得
                entries = root.findall('.//{http://www.w3.org/2005/Atom}entry')
                if entries:
                    for entry in entries[:2]:
                        title_el = entry.find('{http://www.w3.org/2005/Atom}title')
                        if title_el is not None and title_el.text:
                            raw_title = title_el.text
                            # 英語圏のトレンドキーワードからブランド名・名詞を抽出
                            words = re.findall(r'\b[A-Z][a-zA-Z0-9]{2,}\b', raw_title)
                            kw = " ".join(words[:3]) if words else "海外 トレンド ガジェット"
                            new_trends.append({
                                "title": f"【{feed['source']}】{clean_title(raw_title)}",
                                "category": "世界の新着トレンド",
                                "emoji": feed["emoji"],
                                "badge": "本日急上昇",
                                "description": f"世界のコミュニティで今話題沸騰中のアイテム・トピック（原文: {clean_title(raw_title)}）。",
                                "appeal_point": "話題の先取りに！Amazonで関連アイテムや類似の名品を今すぐチェックできます。",
                                "search_keyword": kw,
                                "tags": ["海外トレンド", "自動収集", "話題沸騰"]
                            })
                else:
                    # はてなブックマーク等のRSS
                    items = root.findall('.//{http://purl.org/rss/1.0/}item')
                    for item in items[:2]:
                        title_el = item.find('{http://purl.org/rss/1.0/}title')
                        if title_el is not None and title_el.text:
                            raw_title = title_el.text
                            # 「買ってよかった」「おすすめ」等が含まれる記事を優先しつつキーワード化
                            new_trends.append({
                                "title": f"【注目トピック】{clean_title(raw_title)}",
                                "category": "世界の新着トレンド",
                                "emoji": feed["emoji"],
                                "badge": "SNSで話題",
                                "description": "国内のライフスタイル・暮らしジャンルで多くの注目を集めている最新トピックです。",
                                "appeal_point": "みんなが注目している暮らしのヒントや関連アイテムをAmazonで探せます。",
                                "search_keyword": "買ってよかった 便利グッズ ランキング",
                                "tags": ["国内トレンド", "暮らしの知恵", "注目"]
                            })
        except Exception as e:
            print(f"Feed fetch warning ({feed['source']}): {e}")

    return new_trends

def main():
    if not os.path.exists(DATA_FILE):
        return

    with open(DATA_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    # 既存の厳選アイテム（世界の新着トレンド以外）を保持
    curated_items = [item for item in data.get("items", []) if item.get("category") != "世界の新着トレンド"]
    
    # 新着トレンドを取得して先頭または末尾に結合
    trend_items = fetch_trends()
    
    JST = timezone(timedelta(hours=9))
    now_str = datetime.now(JST).strftime("%Y-%m-%d %H:%M JST")

    data["updated_at"] = now_str
    data["items"] = curated_items + trend_items

    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"Successfully updated {DATA_FILE} at {now_str}")

if __name__ == "__main__":
    main()
