import os
import requests

SLACK_BOT_TOKEN = os.environ.get('SLACK_BOT_TOKEN')
SLACK_CHANNEL = os.environ.get('SLACK_CHANNEL_ID')

def send_test_message():
    headers = {
        "Authorization": f"Bearer {SLACK_BOT_TOKEN}",
        "Content-type": "application/json"
    }
    data = {
        "channel": SLACK_CHANNEL,
        "text": "テスト成功！"
    }

    response = requests.post("https://slack.com/api/chat.postMessage", headers=headers, json=data)
    print(response.json())


if ___name__=="__main__":
    send_test_message()