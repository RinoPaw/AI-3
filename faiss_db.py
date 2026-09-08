import json
import os
import re
import time
from collections import Counter

from boot_timing import boot_log

boot_log("before faiss")
import faiss
boot_log("after faiss")
import numpy as np
boot_log("before sentence_transformers")
from sentence_transformers import SentenceTransformer
boot_log("after sentence_transformers")

from config import (
    FAISS_KEYWORD_PATH,
    EMBEDDING_MODEL_PATH,
    EMBEDDING_DEVICE,
    EMBEDDING_MIN_SIMILARITY,
    FAISS_INDEX_PATH,
    JSONL_DATA_PATH,
    logger,
)


class FaissDB:
    def __init__(
        self,
        model_path: str,
        index_path: str,
        jsonl_path: str,
    ):
        logger.info(
            "Loading embedding model: %s",
            model_path,
        )

        start = time.perf_counter()

        self.embedding_model = SentenceTransformer(
            model_path,
            device=EMBEDDING_DEVICE,
        )

        # 这类非遗知识库通常不需要超长单条文档，限制到 1024 能明显减少
        # 首批大文档在 CPU 上被 padding 到极长序列导致的卡顿。
        if hasattr(self.embedding_model, "max_seq_length"):
            self.embedding_model.max_seq_length = 1024

        logger.info(
            "Embedding model loaded in %.3fs, device=%s",
            time.perf_counter() - start,
            EMBEDDING_DEVICE,
        )

        self.index_path = index_path
        self.jsonl_path = jsonl_path

        self.documents = []
        self.metadatas = []
        self.ids = []
        self.KeyWord = {}

        # 先加载文档，确保文档顺序和 FAISS 索引完全一致
        self._load_metadata()
        self._load_keywords()

        if os.path.exists(index_path):
            with open(index_path, "rb") as f:
                index_bytes = np.frombuffer(
                    f.read(),
                    dtype=np.uint8,
                )

            self.index = faiss.deserialize_index(index_bytes)

            logger.info(
                "Loaded FAISS index: %s, vectors=%d",
                index_path,
                self.index.ntotal,
            )
        else:
            self._create_index()

    def _extract_field(self, content: str, start_field: str, end_field: str = None) -> str:
        """从长内容字符串中提取某个字段。"""
        if end_field:
            pattern = rf"{re.escape(start_field)}:\s*(.*?)(?=,\s*{re.escape(end_field)}:)"
        else:
            pattern = rf"{re.escape(start_field)}:\s*([^,]+)"

        match = re.search(pattern, content, re.S)
        return match.group(1).strip() if match else ""

    def _build_embedding_document(self, title: str, content: str) -> str:
        """只生成用于向量检索的精简文本，完整内容仍保留在 metadata。"""

        category = self._extract_field(content, "类别")
        city = self._extract_field(content, "城市")
        region = self._extract_field(content, "地区")

        intro = self._extract_field(
            content,
            "介绍",
            "重大地区",
        )

        features = self._extract_field(
            content,
            "主要特色",
            "重要价值",
        )

        parts = [
            f"标题：{title}",
            f"类别：{category}" if category else "",
            f"城市：{city}" if city else "",
            f"地区：{region}" if region else "",
            f"介绍：{intro}" if intro else "",
            f"主要特色：{features}" if features else "",
        ]

        return "\n".join(part for part in parts if part)

    def _load_metadata(self):
        """加载非遗知识库。"""

        try:
            with open(
                self.jsonl_path,
                "r",
                encoding="utf-8",
            ) as f:
                data = json.load(f)

            for key, value in data.items():
                self.documents.append(
                    self._build_embedding_document(key, value)
                )

                self.metadatas.append(
                    {
                        "标题": key,
                        "内容": value,
                        "问题": f"关于 {key} 的信息",
                    }
                )

                self.ids.append(
                    f"doc_{hash(key)}"
                )

            logger.info(
                "成功加载 %d 条文档数据",
                len(self.documents),
            )

        except Exception as exc:
            logger.exception(
                "Error loading FAISS data: %s",
                exc,
            )
            raise

    def _create_index(self):
        """使用 Qwen3-Embedding 重建 FAISS 索引。"""

        if not self.documents:
            raise RuntimeError(
                "知识库为空，无法创建 FAISS 索引"
            )

        logger.info(
            "Creating FAISS index with "
            "Qwen3-Embedding..."
        )

        start = time.perf_counter()

        # 文档不使用 query prompt
        embeddings = self.embedding_model.encode(
            self.documents,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=True,
            batch_size=8,
        )

        embeddings = np.asarray(
            embeddings,
            dtype="float32",
        )

        dimension = embeddings.shape[1]

        # 向量已经 L2 normalize，
        # Inner Product 等价于 cosine similarity。
        self.index = faiss.IndexFlatIP(
            dimension
        )

        self.index.add(embeddings)

        index_dir = os.path.dirname(
            self.index_path
        )

        if index_dir:
            os.makedirs(
                index_dir,
                exist_ok=True,
            )

        # 不让 FAISS 直接操作中文 Windows 路径；
        # 通过 serialize_index + Python 文件 IO 绕过路径接口问题。
        serialized = faiss.serialize_index(self.index)

        with open(self.index_path, "wb") as f:
            f.write(serialized.tobytes())

        logger.info(
            "FAISS index created: "
            "%d vectors, dim=%d, time=%.3fs",
            self.index.ntotal,
            dimension,
            time.perf_counter() - start,
        )

    def query(
        self,
        query_text: str,
        n_results: int = 1,
    ) -> dict:
        """
        纯 Qwen3 Embedding + FAISS 检索。
        关键词相关逻辑已不参与查询流程。
        """
        if not query_text or not query_text.strip():
            return {
                "documents": [],
                "metadatas": [],
                "scores": [],
            }

        start = time.perf_counter()

        query_embedding = self.embedding_model.encode(
            [query_text],
            prompt_name="query",
            normalize_embeddings=True,
            convert_to_numpy=True,
        ).astype("float32")

        search_k = min(
            max(n_results * 3, n_results),
            self.index.ntotal,
        )

        scores, indices = self.index.search(
            query_embedding,
            search_k,
        )

        documents = []
        metadatas = []
        result_scores = []

        for score, idx in zip(
            scores[0],
            indices[0],
        ):
            if idx < 0:
                continue

            score = float(score)

            if score < EMBEDDING_MIN_SIMILARITY:
                continue

            documents.append(self.documents[idx])
            metadatas.append(self.metadatas[idx])
            result_scores.append(score)

            if len(documents) >= n_results:
                break

        logger.info(
            "FAISS query: %s | scores=%s | %.3fs",
            query_text,
            [round(x, 4) for x in result_scores],
            time.perf_counter() - start,
        )

        return {
            "documents": documents,
            "metadatas": metadatas,
            "scores": result_scores,
        }

    def _load_keywords(self):
        with open(
            FAISS_KEYWORD_PATH,
            "r",
            encoding="utf-8",
        ) as f:
            self.KeyWord = dict(
                json.load(f)
            )

    def KeySearch(self, query_text):
        total_index = []
        final_list = []

        split_data = jieba.lcut(
            query_text
        )

        for word in split_data:
            if word in self.KeyWord:
                total_index.extend(
                    self.KeyWord[word]
                )

        index_dict = dict(
            Counter(
                total_index
            ).most_common(3)
        )

        counts = sorted(
            list(
                set(index_dict.values())
            ),
            reverse=True,
        )

        for index, count in index_dict.items():
            if len(counts) == 1:
                final_list.append(index)

            elif (
                len(counts) != 1
                and count >= counts[1]
            ):
                final_list.append(index)

        return final_list


if __name__ == "__main__":
    start_time = time.perf_counter()

    db = FaissDB(
        EMBEDDING_MODEL_PATH,
        FAISS_INDEX_PATH,
        JSONL_DATA_PATH,
    )

    print(
        "初始化时间：",
        time.perf_counter() - start_time,
    )

    while True:
        text = input(
            "\n请输入检索问题（q退出）："
        ).strip()

        if text.lower() == "q":
            break

        start = time.perf_counter()

        results = db.query(
            text,
            5,
        )

        print(
            json.dumps(
                results,
                ensure_ascii=False,
                indent=2,
            )
        )

        print(
            "查询耗时：",
            time.perf_counter() - start,
        )