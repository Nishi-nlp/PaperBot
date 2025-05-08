import os
import re
import json
import time
import requests
import feedparser
import tweepy
import praw
from openai import OpenAI
from datetime import datetime, timedelta
from googleapiclient.discovery import build
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError


# 環境変数から各種APIキーを取得
SLACK_BOT_TOKEN = os.environ.get('SLACK_BOT_TOKEN')
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY')
REDDIT_CLIENT_ID = os.environ.get('REDDIT_CLIENT_ID')
REDDIT_CLIENT_SECRET = os.environ.get('REDDIT_CLIENT_SECRET')
GOOGLE_API_KEY = os.environ.get('GOOGLE_API_KEY')
GOOGLE_CSE_ID = os.environ.get('GOOGLE_CSE_ID')

# Slack Channel ID
SLACK_CHANNEL = os.environ.get('SLACK_CHANNEL_ID')

KEYWORDS = [
    "NLP",
    "NLP depression"
    "NLP mental health",
    "自然言語処理 メンタルヘルス",
    "LLM",
    "LLM depression"
    "AI 心理学",
    "GPT counseling",
    "言語モデル カウンセリング",
    "computational psychiatry",
    "mental health informatics",
    "NLP in healthcare",
    "NLP for mental health"
]

client = OpenAI()

slack_client = WebClient(token=SLACK_BOT_TOKEN)

DAYS_TO_LOOK_BACK = 3


def get_date_n_days_ago(n):
    return (datetime.now() - timedelta(days=n)).strftime('%Y-%m-%d')


def summarize_with_gpt(text, max_length=150):
    if not text:
        return "テキストが提供されていません"

    try:
        response = client.responses.create(
            model="o4-mini",
            messages=[
                {"role": "system", "content": "メンタルヘルスへのNLP/LLMの応用またはNLP/LLMの最新技術に関する以下のテキストを100〜150字の日本語で要約してください。重要なポイントだけを簡潔にまとめ、技術的内容があれば優先的に含めてください。"}
            ],
            max_tokens=200
        )
        return response.choices[0].message['content'].strip()
    except Exception as e:
        print(f"GPT API エラー: {e}")
        return text[:max_length] + "..."


def fetch_from_reddit():
    if not REDDIT_CLIENT_ID or not REDDIT_CLIENT_SECRET:
        return []

    try:
        reddit = praw.Reddit(
            client_id=REDDIT_CLIENT_ID,
            client_secret=REDDIT_CLIENT_SECRET,
            user_agent="PaperBot/1.0 (by /u/Initial_Sherbet_7095)"
        )

        results = []
        subreddits = ['MachineLearning', 'NLP', 'LanguageTechnology', 'psychology', 'mentalhealth', 'psychotherapy']

        for subreddit_name in subreddits:
            subreddit = reddit.subreddit(subreddit_name)

            for keyword in KEYWORDS:
                submissions = subreddit.search(keyword, time_filter='week',limit=5)

                for submission in submissions:
                    if submission.score >= 20:
                        content = submission.selftext if submission.selftext else submission.title
                        summary = summarize_with_gpt(content)

                        results.append({
                            'source': f'Reddit (r/{subreddit_name})',
                            'title': submission.title,
                            'url': f"https://www.reddit.com{submission.permalink}",
                            'summary': summary,
                            'date': datetime.fromtimestamp(submission.created_utc).strftime('%Y-%m-%d'),
                            'engagement': submission.score
                        })

        return results
    except Exception as e:
        print(f"Reddit API エラー: {e}")
        return []


def fetch_from_google():
    if not GOOGLE_API_KEY or not GOOGLE_CSE_ID:
        return []

    try:
        service = build("customsearch", "v1", developerKey=GOOGLE_API_KEY)
        results = []

        for keyword in KEYWORDS:
            search_date = get_date_n_days_ago(DAYS_TO_LOOK_BACK)

            search_results = service.cse().list(
                q=keyword,
                cx=GOOGLE_CSE_ID,
                dateRestrict=f"d{DAYS_TO_LOOK_BACK}",
                num=5
            ).execute()

            if 'items' not in search_results:
                continue

            for item in search_results['items']:
                if any(domain in item['link'] for domain in ['.edu', '.org', '.gov', 'blog.', 'news.', 'medium.com']):
                    try:
                        content = f"{item['title']} - {item.get('snippet', '')}"
                        summary = summarize_with_gpt(content)

                        results.append({
                            'source': 'Google Search',
                            'title': item['title'],
                            'url': item['link'],
                            'summary': summary,
                            'date': 'Recent'  # 正確な日付は記事自体から取得する必要がある
                        })
                    except Exception as e:
                        print(f"記事取得エラー: {e}")
        return results
    except Exception as e:
        print(f"Google API エラー: {e}")
        return []


def fetch_from_arxiv():
    try:
        results = []

        for keyword in KEYWORDS:
            search_date = get_date_n_days_ago(DAYS_TO_LOOK_BACK)
            query = f"{keyword} AND submittedDate:[{search_date} TO *]"

            url = f"http://export.arxiv.org/api/query?search_query={query.replace(' ', '+')}&sortBy=submittedDate&sortOrder=descending&max_results=10"
            feed = feedparser.parse(url)

            for entry in feed.entries:
                abstract = entry.summary.replace('\n', ' ')
                summary = summarize_with_gpt(abstract)

                results.append({
                    'source': 'arXiv',
                    'title': entry.title,
                    'url': entry.link,
                    'summary': summary,
                    'date': entry.published.split('T')[0],
                    'authors': ', '.join([author.name for author in entry.authors])
                })

        return results
    except Exception as e:
        print(f"arXiv API エラー: {e}")
        return []


def send_to_slack(items):
    if not items:
        print("送信する情報がありません")
        return

    try:
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        header = f"*【NLP・メンタルヘルス最新情報】* {now}\n"
        header += f"過去{DAYS_TO_LOOK_BACK}日間の注目情報を{len(items)}件お届けします。\n\n"

        try:
            slack_client.chat_postMessage(
                channel=SLACK_CHANNEL,
                text=header
            )
        except SlackApiError as e:
            print(f"Slackメッセージ送信エラー: {e}")

        for item in items:
            source = item['source']
            title = item['title']
            url = item['url']
            summary = item['summary']
            date = item.get('date', 'N/A')

            authors = f"\n*著者:* {item.get('authors', 'N/A')}" if 'authors' in item else ""

            message = f"*【{source}】*\n*タイトル:* <{url}|{title}>\n*日付:* {date}{authors}\n*要約:* {summary}\n\n"

            try:
                slack_client.chat_postMessage(
                    channel=SLACK_CHANNEL,
                    text=message
                )
                time.sleep(1)
            except SlackApiError as e:
                print(f"Slackメッセージ送信エラー: {e}")

    except Exception as e:
        print(f"Slack送信全般エラー: {e}")


def main():
    """メイン実行関数"""
    print("メンタルヘルスとNLPの最新情報収集を開始します...")

    reddit_items = fetch_from_reddit()
    google_items = fetch_from_google()
    arxiv_items = fetch_from_arxiv()

    print(f"Reddit: {len(reddit_items)}件")
    print(f"Google検索: {len(google_items)}件")
    print(f"arXiv: {len(arxiv_items)}件")

    all_items = reddit_items + google_items + arxiv_items

    unique_items = []
    urls = set()

    for item in all_items:
        if item['url'] not in urls:
            urls.add(item['url'])
            unique_items.append(item)


    def sort_key(item):
        engagement = item.get('engagement', 0)
        date_str = item.get('date', '1970-01-01')
        if date_str == 'Recent':
            date_str = datetime.now().strftime('%Y-%m-%d')
        try:
            date_obj = datetime.strptime(date_str, '%Y-%m-%d')
            days_ago = (datetime.now() - date_obj).days
        except:
            days_ago = 100
        return (-engagement, days_ago)

    sorted_items = sorted(unique_items, key=sort_key)

    top_items = sorted_items[:10]
    send_to_slack(top_items)

    print(f"処理完了: 合計{len(top_items)}件の情報をSlackに送信しました")


if __name__=="__main__":
    main()
