import os
import logging
import logging.config
from datetime import datetime
import time
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def setup_logging():
    # 确保logs目录存在
    log_dir = PROJECT_ROOT / "logs"
    if not log_dir.exists():
        log_dir.mkdir(parents=True)
    
    log_filename = (log_dir / time.strftime('mudan_%Y-%m-%d_%H-%M-%S.log')).as_posix()
    # 加载日志配置
    config_path = PROJECT_ROOT / 'logger.ini'
    logging.config.fileConfig(config_path, defaults={'log_filename': log_filename})
    logger = logging.getLogger('appLogger')
    
    # 添加会话开始标记
    logger.info('-'*80)
    logger.info(f'开始时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
    logger.info('-'*80)
    
    return logger

def get_logger():
    return logging.getLogger('appLogger')

# 当目录文件数超过以前的，删除以前的文件
def delete_old_log_files(directory):
    target = Path(directory)
    if not target.is_absolute():
        target = PROJECT_ROOT / target

    if target.exists():
        files = os.listdir(target)
        files.sort()
        if len(files) > 10:
            for file in files[:-10]:
                os.remove(target / file)
