import threading
import time

from .xfyun import XfyunASR


class ASRManager:
    def __init__(
        self,
        cloud_config,
        on_final,
        on_partial=None,
        on_status=None,
    ):
        self.cloud_config = cloud_config

        self.on_final = on_final
        self.on_partial = on_partial or (lambda text: None)
        self.on_status = on_status or (lambda status: None)

        self.stop_event = threading.Event()

        self.thread = None
        self.current_provider = None
        self.mode = None

    def start(self):
        if self.thread and self.thread.is_alive():
            return

        self.stop_event.clear()

        self.thread = threading.Thread(
            target=self._run,
            daemon=True,
            name="ASRManager",
        )

        self.thread.start()

    def stop(self):
        self.stop_event.set()

        if self.current_provider:
            try:
                self.current_provider.stop()
            except Exception:
                pass

        if self.thread:
            self.thread.join(timeout=3.0)

        self.current_provider = None
        self.mode = None

    def _status(self, status):
        self.on_status(status)

    def _run_cloud_once(self):
        got_final = threading.Event()
        got_error = threading.Event()

        def final(text):
            got_final.set()
            self.on_final(text)

        def partial(text):
            self.on_partial(text)

        def status(value):
            self._status(f"cloud:{value}")

            if value.startswith("error:"):
                got_error.set()

        provider = XfyunASR(
            api_config=self.cloud_config,
            on_final=final,
            on_partial=partial,
            on_status=status,
        )

        self.current_provider = provider

        try:
            provider.run()
        except Exception as exc:
            got_error.set()
            self._status(
                f"cloud:error:{exc}"
            )
        finally:
            self.current_provider = None

        if self.stop_event.is_set():
            return "stop"

        if got_error.is_set():
            return "error"

        if got_final.is_set():
            return "final"

        return "closed"

    def _run(self):
        # 每次 start() 都重新给讯飞机会。
        self.mode = "cloud"

        while not self.stop_event.is_set():
            self._status("manager:cloud")

            result = self._run_cloud_once()

            if result == "stop":
                break

            # 正常完成一句：
            # 再建立下一轮讯飞识别。
            if result == "final":
                time.sleep(0.05)
                continue

            # 在线识别失败时明确结束，不加载任何本地 ASR 模型。
            self._status(
                f"manager:cloud_failed:{result}"
            )
            break

        self._status("manager:stopped")
