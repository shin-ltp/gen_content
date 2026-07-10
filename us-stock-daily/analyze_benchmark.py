import re
from collections import Counter

# 读取转录文本
with open('/c/my_project/gen-contents/us-stock-daily/benchmark_transcript.txt', 'r', encoding='utf-8') as f:
    content = f.read()

# 解析时间戳和内容
segments = []
for line in content.strip().split('\n'):
    match = re.match(r'\[([\d.]+)s - ([\d.]+)s\] (.+)', line.strip())
    if match:
        start = float(match.group(1))
        end = float(match.group(2))
        text = match.group(3)
        segments.append({
            'start': start,
            'end': end,
            'duration': end - start,
            'text': text
        })

# 手动识别章节（基于内容关键词和时间戳）
chapters = [
    {'name': '开场市场概览', 'start': 0, 'end': 68.4},
    {'name': '美联储会议纪要', 'start': 68.4, 'end': 314.2},
    {'name': '动量股/AI交易分析', 'start': 326.0, 'end': 569.0},
    {'name': 'Anthropic商业模式分析', 'start': 570.0, 'end': 1012.0},
    {'name': '比特币分析', 'start': 1013.0, 'end': 1203.0},
    {'name': '彭博五大科技新闻', 'start': 1203.0, 'end': 1298.0},
    {'name': '结尾/广告', 'start': 1298.0, 'end': 1378.0}
]

# 计算每个章节的时长
for ch in chapters:
    ch['duration'] = ch['end'] - ch['start']

total_duration = segments[-1]['end']

print("=" * 80)
print("视频结构分析 - 美投侃新闻频道方法论")
print("=" * 80)
print(f"\n总时长: {total_duration:.0f}秒 ({total_duration/60:.1f}分钟)")
print(f"总片段数: {len(segments)}")
print()

print("章节时间分配:")
print("-" * 80)
for i, ch in enumerate(chapters, 1):
    percentage = (ch['duration'] / total_duration) * 100
    print(f"{i}. {ch['name']}")
    print(f"   时长: {ch['duration']:.0f}秒 ({ch['duration']/60:.1f}分钟)")
    print(f"   占比: {percentage:.1f}%")
    print(f"   时间段: {ch['start']:.0f}s - {ch['end']:.0f}s ({ch['start']/60:.1f}分-{ch['end']/60:.1f}分)")
    print()

# 统计关键特征
print("=" * 80)
print("内容特征统计")
print("=" * 80)

full_text = ' '.join([seg['text'] for seg in segments])

# 统计引用来源
sources = {
    '高盛': full_text.count('高盛') + full_text.count('高胜'),
    '瑞银': full_text.count('瑞瑩') + full_text.count('瑞银'),
    '彭博': full_text.count('彭博'),
    'SemiAnalysis': full_text.count('SemiAnalysis') + full_text.count('Sammy analysis') + full_text.count('Samiya Nilesis') + full_text.count('3面NALISIS'),
    '美联储': full_text.count('美联储') + full_text.count('美聯儲'),
    'Glassnote': full_text.count('Glassnote'),
}

print("\n权威来源引用频次:")
for source, count in sorted(sources.items(), key=lambda x: x[1], reverse=True):
    if count > 0:
        print(f"  {source}: {count}次")

# 统计数字和百分比
numbers = re.findall(r'\d+\.?\d*%', full_text)
print(f"\n百分比数据出现次数: {len(numbers)}")
print(f"示例: {', '.join(numbers[:15])}")

# 统计主持人个人观点标记
personal_markers = (full_text.count('JSON认为') + full_text.count('Json认为') + 
                   full_text.count('我认为') + full_text.count('我觉得'))
print(f"\n主持人个人观点标记: {personal_markers}次")
print(f"  - '我认为': {full_text.count('我认为')}次")
print(f"  - '我觉得': {full_text.count('我觉得')}次")
print(f"  - 'JSON/Json认为': {full_text.count('JSON认为') + full_text.count('Json认为')}次")

# 统计互动用语
interaction_words = ['大家', '观众', '你们', '我们', '朋友们']
interaction_count = sum(full_text.count(word) for word in interaction_words)
print(f"\n互动用语: {interaction_count}次")
for word in interaction_words:
    count = full_text.count(word)
    if count > 0:
        print(f"  - '{word}': {count}次")

# 分析开场白结构
print("\n" + "=" * 80)
print("开场白结构分析 (0-68秒)")
print("=" * 80)
opening_segments = [seg for seg in segments if seg['start'] < 68.4]
opening_text = '\n'.join([f"[{seg['start']:.0f}s] {seg['text']}" for seg in opening_segments])
print(opening_text[:1500])

# 分析章节过渡
print("\n" + "=" * 80)
print("章节过渡话术")
print("=" * 80)
transitions = []
for ch in chapters[1:]:
    # 找到章节开始附近的片段
    nearby_segs = [seg for seg in segments if abs(seg['start'] - ch['start']) < 5]
    if nearby_segs:
        transitions.append({
            'to_chapter': ch['name'],
            'transition_text': nearby_segs[0]['text']
        })

for t in transitions:
    print(f"\n→ {t['to_chapter']}:")
    print(f"   {t['transition_text'][:150]}")

