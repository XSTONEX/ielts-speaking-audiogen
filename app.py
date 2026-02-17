from flask import Flask
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

# 启动词汇音频后台任务处理器
from routers.vocabulary import start_audio_task_processor
start_audio_task_processor()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001)
