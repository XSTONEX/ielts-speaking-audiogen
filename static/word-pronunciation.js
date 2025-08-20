/**
 * 词汇发音管理器
 * 直接从后端获取预生成的音频文件
 */
class WordPronunciationManager {
  constructor() {
    this.currentAudio = null; // 当前播放的音频
    this.loadingSet = new Set(); // 正在加载的词汇集合
  }

  /**
   * 播放单词发音
   * @param {string} word - 要发音的单词
   * @param {string} articleId - 文章ID（必需，用于定位音频文件）
   * @returns {Promise<boolean>} - 是否播放成功
   */
  async playWord(word, articleId) {
    if (!word || typeof word !== 'string') {
      console.warn('Invalid word provided:', word);
      return false;
    }

    if (!articleId) {
      console.warn('Article ID is required for audio playback');
      return false;
    }

    const normalizedWord = word.trim().toLowerCase();
    const playKey = `${articleId}-${normalizedWord}`;
    
    // 如果已经在加载，避免重复请求
    if (this.loadingSet.has(playKey)) {
      return false;
    }

    try {
      // 停止当前播放的音频
      this.stopCurrentAudio();

      this.loadingSet.add(playKey);
      
      // 直接从后端获取预生成的音频文件
      const audioUrl = `/vocab_audio/${encodeURIComponent(articleId)}/${encodeURIComponent(normalizedWord)}`;
      
      // 播放音频
      await this.playAudioFromUrl(audioUrl);
      return true;
    } catch (error) {
      console.error('Error playing word pronunciation:', error);
      return false;
    } finally {
      this.loadingSet.delete(playKey);
    }
  }

  /**
   * 直接播放URL音频
   * @param {string} audioUrl - 音频文件URL
   * @returns {Promise<void>}
   */
  async playAudioFromUrl(audioUrl) {
    return new Promise((resolve, reject) => {
      const audio = new Audio(audioUrl);
      
      this.currentAudio = audio;

      audio.onended = () => {
        this.currentAudio = null;
        resolve();
      };

      audio.onerror = (error) => {
        this.currentAudio = null;
        console.error('Audio playback error:', error);
        reject(new Error('音频文件不存在或播放失败'));
      };

      audio.play().catch(reject);
    });
  }



  /**
   * 停止当前播放的音频
   */
  stopCurrentAudio() {
    if (this.currentAudio) {
      this.currentAudio.pause();
      this.currentAudio.currentTime = 0;
      this.currentAudio = null;
    }
  }

  /**
   * 获取状态统计信息
   * @returns {Object} 状态统计
   */
  getStats() {
    return {
      loadingWords: this.loadingSet.size,
      isPlaying: this.currentAudio !== null
    };
  }
}



// 创建全局实例
const wordPronunciation = new WordPronunciationManager();

// 导出到全局作用域
window.wordPronunciation = wordPronunciation;

/**
 * 便捷函数：播放单词发音
 * @param {string} word - 要发音的单词
 * @param {string} articleId - 文章ID（必需）
 * @returns {Promise<boolean>} - 是否播放成功
 */
window.playWordPronunciation = function(word, articleId) {
  if (!articleId) {
    console.warn('Article ID is required for word pronunciation');
    return Promise.resolve(false);
  }
  return wordPronunciation.playWord(word, articleId);
};
