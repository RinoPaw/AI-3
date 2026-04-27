import json
import requests
import logging
from typing import Dict, List, Any
import os
from datetime import datetime

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class OllamaSummarizer:
    def __init__(self, model_name: str = "qwen2.5:3b", base_url: str = "http://localhost:11434"):
        """
        初始化Ollama总结器
        
        Args:
            model_name: Ollama模型名称
            base_url: Ollama服务的基础URL
        """
        self.model_name = model_name
        self.base_url = base_url
        # os.mkdir("./data/faiss_data/summary")

        
    def _call_ollama(self, prompt: str) -> str:
        """
        调用Ollama API
        
        Args:
            prompt: 提示词
            
        Returns:
            str: 模型返回的总结文本
        """
        try:
            response = requests.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": self.model_name,
                    "prompt": prompt,
                    "stream": False
                }
            )
            response.raise_for_status()
            return response.json()["response"]
        except Exception as e:
            logger.error(f"调用Ollama API时发生错误: {str(e)}")
            raise
            
    def summarize_keyword(self, keyword: str, content: str, result: dict) -> Dict[str, Any]:
        """
        对单个关键词的内容进行总结
        
        Args:
            keyword: 关键词
            content: 需要总结的内容
            
        Returns:
            Dict: 包含总结结果的字典
        """
        prompt = f"""请对以下关于"{keyword}"的内容进行总结，要求：
1. 提取关键信息
2. 保持客观准确
3. 使用简洁的语言
4. 突出重要观点
精炼
内容如下：
{content}"""
        
        try:
            summary = self._call_ollama(prompt).replace('*', '').replace('-', '')
            result[f"{keyword}"] = summary
            
            # 保存到JSON文件
            # self._save_to_json(result)
            
            return result
        except Exception as e:
            logger.error(f"总结关键词 '{keyword}' 时发生错误: {str(e)}")
            raise
            
def _save_to_json(data: Dict[str, Any], filename: str):
    """
    将总结结果保存到JSON文件
    
    Args:
        data: 要保存的数据
    """
    try:
        with open(filename, 'a+', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info(f"总结结果已保存到: {filename}")
    except Exception as e:
        logger.error(f"保存JSON文件时发生错误: {str(e)}")
        raise

def load_data(path):
    with open(path, mode='r', encoding='utf-8') as f:
        data = json.load(f)
    return data
def main():
    # 使用示例
    summarizer = OllamaSummarizer()
    
    # 示例数据
    data = load_data("data/faiss_data/faiss_data.json")
    result = {}
    count = 0
    for keyword, content in data.items():
        try:
            count = count + 1
            if count <= 350:
                continue
            result = summarizer.summarize_keyword(keyword, content, result)
            print(f"第{count}个数据处理成功")
            # if count % 50 == 0:
                # filename = f"data/faiss_data/summary/summary{count}.json"
                # _save_to_json(result, filename)
        except Exception as e:
            print(f"处理关键词 '{keyword}' 时发生错误: {str(e)}")

    final_file_name = f"data/faiss_data/summary/summary_final.json"
    _save_to_json(result, final_file_name)

if __name__ == "__main__":
    main() 