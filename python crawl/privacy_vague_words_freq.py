# 假设你已经把所有隐私政策文本保存在一个文件夹里
import os
import re
from collections import Counter
import jieba
import pandas as pd

# 种子模糊词（可从上面列表加载）
vague_seeds = set([
  "可以", "可能", "可能会", "或", "根据需要", "在必要时", "视情况",
  "一般", "通常", "大部分", "合理", "部分", "某些", "包括但不限于",
  # ... 继续添加
])

def is_vague_word(word):
  return word in vague_seeds or re.search(r'(合理|酌情|适时|视情况|根据需要)', word)

folder = "E:\\main files\\毕设-隐私政策模糊性评价方法研究与实现(综合型)\\python crawl"  
all_text = "E:\\main files\\毕设-隐私政策模糊性评价方法研究与实现(综合型)\\隐私政策模糊性词语数据集\\privacy_policies.txt"  # 你可以把所有文本合并成一个大字符串

for filename in os.listdir(folder):
  if filename.endswith(".txt"):
      with open(os.path.join(folder, filename), encoding="utf-8") as f:
          all_text += f.read() + "\n"

# 分词 & 统计
words = jieba.lcut(all_text)
word_freq = Counter(words)

# 筛选疑似模糊词
vague_found = []
for word, cnt in word_freq.most_common(3000):
  if is_vague_word(word) or len(word) >= 2 and cnt > 50:  # 简单过滤
      vague_found.append((word, cnt))

# 保存成 csv
df = pd.DataFrame(vague_found, columns=["词语", "出现次数"])
df.to_csv("E:\\main files\\毕设-隐私政策模糊性评价方法研究与实现(综合型)\\隐私政策模糊性词语数据集\\privacy_vague_words_freq.csv", index=False, encoding="utf-8-sig")

print("已统计出疑似模糊词，保存在 privacy_vague_words_freq.csv")