import json
import os
from collections import Counter

import faiss
import jieba
from sentence_transformers import SentenceTransformer

from config import FAISS_KEYWORD_PATH, logger


class FaissVectorStore:
    def __init__(
        self,
        model_path: str,
        index_path: str,
        json_path: str | None = None,
        jsonl_path: str | None = None,
    ):
        """
        初始化 FAISS 数据库。

        兼容两种参数名：
        - json_path：推荐使用，表示 faiss_data.json
        - jsonl_path：兼容旧代码，虽然名字叫 jsonl，但现在实际也是 JSON 文件
        """
        self.embedding_model = SentenceTransformer(model_path)
        self.index_path = index_path
        self.json_path = json_path or jsonl_path

        if not self.json_path:
            raise ValueError("必须传入 json_path 或 jsonl_path")

        self.documents = []
        self.metadatas = []
        self.ids = []
        self.keyword_index = {}

        self._load_metadata()

        if os.path.exists(index_path):
            self.index = faiss.read_index(index_path)

            # 防止索引数量和文档数量不一致
            if self.index.ntotal != len(self.documents):
                logger.warning(
                    f"FAISS 索引数量 {self.index.ntotal} 与文档数量 {len(self.documents)} 不一致，正在重建索引"
                )
                self._create_index()
        else:
            self._create_index()

        self._load_keywords()

    def load_data(self, path):
        """加载 summary_final.json。"""
        with open(path, mode="r", encoding="utf-8") as f:
            return json.load(f)

    def _load_metadata(self):
        """加载 faiss_data.json，格式为 JSON 字典。"""
        try:
            with open(self.json_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            if not isinstance(data, dict):
                raise ValueError("faiss_data.json 应该是 JSON 字典格式")

            for idx, (key, value) in enumerate(data.items()):
                combined_text = f"标题:{key}\n内容:{value}"

                self.documents.append(combined_text)
                self.metadatas.append({
                    "标题": key,
                    "内容": value,
                    "问题": f"关于 {key} 的信息"
                })
                self.ids.append(f"doc_{idx}")

            logger.info(f"成功加载 {len(self.documents)} 条文档数据")

        except Exception as e:
            logger.exception(f"Error loading FAISS data: {e}")
            raise

    def _create_index(self):
        """根据 self.documents 创建新的 FAISS 索引。"""
        if not self.documents:
            raise ValueError("文档为空，无法创建 FAISS 索引")

        logger.info(f"开始创建 FAISS 索引，文档数量: {len(self.documents)}")
        print(f"开始创建 FAISS 索引，文档数量: {len(self.documents)}", flush=True)

        embeddings = self.embedding_model.encode(
            self.documents,
            batch_size=4,
            normalize_embeddings=True,
            show_progress_bar=True
        ).astype("float32")

        dimension = embeddings.shape[1]

        # 归一化向量 + 内积，相当于余弦相似度
        self.index = faiss.IndexFlatIP(dimension)
        self.index.add(embeddings)

        os.makedirs(os.path.dirname(self.index_path), exist_ok=True)
        faiss.write_index(self.index, self.index_path)

        logger.info(f"FAISS 索引已创建，共 {self.index.ntotal} 条向量")
        print(f"FAISS 索引已创建，共 {self.index.ntotal} 条向量", flush=True)

    def _load_keywords(self):
        """加载关键词倒排索引。"""
        try:
            with open(FAISS_KEYWORD_PATH, "r", encoding="utf-8") as f:
                self.keyword_index = dict(json.load(f))

            logger.info(f"成功加载关键词索引，共 {len(self.keyword_index)} 个关键词")

        except FileNotFoundError:
            logger.warning(f"关键词文件不存在: {FAISS_KEYWORD_PATH}")
            self.keyword_index = {}

        except Exception as e:
            logger.exception(f"加载关键词索引失败: {e}")
            self.keyword_index = {}

    def keyword_search(self, query_text: str):
        """
        关键词检索。
        返回文档下标列表。
        """
        total_index = []
        final_list = []

        splited_data = jieba.lcut(query_text)

        for word in splited_data:
            values = self.keyword_index.get(word)
            if values:
                total_index.extend(values)

        index_dict = dict(Counter(total_index).most_common(3))

        for idx in index_dict.keys():
            # JSON 里读出来一般是 int，但这里顺手兼容 str
            if isinstance(idx, str) and idx.isdigit():
                idx = int(idx)

            if isinstance(idx, int) and 0 <= idx < len(self.documents):
                final_list.append(idx)

        return final_list

    # Backward-compatible aliases for legacy callers.
    def KeySearch(self, query_text: str):
        return self.keyword_search(query_text)

    def _load_Keywords(self):
        return self._load_keywords()

    def query(self, query_text: str, n_results: int = 2) -> dict:
        """
        查询 FAISS 数据库。
        关键词检索 + 向量检索 + 重排序。
        """
        # 一些太泛的词，不适合作为强排序依据
        stop_words = {
            "介绍", "一下", "什么", "是什么", "有什么", "价值", "特色",
            "制作", "技艺", "传统", "非遗", "河南", "项目", "文化",
            "讲讲", "说说", "解释", "说明", "相关", "信息",
            "的", "了", "吗", "呢", "啊", "呀", "和", "与", "及", "是", "有"
        }

        important_tokens = [
            w.strip()
            for w in jieba.lcut(query_text)
            if len(w.strip()) >= 2 and w.strip() not in stop_words
        ]

        # 关键词召回
        keyword_indices = self.keyword_search(query_text)

        # 向量召回：多取一些，后面重排序
        query_embedding = self.embedding_model.encode(
            [query_text],
            normalize_embeddings=True
        ).astype("float32")

        search_k = max(n_results * 5, 20)
        search_k = min(search_k, self.index.ntotal)

        scores, indices = self.index.search(query_embedding, search_k)

        vector_score_map = {}
        for score, idx in zip(scores[0], indices[0]):
            if idx == -1:
                continue
            if 0 <= idx < len(self.documents):
                vector_score_map[idx] = float(score)

        # 合并候选
        candidate_indices = set(keyword_indices) | set(vector_score_map.keys())

        ranked = []

        generic_titles = {
            "皮影戏", "木偶戏", "剪纸", "面塑", "泥塑", "灯谜",
            "民间剪纸", "农民画", "糖画", "香包", "面塑",
            "皮影戏[皮影戏]"
        }

        for idx in candidate_indices:
            if not (0 <= idx < len(self.documents)):
                continue

            doc = self.documents[idx]
            metadata = self.metadatas[idx]
            title = metadata.get("标题", "")

            full_text = f"{title}\n{doc}"
            prefix_text = doc[:500]

            # 基础分：向量相似度
            score = vector_score_map.get(idx, 0.0)

            # 关键词命中的基础加分，但不要太高，避免“制作技艺”这种泛词带偏
            if idx in keyword_indices:
                score += 0.15

            # 标题强匹配加分
            if title and title in query_text:
                score += 2.0

            if query_text in title:
                score += 2.0

            # 用户问题中的重要词，出现在标题或正文中，加分
            title_hits = 0
            doc_hits = 0
            prefix_hits = 0

            for token in important_tokens:
                if token in title:
                    title_hits += 1
                if token in doc[:1500]:
                    doc_hits += 1
                if token in prefix_text:
                    prefix_hits += 1

            score += title_hits * 0.7
            score += min(doc_hits, 4) * 0.2
            score += prefix_hits * 0.5

            # 例如：“罗山 + 皮影戏”、“信阳 + 毛尖”
            # 如果同一篇文档完整命中多个关键信息，强力加分
            if len(important_tokens) >= 2 and all(token in full_text for token in important_tokens):
                score += 2.0

            # 如果所有重要词都出现在文档前半部分，也加分
            if important_tokens and all(token in doc[:2000] for token in important_tokens):
                score += 0.6

            # 标题过于泛化时，轻微降权
            # 例如标题只是“皮影戏”，但问题问的是“罗山皮影戏”
            if title in generic_titles and len(important_tokens) >= 2:
                missing_tokens = [
                    token for token in important_tokens
                    if token not in title
                ]
                if missing_tokens:
                    score -= 0.5

            ranked.append((score, idx))

        ranked.sort(reverse=True, key=lambda x: x[0])

        results = {
            "documents": [],
            "metadatas": [],
            "scores": [],
            # 兼容旧代码里可能使用 distances 的情况
            "distances": []
        }

        seen = set()

        for score, idx in ranked:
            if idx in seen:
                continue

            results["documents"].append(self.documents[idx])
            results["metadatas"].append(self.metadatas[idx])
            results["scores"].append(score)
            results["distances"].append(score)

            seen.add(idx)

            if len(results["documents"]) >= n_results:
                break

        logger.info(
            f"Query: {query_text}, returned {len(results['documents'])} documents"
        )

        return results


# Backward-compatible class name kept for old imports/usages.
FaissDB = FaissVectorStore


if __name__ == "__main__":
    from config import EMBEDDING_MODEL_PATH, FAISS_INDEX_PATH

    try:
        from config import FAISS_DATA_PATH
        data_path = FAISS_DATA_PATH
    except ImportError:
        from config import JSONL_DATA_PATH
        data_path = JSONL_DATA_PATH

    db = FaissVectorStore(
        model_path=EMBEDDING_MODEL_PATH,
        index_path=FAISS_INDEX_PATH,
        json_path=data_path
    )

    questions = [
        "太极拳是什么？",
        "二十四节气有什么价值？",
        "信阳毛尖制作技艺介绍一下",
        "罗山皮影戏有什么特色？",
        "陈氏太极拳有哪些特点？",
        "内乡打春牛是什么？",
    ]

    for q in questions:
        print("=" * 80)
        print("问题：", q)

        result = db.query(q, n_results=3)

        print("返回数量：", len(result["documents"]))

        for i, doc in enumerate(result["documents"], start=1):
            print(f"\n结果 {i}:")
            print(doc[:500])
            print("-" * 40)
