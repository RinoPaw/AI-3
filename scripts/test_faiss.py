import time
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

print("开始导入 FaissVectorStore...")
from mudan.vector_store import FaissVectorStore
from mudan.config import EMBEDDING_MODEL_PATH, FAISS_INDEX_PATH, FAISS_DATA_PATH

print("开始初始化数据库...")
start = time.time()

db = FaissVectorStore(
    model_path=EMBEDDING_MODEL_PATH,
    index_path=FAISS_INDEX_PATH,
    json_path=FAISS_DATA_PATH
)

print(f"数据库初始化完成，用时 {time.time() - start:.2f} 秒")

questions = [
    "太极拳是什么？",
    "二十四节气有什么价值？",
    "信阳毛尖制作技艺介绍一下",
    "罗山皮影戏有什么特色？",
]

for q in questions:
    print("=" * 80)
    print("问题：", q)

    start = time.time()
    result = db.query(q, n_results=3)
    print(f"查询用时 {time.time() - start:.2f} 秒")

    print("返回数量：", len(result["documents"]))

    for i, doc in enumerate(result["documents"], start=1):
        print(f"\n结果 {i}:")
        print(doc[:500])
        print("-" * 40)
