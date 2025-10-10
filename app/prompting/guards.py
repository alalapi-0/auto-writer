"""质量闸门：对生成文本执行多项指标评估，返回结构化评分。"""

from __future__ import annotations  # 启用未来注解语法

import re  # 构建正则模式
from collections import Counter  # 计算词频
from dataclasses import dataclass, field  # 构造报告数据结构
from datetime import datetime, timedelta  # 计算时间窗口
from typing import Dict, Iterable, List, Mapping  # 类型提示

from sqlalchemy.orm import Session  # SQLAlchemy 会话类型

from config.settings import BASE_DIR  # 引入项目根目录，用于定位词典
from app.db import models  # 引入 ORM 模型以获取历史文章

try:  # 尝试引入 sklearn 以计算 TF-IDF 余弦相似度
    from sklearn.feature_extraction.text import TfidfVectorizer  # TF-IDF 向量器
    from sklearn.metrics.pairwise import cosine_similarity  # 余弦相似度

    SKLEARN_AVAILABLE = True  # 标记 sklearn 可用
except Exception:  # noqa: BLE001
    SKLEARN_AVAILABLE = False  # 标记 sklearn 不可用并在下方提供降级方案

# 定义质量指标的目标区间与敏感模式
MIN_WORDS = 1800  # 字数下限
MAX_WORDS = 2300  # 字数上限
STOPWORDS = {  # 基础停用词集合，用于估算可读性
    "的",
    "了",
    "以及",
    "但是",
    "因为",
    "所以",
    "我们",
    "他们",
    "那些",
    "这些",
    "一种",
    "一个",
    "进行",
}  # 可根据 data/style_words.txt 增补
STYLE_WORD_PATH = BASE_DIR / "data" / "style_words.txt"  # 用户可扩展的风格词典路径
SENSITIVE_PATTERNS = [  # 敏感模式正则列表
    re.compile(r"呼吁|号召|必须立即|立刻行动"),  # 呼吁性语言
    re.compile(r"\b(?:我|我们|本人)\b"),  # 第一人称
    re.compile(r"[“\"]{1}[^”\"]+[”\"]{1}"),  # 中文或英文引号内引用
    re.compile(r"[「『][^」』]+[」』]"),  # 引用台词
]


@dataclass
class QualityReport:  # 质量报告数据结构
    """统一封装质量评估结果。"""

    passed: bool  # 是否通过
    scores: Dict[str, float] = field(default_factory=dict)  # 指标分数
    reasons: List[str] = field(default_factory=list)  # 未通过原因
    details: Dict[str, object] = field(default_factory=dict)  # 附加细节


def _load_style_words() -> Iterable[str]:  # 加载自定义风格词典
    """读取 data/style_words.txt 中的风格词汇，以增强风格一致性校验。"""

    if STYLE_WORD_PATH.exists():  # 若文件存在
        return [line.strip() for line in STYLE_WORD_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]  # 返回非空行
    return []  # 默认返回空列表


def _tokenize(text: str) -> List[str]:  # 简易分词，将中文和英文词语拆分
    """使用正则提取中文或英文的连续片段，兼顾数字。"""

    return re.findall(r"[\w\u4e00-\u9fff]+", text)  # 返回匹配到的词列表


def _calc_word_count(content: str) -> int:  # 计算字数
    """通过统计非空白字符数量估算字数。"""

    return len(re.sub(r"\s+", "", content))  # 删除空白并取长度


def _calc_readability(content: str) -> Dict[str, float]:  # 计算可读性指标
    """返回句长、段落密度与停用词占比。"""

    sentences = [s for s in re.split(r"[。！？!?]", content) if s.strip()]  # 划分句子
    avg_sentence_length = sum(len(s) for s in sentences) / len(sentences) if sentences else len(content)  # 平均句长
    paragraphs = [p for p in content.splitlines() if p.strip()]  # 统计有效段落
    paragraph_density = len(sentences) / len(paragraphs) if paragraphs else len(sentences)  # 段落密度
    tokens = _tokenize(content)  # 分词
    stopword_hits = sum(1 for token in tokens if token in STOPWORDS)  # 停用词数量
    stopword_ratio = stopword_hits / len(tokens) if tokens else 0.0  # 停用词占比
    return {
        "avg_sentence_length": avg_sentence_length,
        "paragraph_density": paragraph_density,
        "stopword_ratio": stopword_ratio,
    }  # 返回结构化指标


def _score_readability(metrics: Mapping[str, float]) -> float:  # 将可读性指标转为 0-1 分数
    """通过经验阈值将句长、段落密度与停用词占比转换为标准化得分。"""

    sentence_score = max(0.0, min(1.0, 45 / (metrics["avg_sentence_length"] or 1)))  # 句长越短得分越高
    density_target = 4  # 理想每段 4 句
    density_score = max(0.0, min(1.0, density_target / (metrics["paragraph_density"] or 1)))  # 密度越接近目标越高
    stopword_score = 1 - min(1.0, metrics["stopword_ratio"] * 2)  # 停用词占比高则扣分
    return (sentence_score + density_score + stopword_score) / 3  # 平均得到综合分


def _score_style(tokens: List[str], style_words: Iterable[str]) -> float:  # 风格一致性评分
    """计算词频特征与风格词覆盖率，输出 0-1 分数。"""

    if not tokens:  # 若无词
        return 0.0  # 返回 0 分
    freq = Counter(tokens)  # 统计词频
    most_common = [word for word, _ in freq.most_common(50)]  # 取前 50 高频词
    style_set = set(style_words)  # 风格词集合
    if not style_set:  # 若无自定义风格词典
        style_set = {"案例", "研究", "理论", "方法", "结论"}  # 提供默认集合
    overlap = len(style_set.intersection(most_common))  # 与高频词的交集数量
    coverage = overlap / len(style_set)  # 覆盖率
    density = sum(freq.get(word, 0) for word in style_set) / len(tokens)  # 风格词密度
    return max(0.0, min(1.0, (coverage + density) / 2))  # 综合覆盖与密度


def _compute_similarity(
    session: Session | None,
    content: str,
    title: str | None,
    keywords: Iterable[str] | None,
) -> float:  # 计算与历史文章的相似度
    """拉取 90 天内的文章内容并计算最大相似度。"""

    if session is None:  # 若未提供会话
        return 0.0  # 无历史数据则视为 0 相似度
    cutoff = datetime.utcnow() - timedelta(days=90)  # 计算时间窗口
    rows = (
        session.query(models.ArticleDraft)
        .filter(models.ArticleDraft.created_at >= cutoff)
        .all()
    )  # 查询历史文章
    if not rows:  # 若无历史数据
        return 0.0  # 返回 0
    corpus = []  # 历史语料列表
    for row in rows:  # 遍历历史记录
        payload = " ".join(filter(None, [row.title or "", row.content or ""]))
        corpus.append(payload)  # 拼接标题与正文
    current_text = " ".join(
        filter(None, [title or "", content, " ".join(keywords or [])])
    )  # 组合当前文本
    if SKLEARN_AVAILABLE:  # 若 sklearn 可用
        vectorizer = TfidfVectorizer(max_features=2000)  # 限制特征数量
        matrix = vectorizer.fit_transform(corpus + [current_text])  # 拟合并转换
        similarities = cosine_similarity(matrix[-1], matrix[:-1]).flatten()  # 计算与历史的相似度
        return float(similarities.max()) if similarities.size else 0.0  # 返回最大值
    # sklearn 不可用时使用 Jaccard 相似度降级
    current_tokens = set(_tokenize(current_text))  # 当前文本分词集合
    if not current_tokens:  # 无词时返回 0
        return 0.0
    max_similarity = 0.0  # 初始化最大值
    for doc in corpus:  # 遍历历史语料
        doc_tokens = set(_tokenize(doc))  # 历史文本词集合
        if not doc_tokens:
            continue
        union = current_tokens.union(doc_tokens)  # 并集
        intersection = current_tokens.intersection(doc_tokens)  # 交集
        similarity = len(intersection) / len(union) if union else 0.0  # Jaccard
        max_similarity = max(max_similarity, similarity)  # 记录最大值
    return max_similarity  # 返回最大 Jaccard 值


def _check_sensitive_patterns(content: str) -> List[str]:  # 检查敏感模式
    """返回命中的敏感短语或空列表。"""

    hits: List[str] = []  # 记录命中
    for pattern in SENSITIVE_PATTERNS:  # 遍历模式
        match = pattern.search(content)  # 匹配文本
        if match:
            hits.append(match.group())  # 记录命中片段
    return hits  # 返回命中列表


def evaluate_quality(
    content: str,
    *,
    title: str | None = None,
    keywords: Iterable[str] | None = None,
    session: Session | None = None,
) -> QualityReport:  # 主函数：对生成文本执行所有质量闸门
    """执行字数、可读性、风格一致性、重复度与敏感词校验。"""

    reasons: List[str] = []  # 初始化失败原因列表
    scores: Dict[str, float] = {}  # 初始化得分字典
    details: Dict[str, object] = {}  # 存储中间指标

    word_count = _calc_word_count(content)  # 计算字数
    scores["word_count"] = min(1.0, max(0.0, 1 - abs(word_count - 2050) / 400))  # 根据目标范围折算得分
    details["word_count"] = word_count  # 记录实际字数
    if word_count < MIN_WORDS or word_count > MAX_WORDS:  # 判断是否在目标区间
        reasons.append(f"字数 {word_count} 未命中范围 {MIN_WORDS}-{MAX_WORDS}")  # 记录原因

    readability_metrics = _calc_readability(content)  # 计算可读性
    readability_score = _score_readability(readability_metrics)  # 转换得分
    scores["readability"] = readability_score  # 记录得分
    details["readability"] = readability_metrics  # 保存原始指标
    if readability_score < 0.6:  # 若低于阈值
        reasons.append("可读性评分过低，句长或停用词比例异常")  # 记录原因

    tokens = _tokenize(content)  # 分词结果
    style_score = _score_style(tokens, _load_style_words())  # 计算风格分
    scores["style"] = style_score  # 记录风格得分
    if style_score < 0.5:  # 若风格覆盖不足
        reasons.append("未覆盖足够风格关键词，请检查风格词典配置")  # 记录原因

    similarity = _compute_similarity(session, content, title, keywords)  # 计算重复度
    scores["similarity"] = 1 - similarity  # 相似度越低越好
    details["similarity"] = similarity  # 记录原始相似度
    if similarity > 0.8:  # 超过 0.8 视为重复
        reasons.append(f"与历史文章相似度 {similarity:.2f} 过高")  # 记录原因

    sensitive_hits = _check_sensitive_patterns(content)  # 检查敏感模式
    if sensitive_hits:  # 若存在命中
        reasons.append(f"检测到敏感表达: {','.join(sensitive_hits[:3])}")  # 记录前几个命中
        scores["sensitive"] = 0.0  # 敏感词直接判 0
    else:
        scores["sensitive"] = 1.0  # 无敏感词得满分

    overall = sum(scores.values()) / len(scores) if scores else 0.0  # 平均值作为综合评分
    scores["overall"] = overall  # 记录综合分
    passed = not reasons and overall >= 0.75  # 无失败原因且综合分达标则通过

    return QualityReport(passed=passed, scores=scores, reasons=reasons, details=details)  # 返回报告
