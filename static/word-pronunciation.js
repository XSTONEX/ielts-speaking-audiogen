/**
 * 词汇发音管理器（文章精读）
 * 和单词本一样，点的时候实时取有道词典的发音，不再预先生成、存储 TTS 音频。
 * 有道没有的词（拼错的、生造的）退回以前划词时生成过的 /vocab_audio/<文章>/<词>（有的话）。
 */
class WordPronunciationManager {
  constructor() {
    this.audio = null;    // 只用一个 Audio，换词时直接换 src
    this.playing = null;  // { text, sources, index, resolve }
  }

  static youdaoUrl(text) {
    return 'https://dict.youdao.com/dictvoice?audio=' + encodeURIComponent(text) + '&type=2';
  }

  /**
   * 播放单词发音
   * @param {string} word - 要发音的单词或短语
   * @param {string} [articleId] - 文章ID（只用来找以前存过的音频，没有也能播）
   * @returns {Promise<boolean>} - 是否播放成功
   */
  playWord(word, articleId) {
    const text = typeof word === 'string' ? word.trim().replace(/\s+/g, ' ') : '';
    if (!text) {
      console.warn('Invalid word provided:', word);
      return Promise.resolve(false);
    }
    this.stopCurrentAudio();
    if (!this.audio) {
      this.audio = new Audio();
      this.audio.addEventListener('error', () => { if (this.playing) this.nextSource(this.playing); });
      this.audio.addEventListener('ended', () => this.finish(this.playing, true));
    }
    const sources = [WordPronunciationManager.youdaoUrl(text)];
    if (articleId) sources.push(`/vocab_audio/${encodeURIComponent(articleId)}/${encodeURIComponent(text.toLowerCase())}`);
    return new Promise(resolve => {
      const current = { text, sources, index: 0, resolve };
      this.playing = current;
      this.nextSource(current);
    });
  }

  nextSource(current) {
    if (this.playing !== current) return;
    if (current.index >= current.sources.length) {
      console.warn(`没取到「${current.text}」的发音`);
      this.finish(current, false);
      return;
    }
    this.audio.src = current.sources[current.index++];
    const p = this.audio.play();
    if (p && p.catch) {
      p.catch(err => {
        // 加载失败由 error 事件换下一个来源；浏览器不让自动播放时安静地停下
        if (this.playing === current && err && err.name === 'NotAllowedError') this.finish(current, false);
      });
    }
  }

  finish(current, ok) {
    if (!current || this.playing !== current) return;
    this.playing = null;
    current.resolve(ok);
  }

  /**
   * 停止当前播放的音频
   */
  stopCurrentAudio() {
    if (this.playing) this.finish(this.playing, false);
    if (this.audio) this.audio.pause();
  }

  /**
   * 获取状态统计信息
   * @returns {Object} 状态统计
   */
  getStats() {
    return { isPlaying: this.playing !== null };
  }
}

// 创建全局实例
const wordPronunciation = new WordPronunciationManager();

// 导出到全局作用域
window.wordPronunciation = wordPronunciation;

/**
 * 便捷函数：播放单词发音
 * @param {string} word - 要发音的单词
 * @param {string} [articleId] - 文章ID
 * @returns {Promise<boolean>} - 是否播放成功
 */
window.playWordPronunciation = function(word, articleId) {
  return wordPronunciation.playWord(word, articleId);
};
