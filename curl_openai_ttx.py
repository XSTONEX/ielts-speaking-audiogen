import os
import requests
import json
from datetime import datetime
from dotenv import load_dotenv
load_dotenv()

url = "https://api.deerapi.com/v1/audio/speech"

# strs = """
# Well, I’d like to talk about a really unusual and interesting temple called Zhusheng Temple, which is located in Guilin, a beautiful city in Guangxi Province, China. I haven’t been there myself yet, but I saw some photos online and also heard about it from a friend who studied in Guilin.
# """

# strs = """
# What makes this temple really unusual is that it’s hidden inside a natural cave, unlike most temples that are built above the ground.
# There’s only a small incense-burning spot outside, but once you walk into the cave, it’s like stepping into a different world.
# My friend told me it’s a bit chilly and super quiet inside, and the whole cave gives off a spiritual and mysterious feeling.
# The most amazing part is a long corridor with hundreds of small Buddha statues carved along the wall, and some of them are even three or four meters tall! It really blew my mind just looking at the photos. I can’t imagine how impressive it must feel to be there in person.
# """

strs = """
The temple isn’t very well-known, which makes me even more curious about it. It’s like a hidden gem that not many people talk about. That’s why I’d love to visit it one day—to experience the peaceful vibe, see the cave art with my own eyes, and maybe reflect a little on life. So yeah, Zhusheng Temple is definitely one of the most unusual and interesting buildings I’d like to visit.
"""

payload = json.dumps({
   "model": "tts-1",
   "input": strs,
   "voice": "nova"
})
headers = {
   'Authorization': f'Bearer {os.getenv("DEER_API_KEY")}',
   'Content-Type': 'application/json'
}

response = requests.request("POST", url, headers=headers, data=payload)

# 从响应中获取音频数据
audio_data = response.content

# 生成带时间戳的文件名
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
lesson_name = "P2-unusual_building"
os.makedirs(lesson_name, exist_ok=True)
filename = f"{lesson_name}_{timestamp}.mp3"

# 将音频数据保存到文件
with open(f"{lesson_name}/{filename}", 'wb') as f:
    f.write(audio_data)

print(f"音频文件已保存为: {filename}")