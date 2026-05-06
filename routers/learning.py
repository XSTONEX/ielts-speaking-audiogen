import csv
import io
import os
import uuid
from datetime import datetime

from flask import Blueprint, Response, jsonify, request

import core
from core import require_auth
from utils.json_store import load_json, save_json_atomic


learning_bp = Blueprint("learning", __name__)

CATEGORIES = ("listening", "speaking", "reading", "writing")
LOW_SCORE_THRESHOLD = 6.0


def _category_path(category):
    return os.path.join(core.VOCABULARY_CATEGORIES_DIR, f"{category}.json")


def _writing_path(username, suffix):
    return os.path.join(core.WRITING_DATA_DIR, f"{username}_{suffix}.json")


def _listening_projects_path(username):
    return os.path.join(core.LISTENING_REVIEW_DIR, f"{username}_projects.json")


def _listening_data_path(project_id):
    return os.path.join(core.LISTENING_REVIEW_DIR, project_id, "data.json")


def _challenge_wrong_words_path(username):
    return os.path.join(core.CHALLENGES_DIR, f"wrong_words_{username}.json")


def _challenge_records_path(username):
    return os.path.join(core.CHALLENGES_DIR, f"vocab_summary_{username}.json")


def _now():
    return datetime.now().isoformat()


def _score_value(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _all_vocab_words():
    words = []
    for category in CATEGORIES:
        data = load_json(_category_path(category), None)
        if not isinstance(data, dict):
            continue
        for subcategory_id, subcategory in data.get("subcategories", {}).items():
            for word in subcategory.get("words", []):
                words.append(
                    {
                        **word,
                        "category": category,
                        "subcategory_id": subcategory_id,
                        "subcategory_name": subcategory.get("name", "默认分类"),
                    }
                )
    return words


def _load_writing_records(username):
    records = []
    for suffix, label in (("practice", "task2"), ("small_practice", "task1")):
        for record in load_json(_writing_path(username, suffix), []):
            if isinstance(record, dict):
                records.append({**record, "writing_type": label})
    return records


def _load_listening_projects(username):
    projects = load_json(_listening_projects_path(username), [])
    return [p for p in projects if isinstance(p, dict)]


def _recent_activity(vocab_words, writing_records, listening_projects):
    activities = []
    for word in vocab_words:
        activities.append(
            {
                "type": "vocabulary",
                "title": word.get("word", ""),
                "description": word.get("meaning", ""),
                "timestamp": word.get("created_at", ""),
                "url": "/vocabulary",
            }
        )
    for record in writing_records:
        activities.append(
            {
                "type": "writing",
                "title": record.get("subcategory") or record.get("example_name") or "写作练习",
                "description": record.get("target_chinese", ""),
                "timestamp": record.get("timestamp", ""),
                "url": "/writing_practice",
            }
        )
    for project in listening_projects:
        activities.append(
            {
                "type": "listening",
                "title": project.get("title", "听力精听"),
                "description": project.get("status", ""),
                "timestamp": project.get("updated_at") or project.get("created_at", ""),
                "url": "/listening_review",
            }
        )
    activities.sort(key=lambda item: item.get("timestamp") or "", reverse=True)
    return activities[:8]


def _writing_review_items(records):
    items = []
    for record in records:
        if not record.get("in_review", True):
            continue
        score = _score_value(record.get("score"))
        if score is None or score >= LOW_SCORE_THRESHOLD:
            continue
        items.append(
            {
                "id": record.get("id"),
                "source": "writing",
                "priority": "high" if score < 5.5 else "medium",
                "title": record.get("target_chinese", "写作句子复习"),
                "description": record.get("feedback", {}).get("feedback_summary", ""),
                "score": score,
                "url": "/writing_practice",
                "created_at": record.get("timestamp", ""),
            }
        )
    return items


def _vocabulary_review_items(username, vocab_words):
    items = []
    by_id = {word.get("id"): word for word in vocab_words}
    by_text = {str(word.get("word", "")).lower(): word for word in vocab_words}

    for word in vocab_words:
        if word.get("is_favorited"):
            items.append(
                {
                    "id": word.get("id"),
                    "source": "vocabulary",
                    "priority": "medium",
                    "title": word.get("word", ""),
                    "description": word.get("meaning", ""),
                    "url": "/vocabulary",
                    "created_at": word.get("created_at", ""),
                }
            )

    wrong_words = load_json(_challenge_wrong_words_path(username), {})
    if isinstance(wrong_words, dict):
        for key, wrong in wrong_words.items():
            if not isinstance(wrong, dict):
                continue
            word = by_id.get(wrong.get("id")) or by_text.get(str(wrong.get("word", key)).lower())
            title = wrong.get("word") or (word or {}).get("word") or key
            items.append(
                {
                    "id": wrong.get("id") or key,
                    "source": "vocabulary",
                    "priority": "high",
                    "title": title,
                    "description": wrong.get("meaning") or (word or {}).get("meaning", ""),
                    "wrong_count": wrong.get("wrong_count", 1),
                    "url": "/vocab_summary",
                    "created_at": wrong.get("last_wrong_at", ""),
                }
            )
    return items


def _listening_review_items(projects):
    items = []
    for project in projects:
        data = load_json(_listening_data_path(project.get("id", "")), {})
        starred = data.get("starred_segments") if isinstance(data, dict) else []
        if project.get("status") == "completed" and not project.get("mastered", False):
            items.append(
                {
                    "id": project.get("id"),
                    "source": "listening",
                    "priority": "medium",
                    "title": project.get("title", "听力精听"),
                    "description": f"{len(starred or [])} 个收藏片段待复习",
                    "url": "/listening_review",
                    "created_at": project.get("updated_at") or project.get("created_at", ""),
                }
            )
    return items


def _review_queue(username):
    vocab_words = _all_vocab_words()
    writing_records = _load_writing_records(username)
    listening_projects = _load_listening_projects(username)
    items = []
    items.extend(_vocabulary_review_items(username, vocab_words))
    items.extend(_writing_review_items(writing_records))
    items.extend(_listening_review_items(listening_projects))
    priority_rank = {"high": 0, "medium": 1, "low": 2}
    items.sort(key=lambda item: (priority_rank.get(item.get("priority"), 9), item.get("created_at") or ""), reverse=False)
    return items[:20]


def _learning_tasks(username):
    tasks = []
    if os.path.isdir(core.VOCABULARY_TASKS_DIR):
        for filename in os.listdir(core.VOCABULARY_TASKS_DIR):
            if not filename.endswith(".json"):
                continue
            task = load_json(os.path.join(core.VOCABULARY_TASKS_DIR, filename), {})
            if not isinstance(task, dict):
                continue
            status = task.get("status", "")
            if status in {"pending", "processing", "failed", "max_attempts_reached"}:
                tasks.append(
                    {
                        "id": task.get("id") or filename[:-5],
                        "source": "vocabulary_audio",
                        "title": task.get("word", "词汇音频"),
                        "status": status,
                        "error": task.get("error", ""),
                        "created_at": task.get("created_at", ""),
                        "updated_at": task.get("last_updated", ""),
                    }
                )

    for project in _load_listening_projects(username):
        status = project.get("status", "")
        if status in {"processing", "translating", "error"}:
            tasks.append(
                {
                    "id": project.get("id"),
                    "source": "listening_review",
                    "title": project.get("title", "听力精听"),
                    "status": status,
                    "error": project.get("error", ""),
                    "created_at": project.get("created_at", ""),
                    "updated_at": project.get("updated_at", ""),
                }
            )
    tasks.sort(key=lambda item: item.get("updated_at") or item.get("created_at") or "", reverse=True)
    return tasks


@learning_bp.route("/api/learning/dashboard", methods=["GET"])
@require_auth
def learning_dashboard():
    username = request.username
    vocab_words = _all_vocab_words()
    writing_records = _load_writing_records(username)
    listening_projects = _load_listening_projects(username)
    challenge_records = load_json(_challenge_records_path(username), [])
    review_items = _review_queue(username)
    active_tasks = len(_learning_tasks(username))

    summary = {
        "vocabulary_words": len(vocab_words),
        "favorite_words": sum(1 for word in vocab_words if word.get("is_favorited")),
        "writing_practices": len(writing_records),
        "writing_review_items": len(_writing_review_items(writing_records)),
        "listening_projects": len(listening_projects),
        "listening_unmastered": sum(1 for p in listening_projects if p.get("status") == "completed" and not p.get("mastered", False)),
        "challenge_records": len(challenge_records) if isinstance(challenge_records, list) else 0,
        "active_tasks": active_tasks,
        "review_items": len(review_items),
    }

    quick_links = [
        {"label": "继续写作训练", "url": "/writing_practice"},
        {"label": "复习词汇", "url": "/vocabulary"},
        {"label": "听力精听", "url": "/listening_review"},
        {"label": "文章精读", "url": "/intensive"},
    ]
    return jsonify(
        {
            "success": True,
            "summary": summary,
            "review_queue": review_items[:6],
            "recent_activity": _recent_activity(vocab_words, writing_records, listening_projects),
            "quick_links": quick_links,
        }
    )


@learning_bp.route("/api/learning/review_queue", methods=["GET"])
@require_auth
def learning_review_queue():
    return jsonify({"success": True, "items": _review_queue(request.username)})


@learning_bp.route("/api/learning/tasks", methods=["GET"])
@require_auth
def learning_tasks():
    return jsonify({"success": True, "tasks": _learning_tasks(request.username)})


@learning_bp.route("/api/learning/vocabulary", methods=["POST"])
@require_auth
def learning_add_vocabulary():
    data = request.get_json(silent=True) or {}
    word = str(data.get("word", "")).strip()
    meaning = str(data.get("meaning", "")).strip()
    category = str(data.get("category", "reading")).strip().lower()
    subcategory_name = str(data.get("subcategory_name", "跨模块收集")).strip() or "跨模块收集"
    source = str(data.get("source", "learning")).strip() or "learning"

    if category not in CATEGORIES:
        return jsonify({"success": False, "error": "无效的分类"}), 400
    if not word:
        return jsonify({"success": False, "error": "单词不能为空"}), 400

    path = _category_path(category)
    data_obj = load_json(path, None)
    now = _now()
    if not isinstance(data_obj, dict):
        data_obj = {
            "name": category.capitalize(),
            "icon": {"listening": "🎧", "speaking": "🗣️", "reading": "📖", "writing": "✍️"}[category],
            "subcategories": {},
            "metadata": {"created_at": now, "last_updated": now},
        }

    target_id = None
    for sub_id, subcategory in data_obj.setdefault("subcategories", {}).items():
        if subcategory.get("name") == subcategory_name:
            target_id = sub_id
            break
    if target_id is None:
        target_id = str(uuid.uuid4())
        data_obj["subcategories"][target_id] = {"name": subcategory_name, "created_at": now, "words": []}

    words = data_obj["subcategories"][target_id].setdefault("words", [])
    if any(str(existing.get("word", "")).lower() == word.lower() for existing in words):
        return jsonify({"success": False, "error": "单词已存在"}), 409

    word_obj = {
        "id": str(uuid.uuid4()),
        "word": word,
        "meaning": meaning,
        "created_at": now,
        "audio_generated": False,
        "is_favorited": False,
        "source": source,
        "source_detail": data.get("source_detail", ""),
    }
    words.append(word_obj)
    data_obj.setdefault("metadata", {})["last_updated"] = now
    save_json_atomic(path, data_obj)
    return jsonify({"success": True, "data": word_obj})


@learning_bp.route("/api/learning/export/vocabulary", methods=["GET"])
@require_auth
def export_vocabulary():
    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=["category", "subcategory", "word", "meaning", "is_favorited", "created_at", "source"],
    )
    writer.writeheader()
    for word in _all_vocab_words():
        writer.writerow(
            {
                "category": word.get("category", ""),
                "subcategory": word.get("subcategory_name", ""),
                "word": word.get("word", ""),
                "meaning": word.get("meaning", ""),
                "is_favorited": bool(word.get("is_favorited")),
                "created_at": word.get("created_at", ""),
                "source": word.get("source", ""),
            }
        )
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=vocabulary-export.csv"},
    )


@learning_bp.route("/api/learning/export/writing", methods=["GET"])
@require_auth
def export_writing():
    records = _load_writing_records(request.username)
    lines = ["# Writing Practice Export", ""]
    for record in sorted(records, key=lambda item: item.get("timestamp", ""), reverse=True):
        title = record.get("subcategory") or record.get("example_name") or record.get("category") or "Practice"
        lines.extend(
            [
                f"## {title}",
                "",
                f"- Time: {record.get('timestamp', '')}",
                f"- Score: {record.get('score', '')}",
                f"- Target: {record.get('target_chinese', '')}",
                f"- User: {record.get('user_translation', '')}",
                f"- Native: {record.get('native_version', '')}",
                "",
            ]
        )
        summary = record.get("feedback", {}).get("feedback_summary")
        if summary:
            lines.extend([f"Feedback: {summary}", ""])
    return Response(
        "\n".join(lines),
        mimetype="text/markdown",
        headers={"Content-Disposition": "attachment; filename=writing-export.md"},
    )


@learning_bp.route("/api/learning/export/listening", methods=["GET"])
@require_auth
def export_listening():
    lines = ["# Listening Review Export", ""]
    for project in _load_listening_projects(request.username):
        lines.extend([f"## {project.get('title', 'Listening Review')}", "", f"- Status: {project.get('status', '')}", ""])
        data = load_json(_listening_data_path(project.get("id", "")), {})
        for segment in data.get("segments", []) if isinstance(data, dict) else []:
            lines.append(f"- {segment.get('text', '')}")
            if segment.get("translation"):
                lines.append(f"  {segment.get('translation')}")
        lines.append("")
    return Response(
        "\n".join(lines),
        mimetype="text/markdown",
        headers={"Content-Disposition": "attachment; filename=listening-export.md"},
    )
