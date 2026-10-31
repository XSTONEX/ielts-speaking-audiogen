"""首页数据：每个模块一行实打实的数字，外加「继续上次」和「待复习」。

只读汇总，不写任何文件。口径：
- 「本周」从本周一 0 点算起（服务器本地时间，和各模块写入的时间戳同一个时区）。
- 口语音频、文章精读、单词本、学习技巧、交流区是全站共用的；写作、听力、挑战错词按当前用户。
"""
import os
from datetime import datetime, timedelta
from urllib.parse import quote

from flask import Blueprint, jsonify, request

import core
from core import require_auth
from routers.learning import (
    CATEGORIES,
    _all_vocab_words,
    _listening_review_items,
    _load_listening_projects,
    _load_writing_records,
    _score_value,
    _vocabulary_review_items,
    _writing_review_items,
)
from utils.json_store import load_json


home_bp = Blueprint("home", __name__)

REVIEW_PREVIEW = 6
TIP_TYPES = ("synonyms", "hypernyms", "techniques")

# 精读文章一篇几十 KB，首页每次打开都全读一遍不划算：按文件修改时间缓存标题和最近动静
_article_cache = {}


def _parse_time(value):
    try:
        moment = datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    if moment.tzinfo is not None:
        moment = moment.astimezone().replace(tzinfo=None)
    return moment


def _since(value, start):
    moment = _parse_time(value)
    return moment is not None and moment >= start


def _week_start(now):
    monday = now - timedelta(days=now.weekday())
    return monday.replace(hour=0, minute=0, second=0, microsecond=0)


def _int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _speaking_stats():
    topics = audios = 0
    seconds = 0.0
    try:
        folders = os.listdir(core.MOTHER_DIR)
    except OSError:
        folders = []
    for folder in folders:
        path = os.path.join(core.MOTHER_DIR, folder)
        if folder.startswith(".") or not os.path.isdir(path):
            continue
        files = [name for name in os.listdir(path) if name.endswith(".mp3")]
        if not files:
            continue
        topics += 1
        audios += len(files)
        seconds += sum(core.get_audio_duration(folder, name) for name in files)
    core.flush_duration_cache()
    return {"topics": topics, "audios": audios, "seconds": round(seconds)}


def _article_brief(path):
    """(标题, 最近一次动静的时间)：新建或最后一次高亮，取晚的那个。"""
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return None
    cached = _article_cache.get(path)
    if cached and cached[0] == mtime:
        return cached[1]
    data = load_json(path, None)
    if not isinstance(data, dict):
        return None
    stamps = [str(data.get("created_at") or "")]
    stamps += [str(h.get("created_at") or "") for h in data.get("highlights") or [] if isinstance(h, dict)]
    brief = (data.get("title") or "未命名文章", max(stamps))
    _article_cache[path] = (mtime, brief)
    return brief


def _intensive_stats():
    count = 0
    latest = None
    try:
        names = os.listdir(core.INTENSIVE_DIR)
    except OSError:
        names = []
    for name in names:
        if not name.endswith(".json"):
            continue
        brief = _article_brief(os.path.join(core.INTENSIVE_DIR, name))
        if brief is None:
            continue
        count += 1
        if latest is None or brief[1] > latest[1]:
            latest = brief
    return {"articles": count, "latest_title": latest[0] if latest else ""}


def _writing_stats(records, week_start):
    scores = [s for s in (_score_value(r.get("score")) for r in records) if s is not None]
    return {
        "total": len(records),
        "week": sum(1 for r in records if _since(r.get("timestamp"), week_start)),
        "avg_score": round(sum(scores) / len(scores), 1) if scores else None,
    }


def _listening_stats(projects, week_start):
    return {
        "projects": len(projects),
        "unmastered": sum(1 for p in projects if p.get("status") == "completed" and not p.get("mastered")),
        "checkins": sum(_int(p.get("checkin_count")) for p in projects),
        # 打卡时间是后来才开始记的（checkins），以前的打卡只有总数，算不进本周
        "week_checkins": sum(
            1 for p in projects for stamp in p.get("checkins") or [] if _since(stamp, week_start)
        ),
    }


def _vocabulary_stats(words, week_start):
    return {
        "words": len(words),
        "favorites": sum(1 for w in words if w.get("is_favorited")),
        "week": sum(1 for w in words if _since(w.get("created_at"), week_start)),
    }


def _tips_stats():
    counts = {kind: 0 for kind in TIP_TYPES}
    for category in CATEGORIES:
        for kind in TIP_TYPES:
            data = load_json(os.path.join(core.STUDY_TECHNIQUES_DATA_DIR, f"{category}_{kind}.json"), [])
            if isinstance(data, list):
                counts[kind] += len(data)
    return counts


def _pending_challenges(username):
    """还没交卷的挑战：没结束、自己没参加，而且是自己发的、@了自己或谁都没 @。"""
    count = 0
    try:
        names = os.listdir(core.CHALLENGES_DIR)
    except OSError:
        names = []
    for name in names:
        # 同目录下的挑战记录和错词本不是挑战文件
        if not name.endswith(".json") or name.startswith(("vocab_summary_", "wrong_words_")):
            continue
        data = load_json(os.path.join(core.CHALLENGES_DIR, name), None)
        if not isinstance(data, dict) or "vocabulary" not in data or data.get("status") == "completed":
            continue
        if username in (data.get("participants") or {}):
            continue
        mentioned = data.get("mentioned_users") or []
        if username == data.get("creator") or username in mentioned or not mentioned:
            count += 1
    return count


def _post_brief(post):
    user = post.get("user")
    if isinstance(user, dict):
        who = user.get("display_name") or user.get("username") or ""
    else:
        who = str(user or "")
    content = post.get("content")
    if not isinstance(content, dict):
        content = {"text": content}
    challenge = content.get("challenge")
    articles = [a for a in content.get("articles") or [] if isinstance(a, dict)]
    text = " ".join(str(content.get("text") or "").split())
    # kind=text 时 text 是帖子原文，其余是「发起了…」「分享了…」这样的动作描述
    if isinstance(challenge, dict):
        title = challenge.get("title")
        kind, summary = "challenge", f"发起了词汇挑战：{title}" if title else "发起了词汇挑战"
    elif text:
        kind, summary = "text", text[:60]
    elif articles:
        kind, summary = "article", f"分享了精读文章 {articles[0].get('title') or ''}".strip()
    elif content.get("audios"):
        kind, summary = "audio", "分享了口语音频"
    elif content.get("images"):
        kind, summary = "image", "分享了图片"
    else:
        kind, summary = "other", "发了一条帖子"
    return {"who": who, "kind": kind, "text": summary, "at": post.get("timestamp", "")}


def _board_stats(username):
    posts = load_json(os.path.join(core.MESSAGE_BOARD_DIR, "messages.json"), [])
    posts = [p for p in posts if isinstance(p, dict)] if isinstance(posts, list) else []
    latest = max(posts, key=lambda p: str(p.get("timestamp") or ""), default=None)
    return {
        "posts": len(posts),
        "pending_challenges": _pending_challenges(username),
        "latest": _post_brief(latest) if latest else None,
    }


def _review(username, words, writing_records, projects):
    """各来源先按轻重排好，再轮流各取一条，列表里三种都看得到，不会被 70 个错词刷屏。"""
    vocabulary = sorted(
        _vocabulary_review_items(username, words),
        key=lambda item: (_int(item.get("wrong_count")), str(item.get("created_at") or "")),
        reverse=True,
    )
    writing = sorted(_writing_review_items(writing_records),
                     key=lambda item: str(item.get("created_at") or ""), reverse=True)
    writing.sort(key=lambda item: item["score"])
    listening = sorted(_listening_review_items(projects),
                       key=lambda item: str(item.get("created_at") or ""), reverse=True)
    groups = [vocabulary, writing, listening]
    counts = {"vocabulary": len(vocabulary), "writing": len(writing), "listening": len(listening)}

    items = []
    while len(items) < REVIEW_PREVIEW and any(groups):
        for group in groups:
            if group and len(items) < REVIEW_PREVIEW:
                item = group.pop(0)
                items.append({
                    "source": item["source"],
                    "title": item.get("title") or "",
                    "wrong_count": item.get("wrong_count"),
                    "score": item.get("score"),
                    "url": item.get("url", "/"),
                })
    return {"total": sum(counts.values()), "counts": counts, "items": items}


def _writing_resume_title(record):
    kind = record.get("writing_type")
    if kind == "template":
        parts = ["模板写作", record.get("type_name"), record.get("section_name")]
    elif kind == "task1":
        parts = ["小作文", record.get("example_name"), record.get("section_name")]
    else:
        parts = ["大作文", record.get("category"), record.get("subcategory")]
    return " · ".join(str(p) for p in parts if p)


def _resume(writing_records, projects):
    """最近一次练的东西：写作最后一句，或最后动过的听力（打卡、标熟、转录完成）。"""
    candidates = []
    last_writing = max(writing_records, key=lambda r: str(r.get("timestamp") or ""), default=None)
    if last_writing and last_writing.get("timestamp"):
        candidates.append({
            "module": "writing",
            "module_name": "写作逻辑训练",
            "title": _writing_resume_title(last_writing),
            "sentence": last_writing.get("target_chinese") or "",
            "score": _score_value(last_writing.get("score")),
            "at": last_writing["timestamp"],
            "url": "/writing_practice",
        })
    done = [p for p in projects if p.get("status") == "completed" and p.get("id")]
    last_listening = max(done, key=lambda p: str(p.get("updated_at") or p.get("created_at") or ""), default=None)
    if last_listening:
        candidates.append({
            "module": "listening",
            "module_name": "听力精听复习",
            "title": last_listening.get("title") or "听力精听",
            "checkins": _int(last_listening.get("checkin_count")),
            "mastered": bool(last_listening.get("mastered")),
            "at": last_listening.get("updated_at") or last_listening.get("created_at") or "",
            "url": "/listening_review?project=" + quote(str(last_listening["id"]), safe=""),
        })
    return max(candidates, key=lambda c: str(c["at"]), default=None)


@home_bp.route("/api/home", methods=["GET"])
@require_auth
def home_summary():
    username = request.username
    week_start = _week_start(datetime.now())
    words = _all_vocab_words()
    writing_records = _load_writing_records(username)
    projects = _load_listening_projects(username)

    writing = _writing_stats(writing_records, week_start)
    listening = _listening_stats(projects, week_start)
    vocabulary = _vocabulary_stats(words, week_start)
    return jsonify({
        "success": True,
        "week": {
            "writing": writing["week"],
            "vocabulary": vocabulary["week"],
            "listening_checkins": listening["week_checkins"],
        },
        "resume": _resume(writing_records, projects),
        "speaking": _speaking_stats(),
        "intensive": _intensive_stats(),
        "writing": writing,
        "listening": listening,
        "vocabulary": vocabulary,
        "tips": _tips_stats(),
        "board": _board_stats(username),
        "review": _review(username, words, writing_records, projects),
    })
