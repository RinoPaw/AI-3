from abc import ABC, abstractmethod
from collections.abc import Callable
import threading


TextCallback = Callable[[str], None]
StatusCallback = Callable[[str], None]


class ASRProvider(ABC):
    def __init__(
        self,
        on_final: TextCallback,
        on_partial: TextCallback | None = None,
        on_status: StatusCallback | None = None,
    ):
        self.on_final = on_final
        self.on_partial = on_partial or (lambda text: None)
        self.on_status = on_status or (lambda status: None)
        self.stop_event = threading.Event()

    @abstractmethod
    def run(self) -> None:
        """Blocking recognition loop."""
        raise NotImplementedError

    def stop(self) -> None:
        self.stop_event.set()