#!/usr/bin/env python3
"""
一次性脚本：重新生成失败的词汇音频任务
功能：
  - 重新生成失败的音频任务
  - 自动检测超时的processing任务（超过30分钟），将其标记为失败后重新处理
用法：
  python3 retry_failed_vocab_audio.py              # 默认重置模式：重置并重新生成所有失败任务
  python3 retry_failed_vocab_audio.py --no-reset  # 不重置：只处理当前失败的任务
"""

import os
import json
import time
import sys
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 目录配置
VOCABULARY_BOOK_DIR = 'vocabulary_book'
VOCABULARY_TASKS_DIR = os.path.join(VOCABULARY_BOOK_DIR, 'tasks')
VOCABULARY_CATEGORIES_DIR = os.path.join(VOCABULARY_BOOK_DIR, 'categories')
VOCABULARY_AUDIO_DIR = os.path.join(VOCABULARY_BOOK_DIR, 'audio')

def load_category_data(category):
    """加载分类数据"""
    category_file = os.path.join(VOCABULARY_CATEGORIES_DIR, f'{category}.json')
    if os.path.exists(category_file):
        with open(category_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    return None

def save_category_data(category, data):
    """保存分类数据"""
    category_file = os.path.join(VOCABULARY_CATEGORIES_DIR, f'{category}.json')
    with open(category_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def generate_word_audio(word, word_id, category):
    """为单词生成音频文件"""
    try:
        # 获取API密钥
        api_key = os.getenv('DEER_API_KEY')
        if not api_key:
            print("❌ 未找到DEER_API_KEY环境变量")
            return False

        # 确保音频目录存在
        category_audio_dir = os.path.join(VOCABULARY_AUDIO_DIR, category)
        os.makedirs(category_audio_dir, exist_ok=True)

        # 检查音频是否已存在
        audio_path = os.path.join(category_audio_dir, f"{word_id}.mp3")
        if os.path.exists(audio_path):
            print(f"✅ 音频文件已存在: {word}")
            return True

        print(f"🎵 正在生成音频: {word}")

        # 调用TTS API
        url = "https://api.deerapi.com/v1/audio/speech"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        data = {
            "model": "tts-1",
            "input": word,
            "voice": "nova",
            "response_format": "mp3"
        }

        response = requests.post(url, headers=headers, json=data, timeout=60)

        if response.status_code == 200:
            # 保存音频文件
            with open(audio_path, 'wb') as f:
                f.write(response.content)
            print(f"✅ 音频生成成功: {word}")
            return True
        else:
            print(f"❌ API调用失败 ({response.status_code}): {word}")
            return False

    except Exception as e:
        print(f"❌ 生成音频时出错: {word} - {e}")
        return False

def update_task_status(task_file, status, error_msg=None):
    """更新任务状态"""
    try:
        with open(task_file, 'r', encoding='utf-8') as f:
            task = json.load(f)

        task['status'] = status
        task['last_updated'] = datetime.now().isoformat()

        if error_msg:
            task['error'] = error_msg
            task['attempts'] = task.get('attempts', 0) + 1
        elif status == 'completed':
            task['attempts'] = task.get('attempts', 0) + 1

        with open(task_file, 'w', encoding='utf-8') as f:
            json.dump(task, f, ensure_ascii=False, indent=2)

    except Exception as e:
        print(f"❌ 更新任务状态失败: {e}")

def update_category_word_status(category, subcategory_id, word_id, audio_generated):
    """更新分类中单词的音频生成状态"""
    try:
        category_data = load_category_data(category)
        if not category_data:
            return False

        if subcategory_id in category_data['subcategories']:
            for word in category_data['subcategories'][subcategory_id]['words']:
                if word['id'] == word_id:
                    word['audio_generated'] = audio_generated
                    save_category_data(category, category_data)
                    return True

        return False
    except Exception as e:
        print(f"❌ 更新分类状态失败: {e}")
        return False

def is_task_timeout(task):
    """检查任务是否超时（processing状态超过30分钟）"""
    if task.get('status') != 'processing':
        return False

    created_at_str = task.get('created_at')
    if not created_at_str:
        return False

    try:
        # 解析创建时间
        created_at = datetime.fromisoformat(created_at_str.replace('Z', '+00:00'))
        # 计算时间差
        time_diff = datetime.now() - created_at
        # 检查是否超过30分钟
        return time_diff > timedelta(minutes=30)
    except Exception as e:
        print(f"⚠️ 解析创建时间失败: {created_at_str} - {e}")
        return False

def mark_processing_task_as_failed(task_file):
    """将超时的processing任务标记为failed"""
    try:
        with open(task_file, 'r', encoding='utf-8') as f:
            task = json.load(f)

        task['status'] = 'failed'
        task['error'] = '任务处理超时（超过30分钟）'
        task['last_updated'] = datetime.now().isoformat()
        task['attempts'] = task.get('attempts', 0) + 1

        with open(task_file, 'w', encoding='utf-8') as f:
            json.dump(task, f, ensure_ascii=False, indent=2)

        return task.get('word', 'unknown')
    except Exception as e:
        print(f"❌ 标记任务失败失败: {e}")
        return None

def reset_failed_tasks():
    """重置所有失败任务的重试计数"""
    print("🔄 重置失败任务的重试计数...")
    reset_count = 0

    if not os.path.exists(VOCABULARY_TASKS_DIR):
        print(f"❌ 任务目录不存在: {VOCABULARY_TASKS_DIR}")
        return 0

    for filename in os.listdir(VOCABULARY_TASKS_DIR):
        if filename.endswith('.json'):
            task_file = os.path.join(VOCABULARY_TASKS_DIR, filename)

            try:
                with open(task_file, 'r', encoding='utf-8') as f:
                    task = json.load(f)

                if task.get('status') == 'failed':
                    task['attempts'] = 0
                    task['last_updated'] = datetime.now().isoformat()

                    with open(task_file, 'w', encoding='utf-8') as f:
                        json.dump(task, f, ensure_ascii=False, indent=2)

                    reset_count += 1
                    print(f"🔄 重置任务: {task.get('word', 'unknown')}")

            except Exception as e:
                print(f"❌ 处理任务文件失败 {filename}: {e}")

    print(f"✅ 已重置 {reset_count} 个失败任务的重试计数")
    return reset_count

def main():
    # 处理命令行参数
    reset_mode = True  # 默认重置模式
    if len(sys.argv) > 1 and sys.argv[1] == '--no-reset':
        reset_mode = False

    if reset_mode:
        print("🔄 默认重置模式：重置失败任务的重试计数后重新生成")
        print("="*60)
        reset_failed_tasks()
        print()
    else:
        print("🔄 非重置模式：只处理当前失败的任务...")
        print("="*60)

    # 统计信息
    total_failed_tasks = 0
    timeout_tasks_marked = 0
    successful_regenerations = 0
    failed_regenerations = 0
    skipped_tasks = 0

    # 检查任务目录是否存在
    if not os.path.exists(VOCABULARY_TASKS_DIR):
        print(f"❌ 任务目录不存在: {VOCABULARY_TASKS_DIR}")
        return

    # 扫描所有任务文件
    task_files = []
    for filename in os.listdir(VOCABULARY_TASKS_DIR):
        if filename.endswith('.json'):
            task_files.append(filename)

    if not task_files:
        print("ℹ️ 没有找到任何任务文件")
        return

    print(f"📋 发现 {len(task_files)} 个任务文件")

    # 处理每个任务文件
    for filename in task_files:
        task_file = os.path.join(VOCABULARY_TASKS_DIR, filename)

        try:
            # 读取任务数据
            with open(task_file, 'r', encoding='utf-8') as f:
                task = json.load(f)

            # 检查任务状态
            task_status = task.get('status', 'unknown')
            word = task.get('word', 'unknown')

            # 检查是否是超时的processing任务
            if task_status == 'processing' and is_task_timeout(task):
                print(f"⏰ 发现超时任务，将标记为失败: {word} (ID: {task.get('id', 'unknown')})")
                marked_word = mark_processing_task_as_failed(task_file)
                if marked_word:
                    task_status = 'failed'  # 更新状态以便继续处理
                    timeout_tasks_marked += 1
                    print(f"✅ 已将超时任务标记为失败: {marked_word}")
                else:
                    print(f"❌ 标记超时任务失败失败: {word}")
                    skipped_tasks += 1
                    continue

            # 只处理失败的任务
            if task_status != 'failed':
                print(f"⏭️ 跳过非失败任务: {word} ({task_status})")
                skipped_tasks += 1
                continue

            total_failed_tasks += 1
            word = task.get('word', '')
            word_id = task.get('word_id', '')
            category = task.get('category', '')
            subcategory_id = task.get('subcategory_id', '')

            print(f"\n🔄 处理失败任务: {word} (ID: {word_id})")

            # 检查重试次数
            attempts = task.get('attempts', 0)
            max_attempts = task.get('max_attempts', 3)

            if attempts >= max_attempts:
                print(f"⚠️ 任务已达到最大重试次数 ({max_attempts})，跳过")
                skipped_tasks += 1
                continue

            # 生成音频
            success = generate_word_audio(word, word_id, category)

            if success:
                # 更新任务状态为完成
                update_task_status(task_file, 'completed')

                # 更新分类中的单词状态
                update_category_word_status(category, subcategory_id, word_id, True)

                # 删除成功完成的任务文件
                try:
                    os.remove(task_file)
                    print(f"🗑️  删除完成任务文件: {word}")
                except Exception as e:
                    print(f"⚠️  删除任务文件失败: {word} - {e}")

                successful_regenerations += 1
                print(f"✅ 任务重新生成成功: {word}")
            else:
                # 更新任务状态为失败（增加重试次数）
                update_task_status(task_file, 'failed', '音频生成API调用失败')

                failed_regenerations += 1
                print(f"❌ 任务重新生成失败: {word}")

            # 避免API频率限制
            time.sleep(0.5)

        except Exception as e:
            print(f"❌ 处理任务文件失败 {filename}: {e}")
            failed_regenerations += 1
            continue

    # 输出统计结果
    print("\n" + "="*60)
    print("📊 重新生成统计报告")
    print("="*60)
    print(f"📁 总任务文件数: {len(task_files)}")
    print(f"⏰ 标记超时任务数: {timeout_tasks_marked}")
    print(f"❌ 失败任务数: {total_failed_tasks}")
    print(f"⏭️  跳过任务数: {skipped_tasks}")
    print(f"✅ 重新生成成功: {successful_regenerations}")
    print(f"❌ 重新生成失败: {failed_regenerations}")
    print(f"✅ 成功率: {(successful_regenerations / max(1, successful_regenerations + failed_regenerations)) * 100:.1f}%")
    if failed_regenerations > 0:
        print("⚠️  部分任务重新生成失败，可能需要检查网络连接或API密钥")
        print("   可以稍后重新运行此脚本来重试失败的任务")

    print("="*60)

if __name__ == "__main__":
    main()
