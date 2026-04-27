# say_say.py
import json
import hmac
import hashlib
import base64
import ssl
import time
import asyncio
import threading
import queue
import os
import warnings
from urllib.parse import urlencode

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
warnings.filterwarnings(
    "ignore",
    message="pkg_resources is deprecated as an API.*",
    category=UserWarning,
)

import numpy as np
import pyaudio
import websocket
import pygame
import vosk

from .dialog_service import (
    initialize_engine,
    speak,
    message,
    speak_tone,
    build_prompt,
    is_connected,
)
from . import config
from .config import logger


# === 全局队列与锁 ===
question_queue_stream = queue.Queue()
speech_lock = threading.Lock()


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


def _set_recognition_icon(mainwindow, active: bool):
    setter = getattr(mainwindow, "set_recognition_icon", None)
    if callable(setter):
        setter(active)
    elif hasattr(mainwindow, "action_button"):
        icon = mainwindow.active_icon if active else mainwindow.normal_icon
        mainwindow.action_button.setIcon(icon)


# === 识别文本清洗 ===
def clean_recognition_text(text: str) -> str:
    """
    清理实时转写造成的重复文本。
    例如：
    开封开封有哪些开封有哪些风物质文化遗产
    尽量压成：
    开封有哪些风物质文化遗产
    """
    text = text.strip()

    if not text:
        return text

    text = text.replace(" ", "").replace("\n", "").replace("\t", "")

    common_words = [
        "开封", "洛阳", "郑州", "信阳", "南阳", "安阳", "焦作",
        "许昌", "新乡", "商丘", "周口", "驻马店", "平顶山",
        "三门峡", "濮阳", "鹤壁", "漯河", "济源",
        "有哪些", "有什么", "介绍一下", "讲一下", "说一下",
        "牡丹", "非遗", "文化遗产", "风物质文化遗产", "非物质文化遗产",
    ]

    for word in common_words:
        while word + word in text:
            text = text.replace(word + word, word)

    # 处理短前缀重复
    # 例：开封开封有哪些 -> 开封有哪些
    for size in range(2, min(20, len(text) // 2) + 1):
        prefix = text[:size]
        while text.startswith(prefix + prefix):
            text = text[size:]

    return text.strip()


# === 状态封装类 ===
class RecognitionState:
    def __init__(self):
        self.websocket_connected = False
        self.recognized_text = ""
        self.segments = {}
        self.segment_counter = 0
        self.recognition_complete = False
        self.interrupt_recognition = False
        self.lock = threading.Lock()

    def update_text(self, text: str):
        """
        兼容旧逻辑。
        RTASR 尽量使用 update_segment，避免重复追加。
        """
        if not text:
            return

        with self.lock:
            self.recognized_text += text

    def update_segment(self, seg_id, text: str):
        """
        RTASR 专用。
        同一个 seg_id 的结果会覆盖，不会重复追加。
        """
        if not text:
            return

        with self.lock:
            if seg_id is None:
                seg_id = self.segment_counter
                self.segment_counter += 1

            self.segments[str(seg_id)] = text

    def get_and_clear_text(self) -> str:
        with self.lock:
            if self.segments:
                def sort_key(item):
                    key = item[0]
                    try:
                        return int(key)
                    except Exception:
                        return 999999

                text = "".join(
                    value for _, value in sorted(self.segments.items(), key=sort_key)
                ).strip()
            else:
                text = self.recognized_text.strip()

            text = clean_recognition_text(text)

            self.recognized_text = ""
            self.segments = {}
            self.segment_counter = 0

            return text

    def set_complete(self):
        with self.lock:
            self.recognition_complete = True

    def reset(self):
        with self.lock:
            self.websocket_connected = False
            self.recognized_text = ""
            self.segments = {}
            self.segment_counter = 0
            self.recognition_complete = False
            self.interrupt_recognition = False


recognition_state = RecognitionState()


# === 离线 Vosk 模型，懒加载 ===
vosk_model = None
vosk_rec = None


def ensure_vosk_loaded():
    """需要离线识别时再加载 Vosk，避免程序启动时卡住。"""
    global vosk_model, vosk_rec

    if vosk_rec is not None:
        return True

    try:
        vosk_model = vosk.Model(config.VOSK_MODEL_PATH)
        vosk_rec = vosk.KaldiRecognizer(vosk_model, 16000)
        logger.info("Vosk offline model loaded successfully")
        return True

    except Exception as e:
        logger.exception(f"Failed to load Vosk model: {e}")
        return False


# === 讯飞实时语音转写 RTASR 参数类 ===
class WsParam:
    def __init__(self, APPID: str, APIKey: str, APISecret: str = ""):
        self.APPID = APPID
        self.APIKey = APIKey
        self.APISecret = APISecret

    def create_url(self) -> str:
        """
        讯飞实时语音转写 RTASR WebSocket 鉴权。

        URL:
        wss://rtasr.xfyun.cn/v1/ws?appid=xxx&ts=xxx&signa=xxx
        """
        ts = str(int(time.time()))

        base_string = self.APPID + ts
        md5_base_string = hashlib.md5(base_string.encode("utf-8")).hexdigest()

        signa = hmac.new(
            self.APIKey.encode("utf-8"),
            md5_base_string.encode("utf-8"),
            digestmod=hashlib.sha1,
        ).digest()

        signa = base64.b64encode(signa).decode("utf-8")

        params = {
            "appid": self.APPID,
            "ts": ts,
            "signa": signa,
            "lang": "cn",
        }

        return "wss://rtasr.xfyun.cn/v1/ws?" + urlencode(params)


# === 音频采集类 ===
class AudioRecorder:
    def __init__(self):
        # 16k、16bit、单声道，每 40ms 发送 1280 字节
        self.CHUNK = 1280
        self.FORMAT = pyaudio.paInt16
        self.CHANNELS = 1
        self.RATE = 16000
        self.p = pyaudio.PyAudio()
        self.stream = None

    def start_recording(self):
        if not self.stream:
            self.stream = self.p.open(
                format=self.FORMAT,
                channels=self.CHANNELS,
                rate=self.RATE,
                input=True,
                frames_per_buffer=self.CHUNK,
            )

        logger.info("Audio recording started")

    def read_audio(self):
        if self.stream:
            return self.stream.read(self.CHUNK, exception_on_overflow=False)

        return None

    def stop_recording(self):
        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
            self.stream = None

        logger.info("Audio recording stopped")

    def terminate(self):
        self.stop_recording()

        if self.p:
            self.p.terminate()

        logger.info("Audio recorder terminated")


# === API 管理器 ===
class ApiManager:
    def __init__(self, api_configs: list[dict]):
        if not api_configs:
            raise ValueError("XF_API_CONFIGS is empty")
        self.api_configs = api_configs
        self.current_index = 0
        self.ws_param = None
        self.initialize_current_api()

    def initialize_current_api(self):
        config_data = self.api_configs[self.current_index]

        self.ws_param = WsParam(
            APPID=config_data["APPID"],
            APIKey=config_data["APIKey"],
            APISecret=config_data.get("APISecret", ""),
        )

        logger.info(
            f"Using XF RTASR API config {self.current_index + 1}/{len(self.api_configs)}"
        )

    def switch_to_next_api(self):
        self.current_index = (self.current_index + 1) % len(self.api_configs)
        self.initialize_current_api()
        return self.ws_param

    def get_current_api(self):
        return self.ws_param


api_manager = None


def get_api_manager():
    """联网时懒初始化 API 管理器。"""
    global api_manager

    if api_manager is None:
        api_manager = ApiManager(config.XF_API_CONFIGS)

    return api_manager


# === RTASR WebSocket 事件处理 ===
def parse_rtasr_result(data_str: str):
    """
    解析实时语音转写返回的 data 字段。

    返回：
    - result: 当前段文字
    - seg_id: 当前段 ID，用于避免重复追加
    """
    try:
        data = json.loads(data_str)

        seg_id = data.get("seg_id")

        cn = data.get("cn", {})
        st = cn.get("st", {})

        if seg_id is None:
            seg_id = st.get("bg")

        rt = st.get("rt", [])

        result = ""

        for item in rt:
            for ws_item in item.get("ws", []):
                for cw in ws_item.get("cw", []):
                    word = cw.get("w", "")
                    if word:
                        result += word

        return result, seg_id

    except Exception as e:
        logger.exception(f"Parse RTASR result error: {e}")
        return "", None


def on_message(ws: websocket.WebSocketApp, message: str):
    try:
        msg = json.loads(message)

        action = msg.get("action")
        code = str(msg.get("code", ""))

        if code != "0":
            logger.error(f"RTASR API error: {msg}")
            ws.api_error = True
            recognition_state.set_complete()
            ws.close()
            return

        if action == "started":
            logger.info(f"RTASR started, sid={msg.get('sid')}")
            return

        if action == "result":
            data_str = msg.get("data", "")

            if not data_str:
                return

            result, seg_id = parse_rtasr_result(data_str)

            if result:
                recognition_state.update_segment(seg_id, result)
                logger.info(f"Partial recognition segment={seg_id}: {result}")

        if action == "error":
            logger.error(f"RTASR returned error: {msg}")
            ws.api_error = True
            recognition_state.set_complete()
            ws.close()

    except Exception as e:
        logger.exception(f"Error processing RTASR WebSocket message: {e}")


def on_error(ws: websocket.WebSocketApp, error: Exception):
    logger.error(f"WebSocket error: {error}")
    ws.api_error = True
    recognition_state.set_complete()


def on_close(ws: websocket.WebSocketApp, close_status_code: int, close_msg: str):
    logger.info(f"WebSocket closed: code={close_status_code}, msg={close_msg}")
    recognition_state.websocket_connected = False
    recognition_state.set_complete()


def on_open(ws: websocket.WebSocketApp, mainwindow):
    logger.info("RTASR WebSocket connected")
    recognition_state.websocket_connected = True
    mainwindow.set_overlay_text("正在聆听···")

    def calc_volume(audio_data: bytes) -> float:
        """计算 PCM 音频音量，用于简单静音检测。"""
        if not audio_data:
            return 0.0

        samples = np.frombuffer(audio_data, dtype=np.int16)

        if samples.size == 0:
            return 0.0

        return float(np.sqrt(np.mean(samples.astype(np.float32) ** 2)))

    def run():
        recorder = AudioRecorder()

        # === 录音控制参数 ===
        max_record_seconds = 120.0      # 最长录音 2 分钟
        silence_seconds = 8.0           # 静音 8 秒自动停止
        volume_threshold = 450.0        # 环境吵就调高，太难触发就调低

        start_time = time.time()
        last_voice_time = start_time
        has_voice = False

        try:
            recorder.start_recording()

            while (
                mainwindow.recognizing
                and not mainwindow.interrupt_recognition
                and not recognition_state.interrupt_recognition
            ):
                if not ws.sock or not ws.sock.connected:
                    break

                now = time.time()

                # 最长录音 2 分钟
                if now - start_time >= max_record_seconds:
                    logger.info("RTASR reached max record seconds, stopping")
                    break

                audio_data = recorder.read_audio()

                if not audio_data:
                    continue

                volume = calc_volume(audio_data)

                if volume >= volume_threshold:
                    has_voice = True
                    last_voice_time = now

                ws.send(audio_data, opcode=websocket.ABNF.OPCODE_BINARY)

                # 已经说过话，说完后静音 8 秒自动结束
                if has_voice and now - last_voice_time >= silence_seconds:
                    logger.info("RTASR silence detected after voice, stopping")
                    break

                # 从开始就没人说话，静音 8 秒也自动结束
                if not has_voice and now - start_time >= silence_seconds:
                    logger.info("RTASR no voice detected, stopping")
                    break

                time.sleep(0.04)

        except Exception as e:
            logger.exception(f"Error in RTASR audio sending thread: {e}")

        finally:
            recorder.stop_recording()

            try:
                if ws.sock and ws.sock.connected:
                    ws.send(json.dumps({"end": True}))
                    logger.info("RTASR end flag sent")

                    # 等待服务端返回最后识别结果
                    time.sleep(1.0)

                    recognition_state.set_complete()
                    ws.close()

            except Exception as e:
                logger.exception(f"Error sending RTASR end flag: {e}")
                recognition_state.set_complete()

                try:
                    ws.close()
                except Exception:
                    pass

    threading.Thread(target=run, daemon=True).start()


# === 识别结果后处理 ===
def process_recognition_text(text: str, mainwindow):
    """统一处理替换词、唤醒、对话流程。"""
    replace_map = {
        "平武": ["苹果", "平果", "平国", "平锅", "平谷", "平故", "评估", "平菇"],
        "乡宿": ["香素", "香塑", "香诉", "香速", "香宿", "乡速", "乡素", "乡塑", "乡诉", "乡肃"],
    }

    for target, words in replace_map.items():
        for word in words:
            text = text.replace(word, target)

    text = clean_recognition_text(text)

    if not text:
        return

    logger.info(f"Final recognition: {text}")

    question_queue_stream.put(text)
    mainwindow.set_user_text(text)

    init_state = mainwindow.animation_state
    mainwindow.send_query()

    response = is_connected()

    # 唤醒流程
    if init_state == "waiting" and mainwindow.animation_state == "entrance":
        choose(response, state="hello", mainwindow=mainwindow)
        return

    # 对话流程
    if init_state != "waiting":
        try:
            choose(response, state="thinking", mainwindow=mainwindow)
            mainwindow.waiting_breath_in = True
            mainwindow.animation_state = "idle"

            prompt = build_prompt(text, mainwindow)

            if not prompt:
                mainwindow.set_model_text("没有检索到相关资料，请换个问题试试。")
                return

            start_time = time.time()

            if response:
                logger.info("Using online LLM")
                reply = message(mainwindow, prompt)
                mainwindow.set_model_text(reply)
                logger.info(f"LLM response time: {time.time() - start_time:.2f}s")
                asyncio.run(speak_tone(mainwindow, reply))

            else:
                logger.info("Using offline TTS")
                reply = message(mainwindow, prompt)
                mainwindow.set_model_text(reply)

                tts_thread = threading.Thread(
                    target=speak,
                    args=(mainwindow,),
                    daemon=True,
                )
                tts_thread.start()
                tts_thread.join()

            mainwindow.animation_state = "idle"

        except Exception as e:
            logger.exception(f"Error in dialog flow: {e}")
            error_text = f"对话流程出错：{type(e).__name__}: {e}"
            mainwindow.set_model_text(error_text)
            print(error_text, flush=True)

    while not question_queue_stream.empty():
        question_queue_stream.get()


# === 主识别函数 ===
def run_speech_loop(mainwindow):
    speech_lock.acquire()
    recognition_state.interrupt_recognition = False
    mainwindow.button = False

    accumulated_text = ""
    last_voice_time = time.time()
    silence_threshold = 1.0
    online_mode_available = bool(config.XF_API_CONFIGS)

    if is_connected() and not online_mode_available:
        logger.warning(
            "Network is available but XF API credentials are missing, "
            "fallback to offline recognition."
        )

    try:
        while mainwindow.recognizing and not recognition_state.interrupt_recognition:
            # 在线：讯飞实时语音转写
            if is_connected() and online_mode_available:
                try:
                    recognition_state.reset()

                    manager = get_api_manager()
                    ws_param = manager.get_current_api()
                    ws_url = ws_param.create_url()

                    logger.info(f"Connecting RTASR WebSocket: {ws_url}")

                    ws = websocket.WebSocketApp(
                        ws_url,
                        on_message=on_message,
                        on_error=on_error,
                        on_close=on_close,
                    )

                    ws.on_open = lambda ws_obj: on_open(ws_obj, mainwindow)
                    ws.ws_param = ws_param
                    ws.api_error = False

                    ws.run_forever(sslopt={"cert_reqs": ssl.CERT_NONE})

                    final_text = recognition_state.get_and_clear_text()

                    if final_text:
                        process_recognition_text(final_text, mainwindow)

                    if ws.api_error:
                        logger.info("Switching to next XF API config")
                        manager.switch_to_next_api()
                        time.sleep(1)

                    # 一次点击只识别一轮，静音停止后关闭麦克风
                    mainwindow.recognizing = False

                    try:
                        _set_recognition_icon(mainwindow, False)
                        mainwindow.set_overlay_text("已经停止聆听···")
                    except Exception as e:
                        logger.exception(f"Error resetting recognition button UI: {e}")

                    break

                except Exception as e:
                    logger.exception(f"Online RTASR recognition error: {e}")
                    time.sleep(1)

            # 离线：Vosk
            else:
                if not ensure_vosk_loaded():
                    logger.error("Vosk model not initialized")
                    break

                p = None
                stream = None

                try:
                    p = pyaudio.PyAudio()
                    stream = p.open(
                        format=pyaudio.paInt16,
                        channels=1,
                        rate=16000,
                        input=True,
                        frames_per_buffer=4000,
                    )

                    stream.start_stream()
                    logger.info("Offline recognition started")

                    while mainwindow.recognizing and not recognition_state.interrupt_recognition:
                        data = stream.read(4000, exception_on_overflow=False)

                        if len(data) == 0:
                            break

                        if vosk_rec.AcceptWaveform(data):
                            result = json.loads(vosk_rec.Result())
                            text = result.get("text", "")

                            if text:
                                accumulated_text += " " + text
                                last_voice_time = time.time()

                        else:
                            partial = json.loads(vosk_rec.PartialResult())
                            partial_text = partial.get("partial", "")

                            if partial_text:
                                last_voice_time = time.time()

                        silence_time = time.time() - last_voice_time

                        if silence_time > silence_threshold and accumulated_text.strip():
                            process_recognition_text(accumulated_text.strip(), mainwindow)
                            accumulated_text = ""
                            last_voice_time = time.time()

                    mainwindow.recognizing = False

                    try:
                        _set_recognition_icon(mainwindow, False)
                        mainwindow.set_overlay_text("已经停止聆听···")
                    except Exception as e:
                        logger.exception(f"Error resetting recognition button UI: {e}")

                    break

                except Exception as e:
                    logger.exception(f"Offline recognition error: {e}")

                finally:
                    if stream:
                        stream.stop_stream()
                        stream.close()

                    if p:
                        p.terminate()

    except KeyboardInterrupt:
        logger.info("Recognition interrupted by user")

    finally:
        if speech_lock.locked():
            speech_lock.release()

        logger.info("Recognition thread exited")


# === 音频播放与状态选择 ===
def play_audio(file_path: str, mainwindow, text: str = ""):
    """统一音频播放逻辑。"""
    try:
        pygame.mixer.init()
        pygame.mixer.music.load(file_path)

        if text:
            _set_model_text(mainwindow, text)

        pygame.mixer.music.play()

        while pygame.mixer.music.get_busy():
            pygame.time.Clock().tick(10)

    except Exception as e:
        logger.exception(f"Audio play error: {e}")


def choose(response: bool, state: str, mainwindow):
    """根据状态选择音频或离线 TTS。"""
    # Legacy compatibility: accept old typo state name.
    if state == "interupt":
        state = "interrupt"

    state_config = {
        "hello": (
            config.AUDIO_HELLO_PATH,
            "牡丹盛绽映春辉，国粹非遗共翠微，我是牡丹，欢迎来到河南非遗世界",
        ),
        "interrupt": (
            config.AUDIO_INTERRUPT_PATH,
            "已打断",
        ),
        "no_speak": (
            config.AUDIO_NO_SPEAK_PATH,
            "当前我没有说话",
        ),
        "brain_short": (
            config.AUDIO_BRAIN_SHORT_PATH,
            "不好意思，刚刚思绪有点乱，请您重新提问",
        ),
        "thinking": (
            config.AUDIO_THINKING_PATH,
            "请让我思考一下",
        ),
        "goodbye": (
            config.AUDIO_GOODBYE_PATH,
            "再见，欢迎您下次光临。",
        ),
    }

    audio_path, default_text = state_config.get(state, state_config["goodbye"])

    if response:
        play_audio(audio_path, mainwindow, default_text)

        if state in ["interrupt", "brain_short"]:
            _clear_model_text(mainwindow)
            _clear_user_text(mainwindow)

    else:
        engine = initialize_engine()

        try:
            _set_model_text(mainwindow, default_text)
            engine.say(default_text)
            engine.runAndWait()

        except Exception as e:
            logger.exception(f"Offline TTS error: {e}")

        finally:
            engine.stop()
            del engine


# Backward-compatible aliases for old module API names.
question_qu_stream = question_queue_stream
lock = speech_lock
Ws_Param = WsParam
speak_ = run_speech_loop
