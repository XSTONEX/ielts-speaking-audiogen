#!/usr/bin/env python3
"""
一次性脚本：为现有的高亮词汇生成音频文件
用法：python3 generate_existing_vocab_audio.py
"""

import os
import json
import time
from app import generate_and_save_vocab_audio, INTENSIVE_DIR

def main():
    print("开始为现有高亮词汇生成音频...")
    
    # 统计信息
    total_articles = 0
    total_highlights = 0
    generated_audio = 0
    skipped_audio = 0
    failed_audio = 0
    
    # 遍历所有文章文件
    if not os.path.exists(INTENSIVE_DIR):
        print(f"精读文章目录不存在: {INTENSIVE_DIR}")
        return
    
    for filename in os.listdir(INTENSIVE_DIR):
        if not filename.endswith('.json'):
            continue
            
        article_path = os.path.join(INTENSIVE_DIR, filename)
        article_id = filename[:-5]  # 移除 .json 后缀
        
        try:
            with open(article_path, 'r', encoding='utf-8') as f:
                article_data = json.load(f)
            
            total_articles += 1
            highlights = article_data.get('highlights', [])
            
            if not highlights:
                print(f"📄 文章 {article_id}: 无高亮词汇")
                continue
            
            print(f"📄 处理文章 {article_id}: 发现 {len(highlights)} 个高亮词汇")
            total_highlights += len(highlights)
            
            for highlight in highlights:
                word = highlight.get('text', '').strip()
                if not word:
                    print(f"  ⚠️  跳过空词汇")
                    skipped_audio += 1
                    continue
                
                # 检查音频是否已存在
                from app import get_vocab_audio_path
                audio_path = get_vocab_audio_path(article_id, word)
                
                if os.path.exists(audio_path):
                    print(f"  ✅ 音频已存在: {word}")
                    skipped_audio += 1
                    continue
                
                # 生成音频
                print(f"  🎵 生成音频: {word}")
                result = generate_and_save_vocab_audio(article_id, word)
                
                if result and os.path.exists(result):
                    print(f"  ✅ 生成成功: {word}")
                    generated_audio += 1
                else:
                    print(f"  ❌ 生成失败: {word}")
                    failed_audio += 1
                
                # 避免API频率限制
                time.sleep(0.5)
                
        except Exception as e:
            print(f"❌ 处理文章 {article_id} 时出错: {e}")
            continue
    
    # 输出统计结果
    print("\n" + "="*50)
    print("📊 生成统计报告")
    print("="*50)
    print(f"📁 处理文章数量: {total_articles}")
    print(f"🔤 发现高亮词汇: {total_highlights}")
    print(f"🎵 新生成音频: {generated_audio}")
    print(f"⏭️  跳过已存在: {skipped_audio}")
    print(f"❌ 生成失败: {failed_audio}")
    print(f"✅ 成功率: {(generated_audio / max(1, generated_audio + failed_audio)) * 100:.1f}%")
    print("="*50)
    
    if failed_audio > 0:
        print("⚠️  有部分音频生成失败，可能是由于网络问题或API限制")
        print("   可以稍后重新运行此脚本来重试失败的音频")

if __name__ == "__main__":
    main()
