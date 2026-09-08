import base64
import hashlib
import hmac
import json
import threading
import time
from urllib.parse import urlencode
from wsgiref.handlers import format_date_time

import pyaudio
import websocket

from .base import ASRProvider


class XfyunASR(ASRProvider):
    """
    讯飞「中英识别大模型」ASR Provider

    文档接口：
        wss://iat.xf-yun.com/v1

    输入：
        PCM
        16000 Hz
        16 bit
        单声道

    当前不启用 dwa=wpgs 动态修正，
    因此服务端返回结果按“追加”方式处理。
    """

    HOST = "iat.xf-yun.com"
    PATH = "/v1"

    RATE = 16000
    CHANNELS = 1
    BIT_DEPTH = 16

    # 官方建议：1280 字节 / 40 ms
    CHUNK = 1280
    SEND_INTERVAL = 0.04

    # 连续静音 2 秒后结束本轮识别
    EOS_MS = 2000

    def __init__(
        self,
        api_config: dict,
        *args,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)

        self.app_id = api_config["APPID"].strip()
        self.api_key = api_config["APIKey"].strip()
        self.api_secret = api_config["APISecret"].strip()

        self.ws = None

        self._done = threading.Event()
        self._text = ""

        self._seq = 0
        self._audio_thread = None

    # ---------------------------------------------------------
    # 鉴权
    # ---------------------------------------------------------

    def _create_url(self) -> str:
        date = format_date_time(time.time())

        signature_origin = (
            f"host: {self.HOST}\n"
            f"date: {date}\n"
            f"GET {self.PATH} HTTP/1.1"
        )

        signature_sha = hmac.new(
            self.api_secret.encode("utf-8"),
            signature_origin.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).digest()

        signature = base64.b64encode(
            signature_sha
        ).decode("utf-8")

        authorization_origin = (
            f'api_key="{self.api_key}", '
            f'algorithm="hmac-sha256", '
            f'headers="host date request-line", '
            f'signature="{signature}"'
        )

        authorization = base64.b64encode(
            authorization_origin.encode("utf-8")
        ).decode("utf-8")

        params = {
            "authorization": authorization,
            "date": date,
            "host": self.HOST,
        }

        return (
            f"wss://{self.HOST}{self.PATH}"
            f"?{urlencode(params)}"
        )

    # ---------------------------------------------------------
    # WebSocket callbacks
    # ---------------------------------------------------------

    def _on_open(self, ws):
        self.on_status("connected")

        self._audio_thread = threading.Thread(
            target=self._send_audio,
            daemon=True,
        )

        self._audio_thread.start()

    def _on_message(self, ws, raw_message):
        try:
            message = json.loads(raw_message)

            header = message.get("header", {})

            code = header.get("code", -1)
            status = header.get("status", -1)
            server_message = header.get("message", "")

            # 服务端报错
            if code != 0:
                self.on_status(
                    f"error:{code}:{server_message}"
                )

                self._done.set()
                ws.close()
                return

            payload = message.get("payload", {})
            result_payload = payload.get("result")

            if result_payload:
                encoded_text = result_payload.get("text")

                if encoded_text:
                    decoded_text = base64.b64decode(
                        encoded_text
                    ).decode("utf-8")

                    result_data = json.loads(decoded_text)

                    piece = self._extract_text(
                        result_data
                    )

                    if piece:
                        # 当前没有开启 dwa=wpgs，
                        # 服务端结果为追加型
                        self._text += piece

                        self.on_partial(
                            self._text.strip()
                        )

            # status == 2 表示这一轮识别结束
            if status == 2:
                final_text = self._text.strip()

                if final_text:
                    self.on_final(final_text)

                self._done.set()
                ws.close()

        except Exception as exc:
            self.on_status(
                f"error:message:{exc}"
            )

            self._done.set()

            try:
                ws.close()
            except Exception:
                pass

    def _on_error(self, ws, error):
        if not self.stop_event.is_set():
            self.on_status(
                f"error:websocket:{error}"
            )

        self._done.set()

    def _on_close(
        self,
        ws,
        close_status_code,
        close_msg,
    ):
        self._done.set()

    # ---------------------------------------------------------
    # 解析识别文本
    # ---------------------------------------------------------

    @staticmethod
    def _extract_text(result_data: dict) -> str:
        text = ""

        for word_segment in result_data.get("ws", []):
            candidates = word_segment.get("cw", [])

            if not candidates:
                continue

            # 通常第一个候选就是最佳结果
            word = candidates[0].get("w", "")

            text += word

        return text

    # ---------------------------------------------------------
    # 音频数据包
    # ---------------------------------------------------------

    def _next_seq(self) -> int:
        self._seq += 1
        return self._seq

    def _first_packet(self, audio: str) -> dict:
        return {
            "header": {
                "app_id": self.app_id,
                "status": 0,
            },

            "parameter": {
                "iat": {
                    "domain": "slm",
                    "language": "zh_cn",
                    "accent": "mandarin",

                    # 静音多久认为说完
                    "eos": self.EOS_MS,

                    # 暂时不开 dwa=wpgs
                    # 因为开启后需要处理替换结果
                    "result": {
                        "encoding": "utf8",
                        "compress": "raw",
                        "format": "json",
                    },
                }
            },

            "payload": {
                "audio": {
                    "encoding": "raw",
                    "sample_rate": self.RATE,
                    "channels": self.CHANNELS,
                    "bit_depth": self.BIT_DEPTH,
                    "seq": self._next_seq(),
                    "status": 0,
                    "audio": audio,
                }
            },
        }

    def _middle_packet(self, audio: str) -> dict:
        return {
            "header": {
                "app_id": self.app_id,
                "status": 1,
            },

            "payload": {
                "audio": {
                    "encoding": "raw",
                    "sample_rate": self.RATE,
                    "channels": self.CHANNELS,
                    "bit_depth": self.BIT_DEPTH,
                    "seq": self._next_seq(),
                    "status": 1,
                    "audio": audio,
                }
            },
        }

    def _last_packet(self) -> dict:
        return {
            "header": {
                "app_id": self.app_id,
                "status": 2,
            },

            "payload": {
                "audio": {
                    "encoding": "raw",
                    "sample_rate": self.RATE,
                    "channels": self.CHANNELS,
                    "bit_depth": self.BIT_DEPTH,
                    "seq": self._next_seq(),
                    "status": 2,
                    "audio": "",
                }
            },
        }

    # ---------------------------------------------------------
    # 麦克风
    # ---------------------------------------------------------

    def _send_audio(self):
        audio = pyaudio.PyAudio()
        stream = None

        try:
            stream = audio.open(
                format=pyaudio.paInt16,
                channels=self.CHANNELS,
                rate=self.RATE,
                input=True,
                frames_per_buffer=self.CHUNK,
            )

            stream.start_stream()

            self.on_status("listening")

            first_frame = True

            while (
                not self.stop_event.is_set()
                and not self._done.is_set()
            ):
                data = stream.read(
                    self.CHUNK,
                    exception_on_overflow=False,
                )

                encoded_audio = base64.b64encode(
                    data
                ).decode("utf-8")

                if first_frame:
                    packet = self._first_packet(
                        encoded_audio
                    )

                    first_frame = False

                else:
                    packet = self._middle_packet(
                        encoded_audio
                    )

                if (
                    self.ws
                    and self.ws.sock
                    and self.ws.sock.connected
                ):
                    self.ws.send(
                        json.dumps(packet)
                    )
                else:
                    break

                time.sleep(self.SEND_INTERVAL)

        except Exception as exc:
            if not self.stop_event.is_set():
                self.on_status(
                    f"error:audio:{exc}"
                )

        finally:
            if stream is not None:
                try:
                    stream.stop_stream()
                    stream.close()
                except Exception:
                    pass

            audio.terminate()

            # 用户主动 stop 时，
            # 给服务器发送最后一帧，
            # 让它把剩余文字返回出来。
            if (
                not self._done.is_set()
                and self.ws
                and self.ws.sock
                and self.ws.sock.connected
            ):
                try:
                    self.ws.send(
                        json.dumps(
                            self._last_packet()
                        )
                    )
                except Exception:
                    pass

    # ---------------------------------------------------------
    # Provider interface
    # ---------------------------------------------------------

    def run(self) -> None:
        self.stop_event.clear()
        self._done.clear()

        self._text = ""
        self._seq = 0

        self.on_status("connecting")

        self.ws = websocket.WebSocketApp(
            self._create_url(),
            on_open=self._on_open,
            on_message=self._on_message,
            on_error=self._on_error,
            on_close=self._on_close,
        )

        try:
            self.ws.run_forever()
        finally:
            self._done.set()
            self.on_status("stopped")

    def stop(self) -> None:
        """
        请求停止。

        不立即关闭 WebSocket：
        先让音频线程发送 status=2 的最后一帧，
        等讯飞返回最终识别结果。
        """
        super().stop()

        self._done.set()
        try:
            if self.ws:
                self.ws.close()
        except Exception:
            pass

        # 如果服务器迟迟没有正常结束，
        # 两秒后强制关闭 WebSocket。
        def force_close():
            if not self._done.wait(timeout=2.0):
                try:
                    if self.ws:
                        self.ws.close()
                except Exception:
                    pass

        threading.Thread(
            target=force_close,
            daemon=True,
        ).start()
