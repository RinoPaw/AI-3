import asyncio
import edge_tts
import pygame
import io
import logging
from typing import Optional
from random import choice
import os
# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class AudioSynthesizer:
    def __init__(self):
        """初始化音频合成器"""
        pygame.mixer.init()
        self.available_voices = {
            "云霞": "zh-CN-YunxiaNeural",
            "云希": "zh-CN-YunxiNeural",
            "晓晓": "zh-CN-XiaoxiaoNeural",
            "晓伊": "zh-CN-XiaoyiNeural",
        }

    async def synthesize(self, text: str, voice_name: str = "云霞", output_file: Optional[str] = None) -> bool:
        """
        合成语音
        
        参数:
            text (str): 要合成的文本
            voice_name (str): 语音名称，默认为"云霞"
            output_file (Optional[str]): 输出文件路径，如果为None则直接播放
            
        返回:
            bool: 合成是否成功
        """
        try:
            # 获取语音ID
            voice_id = self.available_voices.get(voice_name)
            if not voice_id:
                logger.error(f"未找到语音: {voice_name}")
                return False

            # logger.info(f"开始合成语音: {text}")
            # logger.info(f"使用语音: {voice_name} ({voice_id})")

            # 创建edge_tts通信对象
            communicate = edge_tts.Communicate(text, voice_id)

            if output_file:
                # 保存到文件
                await communicate.save(output_file)
                # logger.info(f"语音已保存到: {output_file}")
            else:
                # 直接播放
                audio_stream = io.BytesIO()
                
                # 获取音频数据
                async for chunk in communicate.stream():
                    if chunk["type"] == "audio":
                        audio_stream.write(chunk["data"])
                
                # 重置流位置
                audio_stream.seek(0)
                
                # 播放音频
                pygame.mixer.music.load(audio_stream)
                pygame.mixer.music.play()
                
                # 等待播放完成
                while pygame.mixer.music.get_busy():
                    await asyncio.sleep(0.1)
                
                logger.info("语音播放完成")

            return True

        except Exception as e:
            logger.exception(f"语音合成失败: {e}")
            return False

    def get_available_voices(self) -> dict:
        """获取可用的语音列表"""
        return self.available_voices

async def main():
    """示例用法"""
    synthesizer = AudioSynthesizer()
    list_data = list(synthesizer.get_available_voices().keys())
    
    # 示例1：直接播放
    # await synthesizer.synthesize("你好，我是熊猫田田")
    # with open("./data/final_result_input.txt", 'r', encoding='utf-8') as f:
    #     count = 0
    #     if not os.path.exists("./assets/audio/sovice_question"):
    #         os.makedirs("./assets/audio/sovice_question")
    #     for line in f.readlines():
    #         # 示例2：保存到文件
    #         name = choice(list_data)
    #         print(f"正在合成第{count}条数据")
    #         count += 1
    #         await synthesizer.synthesize(
    #             line,
    #             voice_name=name,
    #             output_file=f"./assets/audio/sovice_question/thinking_question_{count}.mp3"
    #         )
    await synthesizer.synthesize(
                "已打断",
                voice_name="晓晓",
                output_file=f"assets/audio/interupt.mp3"
            )

if __name__ == "__main__":
    asyncio.run(main()) 
