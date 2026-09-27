import logging

from flask import Flask, jsonify, request
from werkzeug.exceptions import RequestEntityTooLarge

from core import AuthStoreError, get_bearer_token, init_directories, resolve_token_user

# 创建 Flask 应用
app = Flask(__name__, static_folder='static', static_url_path='/static')

# 单个请求体的上限。最大的正常上传是 25MB 的听力/转写音频（各接口还会按 25MB / 10MB 再校验），
# 这里留一点 multipart 开销的余量；超过的请求直接 413，不会被读进内存或落盘。
MAX_REQUEST_BYTES = 30 * 1024 * 1024
app.config['MAX_CONTENT_LENGTH'] = MAX_REQUEST_BYTES

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

# ==================== 默认要求登录 ====================
# 所有请求默认都要带有效的 Authorization: Bearer <token>，只有下面列出的端点例外。
# 以后新加的路由自动受保护；确实需要公开的，才加进这里
# （tests/test_auth_guard.py 会检查每个没列在这里的路由，匿名访问都得是 401）。
PUBLIC_ENDPOINTS = frozenset({
    'static',
    # 页面：浏览器地址栏直接打开，带不上 Bearer 头；页面脚本会自己校验登录，没登录就跳 /login
    'auth.index', 'auth.login_page',
    'speaking.speaking_page', 'speaking_playlist.combined_page',
    'reading.reading_page',
    'intensive_reading.intensive_page', 'intensive_reading.intensive_new_page',
    'intensive_reading.vocab_summary',
    'community.message_board_page', 'vocabulary.vocabulary_page',
    'study_tips.study_techniques_page', 'asr.audio_transcription_page',
    'writing.writing_practice_page',
    'listening_review.listening_review_page', 'listening_review.listening_notes_page',
    # 登录流程本身
    'auth.user_login', 'auth.verify_token',
    # 只读的媒体文件：<audio>/<img>/下载链接/新窗口打开都发不了 Authorization 头。
    # 这些接口只读已有文件，不会触发 TTS/LLM；要把它们也保护起来，得改成 cookie 登录。
    'speaking.serve_audio', 'speaking_playlist.serve_combined_audio',
    'community.serve_message_image',
    'intensive_reading.serve_intensive_image', 'intensive_reading.get_vocab_audio',
    'intensive_reading.get_article_audio',
    'vocabulary.serve_vocabulary_audio', 'writing.small_serve_image',
    'reading.serve_reading_file', 'reading.reading_view',
})

# 这两个音频接口本来就允许把 token 放在 ?token= 里（<audio src> 只能这样带），规则照旧
QUERY_TOKEN_ENDPOINTS = frozenset({
    'listening_review.serve_audio',
    'asr.serve_transcription_audio',
})


def _too_large_response():
    limit_mb = MAX_REQUEST_BYTES // (1024 * 1024)
    return jsonify({'success': False, 'error': f'上传内容太大，单次不能超过 {limit_mb}MB'}), 413


@app.errorhandler(RequestEntityTooLarge)
def _handle_request_too_large(_error):
    return _too_large_response()


@app.before_request
def _guard_request():
    # 先挡超大的请求体。很多接口外面包着 except Exception，会把 413 吞成 500，
    # 所以进视图之前先按 Content-Length 判一次；不带 Content-Length 的分块上传，
    # 由 MAX_CONTENT_LENGTH 在读取时兜底。
    if request.content_length is not None and request.content_length > MAX_REQUEST_BYTES:
        return _too_large_response()

    endpoint = request.endpoint
    # 路由不存在（404/405）交给 Flask 自己处理；OPTIONS 预检不会执行视图函数
    if endpoint is None or request.method == 'OPTIONS' or endpoint in PUBLIC_ENDPOINTS:
        return None

    token = get_bearer_token()
    if not token and endpoint in QUERY_TOKEN_ENDPOINTS:
        token = request.args.get('token', '')
    try:
        username = resolve_token_user(token)
    except AuthStoreError:
        # 读不出 tokens.json / users.json 时说不清 token 是否有效：回 503，
        # 不回 401 —— 前端只在服务器明确说无效时才清掉登录状态
        logging.exception('登录状态校验失败：tokens.json / users.json 读不出来')
        return jsonify({'error': '身份校验暂时不可用，请稍后重试'}), 503
    if not username:
        return jsonify({'error': '未登录或登录已失效，请重新登录'}), 401
    return None

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
