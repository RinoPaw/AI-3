# config.py
import json
import os
import sys
from set_logger import setup_logging


def _load_dotenv_if_exists(file_name: str = ".env") -> None:
    """Load .env into process env without external dependencies."""
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), file_name)
    if not os.path.exists(env_path):
        return

    try:
        with open(env_path, "r", encoding="utf-8") as f:
            for raw_line in f:
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue

                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip()

                if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
                    value = value[1:-1]

                if key and key not in os.environ:
                    os.environ[key] = value
    except Exception:
        # Avoid crashing when local .env has malformed lines.
        pass


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _env_path(name: str, default_relative_path: str) -> str:
    return resource_path(_env(name, default_relative_path))


def resource_path(relative_path: str) -> str:
    """获取资源文件的绝对路径"""
    try:
        # 首先尝试获取 PyInstaller 的临时路径
        if hasattr(sys, "_MEIPASS"):
            base_path = sys._MEIPASS
            logger.info(f"Using PyInstaller temporary path: {base_path}")
        else:
            # 如果不是打包环境，使用当前目录
            base_path = os.path.dirname(os.path.abspath(__file__))
    except Exception as e:
        # 如果出现任何异常，使用当前目录
        base_path = os.path.dirname(os.path.abspath(__file__))
        logger.info(f"Use current directory as base path: {base_path}")
        logger.exception(f"Exception: {str(e)}")

    full_path = os.path.join(base_path, relative_path)
    if not os.path.exists(full_path):
        logger.warning(f"Warning: File does not exist: {full_path}")
        # 尝试在当前目录下查找
        current_dir_path = os.path.join(os.getcwd(), relative_path)
        if os.path.exists(current_dir_path):
            logger.info(f"File found in current directory: {current_dir_path}")
            return current_dir_path
    return full_path


def _load_xf_api_configs() -> list[dict]:
    """
    Load XF API configs from env.

    Priority:
    1) XF_API_CONFIGS_JSON as JSON list.
    2) Single config from XF_APPID + XF_API_KEY (+ optional XF_API_SECRET).
    3) Empty list.
    """
    raw_json = _env("XF_API_CONFIGS_JSON", "")
    if raw_json:
        try:
            parsed = json.loads(raw_json)
            if isinstance(parsed, list):
                normalized = []
                for item in parsed:
                    if not isinstance(item, dict):
                        continue
                    appid = str(item.get("APPID", "")).strip()
                    api_key = str(item.get("APIKey", "")).strip()
                    api_secret = str(item.get("APISecret", "")).strip()
                    if appid and api_key:
                        normalized.append(
                            {
                                "APPID": appid,
                                "APIKey": api_key,
                                "APISecret": api_secret,
                            }
                        )
                if normalized:
                    return normalized
            logger.warning("XF_API_CONFIGS_JSON is invalid or empty after parsing.")
        except Exception as e:
            logger.exception(f"Failed to parse XF_API_CONFIGS_JSON: {e}")

    appid = _env("XF_APPID", "")
    api_key = _env("XF_API_KEY", "")
    api_secret = _env("XF_API_SECRET", "")
    if appid and api_key:
        return [
            {
                "APPID": appid,
                "APIKey": api_key,
                "APISecret": api_secret,
            }
        ]

    logger.warning(
        "XF API credentials are not configured. "
        "Set XF_APPID/XF_API_KEY(/XF_API_SECRET) or XF_API_CONFIGS_JSON."
    )
    return []


_load_dotenv_if_exists()
logger = setup_logging()

# 基础路径
BASE_PATH = os.path.abspath(".")

# 模型相关路径
VOSK_MODEL_PATH = _env_path("VOSK_MODEL_PATH", "models/vosk-model-cn-0.22")
EMBEDDING_MODEL_PATH = _env_path(
    "EMBEDDING_MODEL_PATH",
    "models/embedding/BAAI/bge-large-zh-v1___5",
)

# 数据库路径
FAISS_INDEX_PATH = _env_path("FAISS_INDEX_PATH", "data/faiss_data/faiss_index.index")
FAISS_DATA_PATH = _env_path("FAISS_DATA_PATH", "data/faiss_data/faiss_data.json")
FAISS_KEYWORD_PATH = _env_path("FAISS_KEYWORD_PATH", "data/faiss_data/my_keywords.json")

# 音频文件路径
AUDIO_HELLO_PATH = _env_path("AUDIO_HELLO_PATH", "audio/hello.mp3")
AUDIO_GOODBYE_PATH = _env_path("AUDIO_GOODBYE_PATH", "audio/goodbye.mp3")
AUDIO_INTERRUPT_PATH = _env_path("AUDIO_INTERRUPT_PATH", "audio/interupt.mp3")
# 兼容旧命名
AUDIO_INTERUPT_PATH = AUDIO_INTERRUPT_PATH
AUDIO_NO_SPEAK_PATH = _env_path("AUDIO_NO_SPEAK_PATH", "audio/no_speak.mp3")
AUDIO_THINKING_PATH = _env_path("AUDIO_THINKING_PATH", "audio/thinking.mp3")
AUDIO_BRAIN_SHORT_PATH = _env_path("AUDIO_BRAIN_SHORT_PATH", "audio/brain_short.mp3")
AUDIO_NO_RETRIVAL_PATH = _env_path("AUDIO_NO_RETRIVAL_PATH", "audio/no_retrival.mp3")

# 动画帧路径
FRAME_DIR_GREET = _env_path("FRAME_DIR_GREET", "process/greet/0/")
FRAME_DIR_IDLE = _env_path("FRAME_DIR_IDLE", "process/idle/0/")
FRAME_DIR_SPEAK = _env_path("FRAME_DIR_SPEAK", "process/speak/0/")
FRAME_DIR_FAREWELL = _env_path("FRAME_DIR_FAREWELL", "process/farewell/0/")
FRAME_DIR_THANK = _env_path("FRAME_DIR_THANK", "process/thank/0/")

# icon图标路径
ICON_CLOSE = _env_path("ICON_CLOSE", "icon/close.png")
ICON_HEAR = _env_path("ICON_HEAR", "icon/hear.png")
ICON_NO_HEAR = _env_path("ICON_NO_HEAR", "icon/no_hear.png")
ICON_INTERRUPT = _env_path("ICON_INTERRUPT", "icon/interupt.png")
# 兼容旧命名
ICON_INTERUPT = ICON_INTERRUPT

# 背景图片路径
BACKGROUND_IMAGE = _env_path("BACKGROUND_IMAGE", "icon/background(1).jpg")

# 本地模型名称
LOCAL_MODEL = _env("LOCAL_MODEL", "llama3.2")

# 讯飞语音识别 API 配置列表
XF_API_CONFIGS = _load_xf_api_configs()

# 智谱 API 配置
ZHIPU_API_KEY = _env("ZHIPU_API_KEY", "")
ZHIPU_MODEL = _env("ZHIPU_MODEL", "glm-4.5-flash")

# 知识图谱
HTML_PATH = _env_path("HTML_PATH", "heritage/templates/index.html")
