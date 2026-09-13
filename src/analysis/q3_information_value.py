"""Q3 Vdk 已验证诊断的只读索引；不在 reference 分支重新计算。"""

from pathlib import Path
import json

SOURCE_COMMIT = "c5c5bf959c8ef54828ac1618ea1ee97f4a7443e8"


def load_validated(root):
    """读取已验证分支导出的Vdk结果，明确禁止把它当作本分支重算结果。"""
    path = Path(root) / "outputs/model_validation/q3_information_value/q3_information_value.json"
    result = json.loads(path.read_text(encoding="utf-8"))
    if result.get("source_commit") != SOURCE_COMMIT or result.get("status") != "validated":
        raise ValueError("Vdk来源提交或验收状态不符")
    return result
