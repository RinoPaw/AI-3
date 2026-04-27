import edge_tts
import pygame
import tempfile
import time
import asyncio
import jieba
import re

async def speak_tone(text : str):
    start_time = time.time()
    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp:
        output_path = tmp.name
    
    # 使用 edge-tts 合成语音
    communicate = edge_tts.Communicate(text, "zh-CN-YunxiaNeural")
    await communicate.save(output_path)

    # 初始化 pygame 播放器
    pygame.mixer.init()
    pygame.mixer.music.load(output_path)
    pygame.mixer.music.play()

# 等待播放结束
    while pygame.mixer.music.get_busy():
        time.sleep(0.1)

def clean_text(text : str):
        # 定义中文和英文标点符号的正则表达式
    # 中文标点符号：。，、；：？！「」『』（）《》【】…—～
    # 英文标点符号：.,;:?!()[]{}-~'"/
    punctuation_pattern = r'[\u3000-\u303f\uff00-\uffef\u2000-\u206f\u2e00-\u2e7f\s,\.;:?!\(\)\[\]\{\}\-\~\'\"\/]'
    
    # 使用正则表达式替换标点符号为空字符串
    cleaned_text = re.sub(punctuation_pattern, '', text)
        # 去除多余空格
    cleaned_text = re.sub(r'\s+', ' ', cleaned_text)
    # 去除首尾空格
    cleaned_text = cleaned_text.strip()
    return cleaned_text


if __name__ == "__main__":
    text = "你好，我是熊猫田田，请给我详细介绍一下品无线按附件安抚了数个苏沪高速喀湖是给试试看韩国如果还"
    text = clean_text(text)
    text = jieba.lcut(text)
    print(text)
    for i in text:
        asyncio.run(speak_tone(i))