import pygame
from pathlib import Path
import os
import time

def loop_play(file_path):
    pygame.mixer.init()
    pygame.mixer.music.load(file_path)
    pygame.mixer.music.play()

if __name__ == "__main__":
    start_time = time.time()
    mp3_filename = Path('utils/sovice_question')
    print(mp3_filename)
    mp3_list = list(mp3_filename.glob('*.mp3'))
    for mp3_ in  mp3_list:
        try:
            loop_play(mp3_)
            time.sleep(60)
        except Exception as e:
            print(e)
            continue
    end_time = time.time()
    print(f"程序运行时间: {end_time - start_time} 秒")

