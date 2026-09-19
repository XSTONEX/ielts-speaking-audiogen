from flask import Flask, request
from core import init_directories

# 创建 Flask 应用
app = Flask(__name__, static_folder='static', static_url_path='/static')

# 初始化目录
init_directories()

# 注册所有 Blueprint（无 prefix，保持原有 URL）
from routers.auth import auth_bp
from routers.speaking import speaking_bp
from routers.speaking_playlist import speaking_playlist_bp
from routers.reading import reading_bp
from routers.intensive_reading import intensive_reading_bp
from routers.community import community_bp
from routers.vocabulary import vocabulary_bp
from routers.study_tips import study_tips_bp
from routers.asr_transcription import asr_bp
from routers.writing_logic import writing_bp
from routers.listening_review import listening_review_bp
from routers.learning import learning_bp

app.register_blueprint(auth_bp)
app.register_blueprint(speaking_bp)
app.register_blueprint(speaking_playlist_bp)
app.register_blueprint(reading_bp)
app.register_blueprint(intensive_reading_bp)
app.register_blueprint(community_bp)
app.register_blueprint(vocabulary_bp)
app.register_blueprint(study_tips_bp)
app.register_blueprint(asr_bp)
app.register_blueprint(writing_bp)
app.register_blueprint(listening_review_bp)
app.register_blueprint(learning_bp)

# ==================== 文本类响应 gzip ====================
# 手机上最贵的是字节数。/list_audio 这类 JSON 原始体积近 100KB，
# gzip 后通常只剩两成左右。音频/图片本身已压缩，跳过不处理。
import gzip as _gzip

_COMPRESSIBLE_PREFIXES = ('text/', 'application/json', 'application/javascript', 'image/svg+xml')
_COMPRESS_MIN_BYTES = 1024


@app.after_request
def _compress_text_responses(response):
    try:
        if response.status_code >= 300:
            return response
        if 'gzip' not in request.headers.get('Accept-Encoding', ''):
            return response
        if response.headers.get('Content-Encoding'):
            return response
        # 先判类型再判 passthrough：模板页是 send_file 送出的，处于 direct_passthrough
        # 模式，早退就会漏掉它们 —— 而这些 HTML 恰恰是最大的一笔流量
        # （单词本页 182KB）。音频是 audio/mpeg，在这一步就被排除，不会被读进内存。
        ctype = (response.content_type or '').split(';')[0].strip()
        if not ctype.startswith(_COMPRESSIBLE_PREFIXES):
            return response
        if response.direct_passthrough:
            response.direct_passthrough = False
        data = response.get_data()
        if len(data) < _COMPRESS_MIN_BYTES:
            return response
        response.set_data(_gzip.compress(data, 6))
        response.headers['Content-Encoding'] = 'gzip'
        response.headers['Content-Length'] = len(response.get_data())
        response.headers.add('Vary', 'Accept-Encoding')
    except Exception:
        # 压缩只是优化，任何异常都不应该影响正常响应
        return response
    return response


# 启动词汇音频后台任务处理器
from routers.vocabulary import start_audio_task_processor
start_audio_task_processor()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001)
