# say.py
import asyncio
import io
import json
import os
import queue
import re
import tempfile
import threading
import time
import warnings

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
warnings.filterwarnings(
    "ignore",
    message="pkg_resources is deprecated as an API.*",
    category=UserWarning,
)
warnings.filterwarnings("ignore", category=SyntaxWarning)

import edge_tts
import pygame
import pyttsx3
import requests
from zhipuai import ZhipuAI

from . import config
from .config import logger


# === 基础配置 ===
welcome_message = "大家好，我是河南非遗数字讲解员牡丹"
goodbye_message = "拜拜呀，有问题来找我哦"

AUDIO_RATE = 16000
AUDIO_CHANNELS = 1
CHUNK = 4000
NO_SPEECH_THRESHOLD = 3

SUMMARY_PATH = config.resource_path("data/faiss_data/summary/summary_final.json")

headers = {
    "user-agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/134.0.0.0 Safari/537.36 Edg/134.0.0.0"
    )
}

text_queue = queue.Queue()


_faiss_db = None
summary = None


def get_summary() -> dict:
    """Load summary metadata without initializing the embedding model."""
    global summary

    if summary is None:
        try:
            with open(SUMMARY_PATH, mode="r", encoding="utf-8") as f:
                summary = json.load(f)
        except FileNotFoundError:
            logger.warning(f"Summary file does not exist: {SUMMARY_PATH}")
            summary = {}
        except Exception as e:
            logger.exception(f"Failed to load summary file: {e}")
            summary = {}

    return summary


def get_faiss_db():
    """Lazily initialize FAISS so the desktop UI can start quickly."""
    global _faiss_db, summary

    if _faiss_db is None:
        logger.info("Initializing FAISS vector store")
        from .vector_store import FaissVectorStore

        _faiss_db = FaissVectorStore(
            model_path=config.EMBEDDING_MODEL_PATH,
            index_path=config.FAISS_INDEX_PATH,
            json_path=config.FAISS_DATA_PATH,
        )
        get_summary()

    return _faiss_db


def is_connected():
    """检测网络是否可用。"""
    try:
        response = requests.get(
            url="https://www.baidu.com",
            headers=headers,
            timeout=2,
        )
        return response.status_code == 200
    except Exception as e:
        logger.exception(f"Check network error: {e}")
        return False


def split_sentences(text: str) -> list[str]:
    """
    把大模型回答拆成适合 TTS 朗读的短句。
    """
    text = text.replace("*", "").strip()

    if not text:
        return []

    parts = re.split(r"([。！？!?；;])", text)

    sentences = []
    buffer = ""

    for part in parts:
        if not part:
            continue

        buffer += part

        if part in "。！？!?；;":
            sentence = buffer.strip()
            if sentence:
                sentences.append(sentence)
            buffer = ""

    if buffer.strip():
        sentences.append(buffer.strip())

    return sentences


def _set_model_text(mainwindow, text: str):
    setter = getattr(mainwindow, "set_model_text", None)
    if callable(setter):
        setter(text)
    elif hasattr(mainwindow, "model_bubble"):
        mainwindow.model_bubble.setText(text)


def _clear_model_text(mainwindow):
    clearer = getattr(mainwindow, "clear_model_text", None)
    if callable(clearer):
        clearer()
    elif hasattr(mainwindow, "model_bubble"):
        mainwindow.model_bubble.clear()


def _clear_user_text(mainwindow):
    clearer = getattr(mainwindow, "clear_user_text", None)
    if callable(clearer):
        clearer()
    elif hasattr(mainwindow, "user_bubble"):
        mainwindow.user_bubble.clear()


async def speak_tone(self, text: str):
    """
    使用 edge_tts 生成语音并播放。
    在线模式使用。
    """
    start_time = time.time()
    logger.info("Speak tone is starting")

    output_path = None

    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp:
            output_path = tmp.name

        communicate = edge_tts.Communicate(text, "zh-CN-XiaoxiaoNeural")
        await communicate.save(output_path)

        self.animation_state = "speaking"

        pygame.mixer.init()
        logger.info(f"speak_tone generate audio time: {time.time() - start_time:.2f}s")

        pygame.mixer.music.load(output_path)
        pygame.mixer.music.play()

        while pygame.mixer.music.get_busy():
            await asyncio.sleep(0.1)

        logger.info("Speak tone completed")

    except Exception as e:
        logger.exception(f"Speak tone error: {e}")
        choose(True, state="brain_short", mainwindow=self)

    finally:
        if output_path and os.path.exists(output_path):
            try:
                os.remove(output_path)
            except Exception as e:
                logger.warning(f"Failed to remove temporary audio file: {e}")


async def speak_tone_no(self, text: str):
    """
    使用 edge_tts 生成语音并直接播放。
    用于不切换 speaking 动画的短提示。
    """
    logger.info("Speak tone no is starting")

    try:
        communicate = edge_tts.Communicate(text, "zh-CN-XiaoxiaoNeural")
        audio_stream = io.BytesIO()

        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_stream.write(chunk["data"])

        audio_stream.seek(0)

        pygame.mixer.init()
        pygame.mixer.music.load(audio_stream)
        pygame.mixer.music.play()

        while pygame.mixer.music.get_busy():
            await asyncio.sleep(0.1)

        logger.info("Speak tone no completed")

        _clear_model_text(self)
        _clear_user_text(self)

    except Exception as e:
        logger.exception(f"Speak tone no error: {e}")
        choose(True, state="brain_short", mainwindow=self)


def initialize_engine():
    """
    初始化 pyttsx3 离线 TTS 引擎。
    """
    logger.info("Initialize engine is starting")

    try:
        engine = pyttsx3.init()

        if not engine:
            logger.warning("Failed to initialize engine")
            return None

        logger.info("Initialize engine successfully")

        engine.setProperty("rate", 200)
        logger.info("Set rate: 200")

        voices = engine.getProperty("voices")
        logger.info(f"Available voices: {len(voices)}")

        chinese_voice_found = False

        for voice in voices:
            logger.info(f"Check voice: {voice.id}")

            if "ZH" in voice.id.upper() or "CHINESE" in voice.id.upper():
                engine.setProperty("voice", voice.id)
                logger.info(f"Set Chinese voice: {voice.id}")
                chinese_voice_found = True
                break

        if not chinese_voice_found:
            logger.warning("Chinese voice not found, using default voice")

        return engine

    except Exception as e:
        logger.exception(f"Initialize engine error: {e}")
        return None


def speak(self):
    """
    离线 TTS 朗读 text_queue 里的句子。
    """
    try:
        if self.engine:
            self.engine.stop()

            try:
                self.engine.endLoop()
            except Exception:
                logger.info("loop not start")

            del self.engine
            self.engine = None

        self.engine = initialize_engine()

        if not self.engine:
            logger.warning("Initialize engine failed")
            return

        self.animation_state = "speaking"

        while True:
            try:
                text = text_queue.get(timeout=0.1)

                if text is None:
                    logger.info("Received end signal")
                    break

                logger.info(f"Read: {text}")
                self.engine.say(text)
                self.engine.runAndWait()
                logger.info("Read completed")

            except queue.Empty:
                logger.info("Queue is empty, continue waiting")
                break

            except Exception as e:
                logger.exception(f"Error processing text: {e}")
                break

    finally:
        if self.engine:
            self.engine.stop()

            try:
                self.engine.endLoop()
            except Exception:
                logger.info("loop not start")

            del self.engine
            self.engine = None

        self.animation_state = "idle"
        logger.info("Engine released")


def build_prompt(question: str, mainwindow):
    """
    从 FAISS 检索相关非遗资料，并构造给大模型的 prompt。
    """
    faiss_db = get_faiss_db()
    results = faiss_db.query(question, n_results=2)
    context = "\n\n".join(results["documents"]) if results["documents"] else ""

    logger.info(f"Retrieved Context: {context}")

    if not context.strip():
        choose(True, state="no_retrival", mainwindow=mainwindow)
        return False

    return f"""
下面是你的资料库记忆。请你只根据这些资料回答用户问题，不要编造，不要反问用户。

【资料库记忆】
{context}

【用户问题】
{question}

【回答要求】
1. 你是河南非遗数字讲解员“牡丹”。
2. 回答要自然、简洁、适合语音播报。
3. 尽量控制在 150 字以内。
4. 如果资料里没有答案，就说“暂时没有查到相关资料”。
"""


def choose(response: bool, state: str, mainwindow):
    """
    根据状态播放预设音频或显示提示。
    """
    # Legacy compatibility: accept old typo state name.
    if state == "interupt":
        state = "interrupt"

    if response:
        pygame.mixer.init()

        if state == "hello":
            _set_model_text(
                mainwindow,
                "牡丹盛绽映春辉，国粹非遗共翠微，我是牡丹，欢迎来到河南非遗世界"
            )
            pygame.mixer.music.load(config.AUDIO_HELLO_PATH)

        elif state == "interrupt":
            _set_model_text(mainwindow, "已打断")
            pygame.mixer.music.load(config.AUDIO_INTERRUPT_PATH)

        elif state == "no_speak":
            _set_model_text(mainwindow, "当前我没有说话")
            pygame.mixer.music.load(config.AUDIO_NO_SPEAK_PATH)

        elif state == "brain_short":
            _set_model_text(mainwindow, "不好意思，刚刚思绪有点乱，请您重新提问")
            pygame.mixer.music.load(config.AUDIO_BRAIN_SHORT_PATH)

        elif state == "thinking":
            _set_model_text(mainwindow, "请让我思考一下")
            pygame.mixer.music.load(config.AUDIO_THINKING_PATH)

        elif state == "no_retrival":
            _set_model_text(mainwindow, "你所问的问题我当前不太清楚")
            pygame.mixer.music.load(config.AUDIO_NO_RETRIVAL_PATH)

        else:
            _set_model_text(mainwindow, "再见，欢迎您下次光临。")
            pygame.mixer.music.load(config.AUDIO_GOODBYE_PATH)

        pygame.mixer.music.play()

        while pygame.mixer.music.get_busy():
            pygame.time.Clock().tick(10)

        if state in ["interrupt", "brain_short", "no_retrival"]:
            _clear_model_text(mainwindow)
            logger.info("Say, Model bubble is cleared, state: %s", state)

            _clear_user_text(mainwindow)
            logger.info("Say, User bubble is cleared, state: %s", state)

    else:
        engine = initialize_engine()

        if not engine:
            return

        try:
            if state == "hello":
                text = "牡丹盛绽映春辉，国粹非遗共翠微，我是牡丹，欢迎来到河南非遗世界"
            elif state == "interrupt":
                text = "已打断"
            elif state == "no_speak":
                text = "当前我没有说话"
            elif state == "brain_short":
                text = "不好意思，刚刚思绪有点乱，请您重新提问"
            elif state == "thinking":
                text = "请让我思考一下"
            elif state == "no_retrival":
                text = "你所问的问题我当前不太清楚"
            else:
                text = "再见，欢迎您下次光临。"

            _set_model_text(mainwindow, text)
            engine.say(text)
            engine.runAndWait()

        except Exception as e:
            logger.exception(f"Offline choose TTS error: {e}")

        finally:
            engine.stop()
            del engine


def message(self, problem: str) -> str:
    """
    调用智谱大模型生成回答。

    self: MainWindow
    problem: build_prompt() 生成的完整 prompt
    """
    # 清空旧的离线朗读队列，避免上一次残留
    while not text_queue.empty():
        try:
            text_queue.get_nowait()
        except queue.Empty:
            break

    api_key = getattr(config, "ZHIPU_API_KEY", "")
    model_name = getattr(config, "ZHIPU_MODEL", "glm-4.5-flash")

    if not api_key:
        error_text = "智谱 API Key 还没有配置，请先设置 ZHIPU_API_KEY。"
        logger.error(error_text)
        text_queue.put(error_text)
        text_queue.put(None)
        return error_text

    try:
        client = ZhipuAI(api_key=api_key)

        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "你是河南非遗数字讲解员牡丹。"
                        "请严格根据提供的资料回答，不要编造。"
                        "回答要自然、简洁、适合语音播报。"
                        "如果资料里没有答案，就说暂时没有查到相关资料。"
                        "除专有名词、人名、地名外，请尽量使用中文表达。"
                    ),
                },
                {
                    "role": "user",
                    "content": problem,
                },
            ],
            temperature=0.2,
            top_p=0.8,
            max_tokens=800,
            stream=False,
        )

        reply = response.choices[0].message.content.strip()
        reply = reply.replace("*", "")

        if not reply:
            reply = "暂时没有生成有效回答，请换个问题试试。"

        logger.info(f"ZhipuAI reply: {reply}")

        for sentence in split_sentences(reply):
            text_queue.put(sentence)
            logger.info(f"sentence is {sentence}")

        text_queue.put(None)

        return reply

    except Exception as e:
        logger.exception(f"Error during ZhipuAI request: {e}")

        error_text = f"智谱 API 调用失败：{type(e).__name__}: {e}"
        text_queue.put(error_text)
        text_queue.put(None)

        return error_text


if __name__ == "__main__":
    while True:
        try:
            problem = input("Please enter your question: ")

            class DummyWindow:
                engine = None
                animation_state = "idle"

                class Bubble:
                    def setText(self, text):
                        print(text)

                    def clear(self):
                        pass

                model_bubble = Bubble()
                user_bubble = Bubble()

            dummy_window = DummyWindow()
            prompt = build_prompt(problem, dummy_window)

            if not prompt:
                continue

            if is_connected():
                logger.info("Using online LLM and online TTS")
                reply_text = message(dummy_window, prompt)
                print("回答：", reply_text)
                asyncio.run(speak_tone(dummy_window, reply_text))
            else:
                logger.info("Using offline TTS")
                message(dummy_window, prompt)
                tts_thread = threading.Thread(target=speak, args=(dummy_window,))
                tts_thread.start()
                tts_thread.join()

        except KeyboardInterrupt:
            text_queue.put(None)
            break

        except Exception:
            logger.exception("It has something error!!!")


# Canonical function names with backward-compatible aliases.
speak_online_tts = speak_tone
speak_online_prompt_tts = speak_tone_no
speak_offline_queue = speak
build_rag_prompt = build_prompt
play_state_feedback = choose
generate_reply = message
