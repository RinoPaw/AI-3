from __future__ import annotations

import asyncio
import queue
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from boot_timing import boot_log

boot_log("before av")
import av
boot_log("after av")

import edge_tts

boot_log("before pygame (say)")
import pygame
boot_log("after pygame (say)")

boot_log("before sounddevice")
import sounddevice as sd
boot_log("after sounddevice")

from openai import OpenAI

import config
from config import logger
from faiss_db import FaissDB


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

TTS_VOICE = "zh-CN-XiaoxiaoNeural"
_FIRST_SENTENCE_BOUNDARIES = "。！？；\n"
_PCM_END = object()


# ---------------------------------------------------------------------------
# RAG
# ---------------------------------------------------------------------------

faiss_db = FaissDB(
    model_path=config.EMBEDDING_MODEL_PATH,
    index_path=config.FAISS_INDEX_PATH,
    jsonl_path=config.JSONL_DATA_PATH,
)
boot_log("RAG initialized")


def build_prompt(question: str, mainwindow) -> str | bool:
    """Retrieve relevant memories and build the LLM prompt."""
    rag_start = time.perf_counter()
    logger.info("[PERF] RAG start")

    results = faiss_db.query(question, n_results=2)
    documents = results.get("documents") or []
    context = "\n".join(documents)

    logger.info(
        "[PERF] RAG done: %.3fs",
        time.perf_counter() - rag_start,
    )
    logger.info("[PERF] Context size: %d chars", len(context))
    logger.debug("Retrieved context: %s", context)

    if not context.strip():
        choose(True, state="no_retrival", mainwindow=mainwindow)
        return False

    prompt = (
        '下面的"记忆"是你的记忆，请你根据你的记忆回答问题，不要反问我。\n'
        f"记忆: {context}\n"
        f"问题: {question}"
    )
    logger.info("[PERF] Prompt size: %d chars", len(prompt))
    return prompt


# ---------------------------------------------------------------------------
# Pre-recorded status audio
# ---------------------------------------------------------------------------


def _preset_audio(state: str) -> tuple[str, str]:
    presets = {
        "hello": (
            "牡丹盛绽映春辉，国粹非遗共翠微，我是牡丹，欢迎来到河南非遗世界",
            config.AUDIO_HELLO_PATH,
        ),
        "interupt": ("已打断", config.AUDIO_INTERUPT_PATH),
        "no_speak": ("当前我没有说话", config.AUDIO_NO_SPEAK_PATH),
        "brain_short": (
            "不好意思，刚刚思绪有点乱，请您重新提问",
            config.AUDIO_BRAIN_SHORT_PATH,
        ),
        # Kept for compatibility with callers that have not removed the old state.
        # The normal question path should not use it.
        "thinking": ("请让我思考一下", config.AUDIO_THINKING_PATH),
        "no_retrival": (
            "你所问的问题我当前不太清楚",
            config.AUDIO_NO_RETRIVAL_PATH,
        ),
        "goodbye": ("再见，欢迎您下次光临。", config.AUDIO_GOODBYE_PATH),
    }
    return presets.get(state, presets["goodbye"])


def choose(response: bool, state: str, mainwindow) -> None:
    """Play one short pre-recorded status clip synchronously."""
    if not response:
        return

    text, audio_path = _preset_audio(state)
    mainwindow.set_model_text_threadsafe(text)

    if not pygame.mixer.get_init():
        pygame.mixer.init()

    pygame.mixer.music.load(audio_path)
    pygame.mixer.music.play()

    while pygame.mixer.music.get_busy():
        pygame.time.Clock().tick(20)

    if state in {"interupt", "brain_short", "no_retrival"}:
        mainwindow.clear_bubbles_threadsafe()
        logger.info("Say bubbles cleared, state: %s", state)


# ---------------------------------------------------------------------------
# TTS session lifecycle
# ---------------------------------------------------------------------------


@dataclass
class _SpeechSession:
    cancel_event: threading.Event = field(default_factory=threading.Event)
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _stream: Any = None
    _loop: asyncio.AbstractEventLoop | None = None
    _tasks: set[asyncio.Task] = field(default_factory=set)
    error: BaseException | None = None

    @property
    def cancelled(self) -> bool:
        return self.cancel_event.is_set()

    def attach_stream(self, stream) -> bool:
        with self._lock:
            if self.cancelled:
                return False
            self._stream = stream
            return True

    def clear_stream(self, stream) -> None:
        with self._lock:
            if self._stream is stream:
                self._stream = None

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        with self._lock:
            self._loop = loop

    def register_task(self, task: asyncio.Task) -> None:
        with self._lock:
            self._tasks.add(task)
        task.add_done_callback(self._discard_task)

    def _discard_task(self, task: asyncio.Task) -> None:
        with self._lock:
            self._tasks.discard(task)

    def set_error(self, exc: BaseException) -> None:
        with self._lock:
            if self.error is None:
                self.error = exc

    def cancel(self) -> None:
        self.cancel_event.set()

        with self._lock:
            stream = self._stream
            loop = self._loop
            tasks = tuple(self._tasks)

        if stream is not None:
            try:
                stream.abort()
            except Exception:
                logger.debug("TTS stream was already stopped", exc_info=True)

        if loop is not None and not loop.is_closed():
            for task in tasks:
                if not task.done():
                    try:
                        loop.call_soon_threadsafe(task.cancel)
                    except RuntimeError:
                        break


_active_session_lock = threading.Lock()
_active_session: _SpeechSession | None = None


def _begin_session() -> _SpeechSession:
    global _active_session

    session = _SpeechSession()
    with _active_session_lock:
        previous = _active_session
        _active_session = session

    if previous is not None:
        previous.cancel()

    return session


def _finish_session(session: _SpeechSession) -> None:
    global _active_session

    with _active_session_lock:
        if _active_session is session:
            _active_session = None


def stop_speaking() -> None:
    """Stop the current Edge-TTS request and audio output immediately."""
    with _active_session_lock:
        session = _active_session

    if session is not None:
        session.cancel()


def is_tts_playing() -> bool:
    """Return True while a TTS session is requesting, buffering, or playing."""
    with _active_session_lock:
        session = _active_session
    return session is not None and not session.cancelled


# Current MainWindow still clears this queue on interrupt.  The active Edge-TTS
# pipeline does not use it; keeping the object preserves that public interface.
text_queue: queue.Queue = queue.Queue()


# ---------------------------------------------------------------------------
# TTS transport: Edge MP3 -> decoded PCM queues -> one audio output stream
# ---------------------------------------------------------------------------

_output_rate_lock = threading.Lock()
_output_rate: int | None = None


def _get_output_rate() -> int:
    global _output_rate

    with _output_rate_lock:
        if _output_rate is None:
            device = sd.query_devices(kind="output")
            _output_rate = int(device["default_samplerate"])
        return _output_rate


def _pcm_bytes(frame) -> bytes:
    # All frames are mono signed 16-bit PCM after resampling.
    return bytes(frame.planes[0])[: frame.samples * 2]


def _queue_put_end(pcm_queue: queue.Queue) -> None:
    pcm_queue.put(_PCM_END)


async def _edge_to_pcm_queue(
    text: str,
    pcm_queue: queue.Queue,
    session: _SpeechSession,
    *,
    label: str,
) -> None:
    """Stream one Edge-TTS request into a PCM queue without playing it."""
    start_time = time.perf_counter()
    first_audio_time: float | None = None
    audio_bytes = 0

    if not text or not text.strip():
        _queue_put_end(pcm_queue)
        return

    logger.info("[PERF] TTS %s request start: %s", label, text)

    output_rate = _get_output_rate()
    decoder = av.CodecContext.create("mp3", "r")
    resampler = av.AudioResampler(
        format="s16",
        layout="mono",
        rate=output_rate,
    )

    def push_frame(frame) -> None:
        for pcm_frame in resampler.resample(frame):
            if session.cancelled:
                return
            pcm_queue.put(_pcm_bytes(pcm_frame))

    try:
        communicate = edge_tts.Communicate(text, TTS_VOICE)

        async for chunk in communicate.stream():
            if session.cancelled:
                break
            if chunk.get("type") != "audio":
                continue

            data = chunk["data"]
            audio_bytes += len(data)

            if first_audio_time is None:
                first_audio_time = time.perf_counter() - start_time
                if label == "first":
                    logger.info("TTS first audio: %.3fs", first_audio_time)
                else:
                    logger.info(
                        "[PERF] TTS remaining first audio: %.3fs",
                        first_audio_time,
                    )

            for packet in decoder.parse(data):
                for frame in decoder.decode(packet):
                    push_frame(frame)

        if not session.cancelled:
            for packet in decoder.parse(b""):
                for frame in decoder.decode(packet):
                    push_frame(frame)

            for frame in decoder.decode(None):
                push_frame(frame)

            for pcm_frame in resampler.resample(None):
                if session.cancelled:
                    break
                pcm_queue.put(_pcm_bytes(pcm_frame))

        elapsed = time.perf_counter() - start_time
        if session.cancelled:
            logger.info("[PERF] TTS %s request cancelled: %.3fs", label, elapsed)
        else:
            logger.info(
                "[PERF] TTS %s request complete: %.3fs, %.1f KB",
                label,
                elapsed,
                audio_bytes / 1024,
            )

    except asyncio.CancelledError:
        logger.info(
            "[PERF] TTS %s task cancelled: %.3fs",
            label,
            time.perf_counter() - start_time,
        )
        raise

    except Exception as exc:
        session.set_error(exc)
        if session.cancelled:
            logger.info("TTS %s stopped during cleanup", label)
        else:
            logger.exception("TTS %s request failed: %s", label, exc)

    finally:
        _queue_put_end(pcm_queue)


def _signal_playback_started(
    event,
    loop: asyncio.AbstractEventLoop,
) -> None:
    if event is None:
        return

    if isinstance(event, asyncio.Event):
        loop.call_soon_threadsafe(event.set)
    else:
        event.set()


def _get_interruptibly(
    pcm_queue: queue.Queue,
    session: _SpeechSession,
):
    while not session.cancelled:
        try:
            return pcm_queue.get(timeout=0.1)
        except queue.Empty:
            continue
    return _PCM_END


def _play_pcm_queues(
    mainwindow,
    session: _SpeechSession,
    first_pcm: queue.Queue,
    remaining_pcm: queue.Queue | None,
    *,
    loop: asyncio.AbstractEventLoop,
    playback_started_event=None,
) -> None:
    """Play first and remaining PCM queues through one continuous output stream."""
    start_time = time.perf_counter()
    stream = None
    output_rate = _get_output_rate()
    current_queue = first_pcm
    phase = "first"

    try:
        while not session.cancelled:
            item = _get_interruptibly(current_queue, session)

            if item is _PCM_END:
                if phase == "first" and remaining_pcm is not None:
                    phase = "remaining"
                    current_queue = remaining_pcm
                    continue
                break

            if stream is None:
                stream = sd.RawOutputStream(
                    samplerate=output_rate,
                    channels=1,
                    dtype="int16",
                    latency="low",
                )
                stream.start()

                if not session.attach_stream(stream):
                    stream.abort()
                    return

                mainwindow.animation_state = "speaking"
                _signal_playback_started(
                    playback_started_event,
                    loop,
                )
                logger.info(
                    "TTS playback started: %.3fs",
                    time.perf_counter() - start_time,
                )

            underflowed = stream.write(item)
            if underflowed:
                logger.warning("TTS output underflow")

        if stream is not None and not session.cancelled:
            stream.stop()

        elapsed = time.perf_counter() - start_time
        if session.cancelled:
            logger.info("TTS playback interrupted: %.3fs", elapsed)
        else:
            logger.info("TTS playback completed: %.3fs", elapsed)

    except Exception as exc:
        session.set_error(exc)
        if not session.cancelled:
            logger.exception("TTS playback failed: %s", exc)

    finally:
        if stream is not None:
            session.clear_stream(stream)
            try:
                if session.cancelled or session.error is not None:
                    stream.abort()
                stream.close()
            except Exception:
                logger.debug("TTS stream cleanup failed", exc_info=True)


async def _run_single_text_tts(
    mainwindow,
    text: str,
    *,
    playback_started_event=None,
) -> None:
    session = _begin_session()
    loop = asyncio.get_running_loop()
    session.bind_loop(loop)
    pcm_queue: queue.Queue = queue.Queue()

    producer = asyncio.create_task(
        _edge_to_pcm_queue(
            text,
            pcm_queue,
            session,
            label="first",
        )
    )
    session.register_task(producer)

    playback = asyncio.create_task(
        asyncio.to_thread(
            _play_pcm_queues,
            mainwindow,
            session,
            pcm_queue,
            None,
            loop=loop,
            playback_started_event=playback_started_event,
        )
    )
    session.register_task(playback)

    try:
        await asyncio.gather(producer, playback)
    except asyncio.CancelledError:
        # stop_speaking() intentionally cancels tasks in this session.
        pass
    finally:
        _finish_session(session)

    if session.error is not None and not session.cancelled:
        choose(True, state="brain_short", mainwindow=mainwindow)


async def speak_tone(
    self,
    text: str,
    playback_started_event=None,
) -> None:
    """Stream one text to Edge TTS and play it as audio arrives."""
    await _run_single_text_tts(
        self,
        text,
        playback_started_event=playback_started_event,
    )


async def _sentence_event_get(sentence_queue):
    item = await asyncio.to_thread(sentence_queue.get)
    sentence_queue.task_done()
    return item


async def speak_first_remaining(mainwindow, sentence_queue) -> None:
    """
    Play an LLM answer with minimal perceived latency.

    Contract with the producer queue:
      ("first", first_sentence)       -> emitted as soon as the first sentence ends
      ("remaining", remaining_text)   -> emitted once the LLM answer is complete
      None                             -> completion marker

    The first Edge-TTS request is streamed immediately.  Once its playback has
    actually started, the remaining answer starts a second Edge-TTS request.
    That second request is decoded into a PCM buffer while the first sentence is
    still playing.  One sounddevice stream consumes both buffers in order, so
    playback can continue directly into already-prefetched remaining audio.
    """
    first_event = await _sentence_event_get(sentence_queue)
    if first_event is None:
        return

    event_type, first_text = first_event

    # If the LLM never produced a sentence boundary, the whole answer arrives as
    # one "remaining" event.  Stream it directly instead of inventing a split.
    if event_type == "remaining":
        await speak_tone(mainwindow, first_text)
        completion = await _sentence_event_get(sentence_queue)
        return

    session = _begin_session()
    loop = asyncio.get_running_loop()
    session.bind_loop(loop)

    first_pcm: queue.Queue = queue.Queue()
    remaining_pcm: queue.Queue = queue.Queue()
    first_playback_started = threading.Event()

    first_producer = asyncio.create_task(
        _edge_to_pcm_queue(
            first_text,
            first_pcm,
            session,
            label="first",
        )
    )
    session.register_task(first_producer)

    playback = asyncio.create_task(
        asyncio.to_thread(
            _play_pcm_queues,
            mainwindow,
            session,
            first_pcm,
            remaining_pcm,
            loop=loop,
            playback_started_event=first_playback_started,
        )
    )
    session.register_task(playback)

    async def produce_remaining() -> str | None:
        # Protect first-sentence latency: do not open the second Edge request
        # until sound from the first request is actually playing.
        while (
            not first_playback_started.is_set()
            and not first_producer.done()
            and not session.cancelled
        ):
            await asyncio.sleep(0.01)

        if session.cancelled or not first_playback_started.is_set():
            _queue_put_end(remaining_pcm)
            return None

        remaining_event = await _sentence_event_get(sentence_queue)
        if remaining_event is None:
            _queue_put_end(remaining_pcm)
            return None

        remaining_type, remaining_text = remaining_event
        if remaining_type != "remaining":
            session.set_error(
                RuntimeError(
                    f"Unexpected TTS queue event: {remaining_type!r}"
                )
            )
            _queue_put_end(remaining_pcm)
            return None

        logger.info(
            "[PERF] TTS remaining prefetch start: %s",
            remaining_text,
        )

        await _edge_to_pcm_queue(
            remaining_text,
            remaining_pcm,
            session,
            label="remaining",
        )
        return remaining_text

    remaining_producer = asyncio.create_task(produce_remaining())
    session.register_task(remaining_producer)

    remaining_text: str | None = None

    try:
        results = await asyncio.gather(
            first_producer,
            remaining_producer,
            playback,
            return_exceptions=True,
        )

        remaining_result = results[1]
        if isinstance(remaining_result, str):
            remaining_text = remaining_result

    finally:
        _finish_session(session)

    # A remaining-text event is followed by one completion marker.  Consume it
    # only after the remaining event has actually been consumed above.
    if remaining_text is not None:
        await _sentence_event_get(sentence_queue)

    if session.error is not None and not session.cancelled:
        choose(True, state="brain_short", mainwindow=mainwindow)


# ---------------------------------------------------------------------------
# LLM
# ---------------------------------------------------------------------------

def _safe_callback(callback: Callable | None, *args) -> None:
    if callback is None:
        return
    try:
        callback(*args)
    except Exception:
        logger.exception("LLM stream callback failed")


def _first_sentence_boundary(text: str) -> int | None:
    for index, character in enumerate(text):
        if character in _FIRST_SENTENCE_BOUNDARIES:
            return index
    return None


def _collect_stream_text(
    client: OpenAI,
    model_name: str,
    messages: list,
    *,
    label: str,
    use_deepseek: bool = False,
    on_token=None,
    on_first_sentence=None,
    on_remaining=None,
) -> str:
    start_time = time.perf_counter()
    text_parts: list[str] = []
    sentence_buffer = ""
    first_sentence: str | None = None
    first_token_time: float | None = None

    kwargs = {
        "model": model_name,
        "messages": messages,
        "temperature": 0.1,
        "top_p": 0.7,
        "max_tokens": 256,
        "stream": True,
    }

    if use_deepseek:
        kwargs["extra_body"] = {"thinking": {"type": "disabled"}}

    logger.info("[PERF] LLM request start")
    response = client.chat.completions.create(**kwargs)

    for chunk in response:
        if not chunk.choices:
            continue

        content = chunk.choices[0].delta.content
        if not content:
            continue

        # Keep TTS/UI text and final text in the same cleaned coordinate space.
        content = content.replace("*", "")
        if not content:
            continue

        if first_token_time is None:
            first_token_time = time.perf_counter() - start_time
            logger.info("[PERF] LLM first token: %.3fs", first_token_time)

        text_parts.append(content)
        _safe_callback(on_token, content)

        if on_first_sentence is not None and first_sentence is None:
            sentence_buffer += content
            boundary = _first_sentence_boundary(sentence_buffer)
            if boundary is not None:
                candidate = sentence_buffer[: boundary + 1].strip()
                if candidate:
                    first_sentence = candidate
                    _safe_callback(on_first_sentence, first_sentence)

    text = "".join(text_parts).strip()

    if not text:
        raise ValueError(f"{label} returned empty response")

    if on_remaining is not None:
        if first_sentence and text.startswith(first_sentence):
            remaining = text[len(first_sentence) :].strip()
        elif first_sentence:
            # Defensive fallback; a callback should never change generated text.
            position = text.find(first_sentence)
            remaining = (
                text[position + len(first_sentence) :].strip()
                if position >= 0
                else text
            )
        else:
            remaining = text

        if remaining:
            _safe_callback(on_remaining, remaining)

    logger.info(
        "[PERF] LLM complete: %.3fs, %d chars",
        time.perf_counter() - start_time,
        len(text),
    )
    logger.info("%s response: %s", label, text)
    return text


def message(
    self,
    problem: str,
    on_token=None,
    on_first_sentence=None,
    on_remaining=None,
) -> str:
    """Generate one grounded answer, preferring the online DeepSeek service."""
    logger.info("[PERF] Enter message()")

    messages = [
        {
            "role": "system",
            "content": (
                "你是河南非遗数字人牡丹，负责向参观者介绍河南非遗文化。"
                "用户消息中包含‘记忆’和‘问题’。"
                "只能依据‘记忆’中明确提供的信息回答。"
                "不要自行补充记忆中没有出现的年代、材料、颜色、人物、称号、"
                "工艺细节、历史事件或其他事实。"
                "如果记忆不足以支持某个事实，直接说明这部分暂时不清楚。"
                "回答少于150字，语言自然、简洁，适合直接朗读。"
            ),
        },
        {"role": "user", "content": problem},
    ]

    try:
        deepseek_client = OpenAI(
            api_key=config.DEEPSEEK_API_KEY,
            base_url=config.DEEPSEEK_BASE_URL,
            timeout=config.DEEPSEEK_TIMEOUT,
            max_retries=1,
        )
        logger.info("Using online LLM: %s", config.DEEPSEEK_MODEL)

        return _collect_stream_text(
            deepseek_client,
            config.DEEPSEEK_MODEL,
            messages,
            label="DeepSeek",
            use_deepseek=True,
            on_token=on_token,
            on_first_sentence=on_first_sentence,
            on_remaining=on_remaining,
        )

    except Exception as exc:
        logger.exception("Online LLM failed: %s", exc)
        choose(True, state="brain_short", mainwindow=self)
        return ""
