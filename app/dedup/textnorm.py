"""文本归一化与签名工具，提供去除标点、半角转换以及 SimHash 计算能力。"""  # 模块中文说明确保满足注释要求
from __future__ import annotations  # 引入未来注解语法以兼容类型提示前置引用
import hashlib  # 导入哈希库用于计算 SHA256 与 MD5
import re  # 导入正则模块用于文本清洗
from typing import Iterable, Dict  # 引入类型提示以增强可读性
_FULL_WIDTH_START = 0xFF01  # 定义全角字符起始码位常量
_FULL_WIDTH_END = 0xFF5E  # 定义全角字符结束码位常量
_FULL_WIDTH_OFFSET = 0xFEE0  # 定义全角转半角的偏移量
_WS_RE = re.compile(r"\s+")  # 编译空白字符正则表达式
_PUNCT_RE = re.compile(r"[^\w\u4e00-\u9fff]+")  # 编译移除标点的正则表达式

def to_halfwidth(text: str) -> str:  # 定义全角转半角函数
    """将输入字符串中的全角字符转换为半角字符以统一签名。"""  # 函数中文文档说明
    result_chars: list[str] = []  # 初始化结果字符列表
    for ch in text:  # 遍历输入字符串中的每一个字符
        code = ord(ch)  # 获取当前字符的 Unicode 码位
        if code == 0x3000:  # 判断是否为全角空格
            code = 0x20  # 转换为半角空格码位
        elif _FULL_WIDTH_START <= code <= _FULL_WIDTH_END:  # 判断是否处于全角标点范围
            code -= _FULL_WIDTH_OFFSET  # 减去偏移量得到对应半角字符
        result_chars.append(chr(code))  # 将转换后的字符加入结果列表
    return "".join(result_chars)  # 拼接字符列表并返回转换结果

def normalize_text(text: str) -> str:  # 定义文本归一化函数
    """执行半角转换、小写化、去除标点及空白压缩的归一化流程。"""  # 函数中文文档说明
    text = to_halfwidth(text)  # 首先处理全角字符为半角
    text = text.lower()  # 将文本统一转换为小写
    text = _WS_RE.sub(" ", text)  # 合并连续空白为单个空格
    text = _PUNCT_RE.sub(" ", text)  # 移除除字母数字及中文外的字符
    text = _WS_RE.sub(" ", text).strip()  # 再次压缩空白并去除首尾空格
    return text  # 返回归一化后的文本

def sha256_signature(text: str) -> str:  # 定义 SHA256 签名函数
    """对文本执行 SHA256 摘要计算并返回十六进制字符串。"""  # 函数中文文档说明
    return hashlib.sha256(text.encode("utf-8")).hexdigest()  # 将文本编码后计算哈希并返回

def _collect_features(tokens: Iterable[str]) -> Dict[str, int]:  # 定义特征收集函数
    """统计 n-gram 词频以便 SimHash 构造带权向量。"""  # 函数中文文档说明
    counts: Dict[str, int] = {}  # 初始化词频映射
    for token in tokens:  # 遍历传入的所有 n-gram
        if not token:  # 跳过空字符串避免污染结果
            continue  # 继续处理下一个特征
        counts[token] = counts.get(token, 0) + 1  # 将词频累加一
    return counts  # 返回最终词频统计

def simhash(text: str, ngram: int = 3, bits: int = 64) -> int:  # 定义 SimHash 计算函数
    """使用字符 n-gram 及权重向量计算简化版 SimHash 值。"""  # 函数中文文档说明
    normalized = normalize_text(text)  # 对文本进行归一化以保证一致
    if not normalized:  # 若归一化后为空字符串
        return 0  # 直接返回零避免除零或空向量问题
    grams = [normalized[i : i + ngram] for i in range(max(0, len(normalized) - ngram + 1))]  # 生成定长 n-gram 列表
    features = _collect_features(grams)  # 获取带权特征
    vector = [0] * bits  # 初始化位向量用于累加
    for token, weight in features.items():  # 遍历每个特征及其权重
        digest = int(hashlib.md5(token.encode("utf-8")).hexdigest(), 16)  # 对特征使用 MD5 生成固定长度哈希
        for index in range(bits):  # 遍历哈希的每一位
            bit = (digest >> index) & 1  # 取出当前位的比特值
            if bit:  # 如果当前位为 1
                vector[index] += weight  # 将对应向量位置加上权重
            else:  # 如果当前位为 0
                vector[index] -= weight  # 将对应向量位置减去权重
    result = 0  # 初始化最终结果整数
    for index, value in enumerate(vector):  # 遍历累加后的向量值
        if value >= 0:  # 若该位值大于等于零
            result |= 1 << index  # 将该位设置为 1
    return result  # 返回最终 SimHash 整数

def hamming_distance(left: int, right: int) -> int:  # 定义汉明距离计算函数
    """计算两个整数的汉明距离用于衡量相似度。"""  # 函数中文文档说明
    return (left ^ right).bit_count()  # 通过异或再统计 1 的个数得到距离

def content_signature(text: str) -> str:  # 定义正文复合签名函数
    """结合 SHA256 与 SimHash 生成正文复合签名字符串。"""  # 函数中文文档说明
    normalized = normalize_text(text)  # 获取归一化正文
    sha = sha256_signature(normalized)  # 计算归一化正文的 SHA256
    sim = simhash(normalized)  # 计算归一化正文的 SimHash
    return f"{sha}-{sim:016x}"  # 拼接两个哈希构成最终签名

def title_signature(title: str) -> str:  # 定义标题签名函数
    """针对标题执行归一化后计算 SHA256 签名。"""  # 函数中文文档说明
    return sha256_signature(normalize_text(title))  # 归一化标题并返回哈希结果
