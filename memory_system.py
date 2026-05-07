"""
memory_system.py - Persistent Memory System using HuggingFace
Makes AI smarter over time by learning from every conversation
"""

import json
import os
from datetime import datetime, timezone
from typing import Optional

def get_memory_repo_id() -> str:
    """Get the HuggingFace repo ID from secrets or environment."""
    return os.environ.get("HF_REPO_ID", "")

def get_hf_token() -> str:
    """Get the HuggingFace token from secrets or environment."""
    return os.environ.get("HuggingFace_API_KEY", "")

def get_memory_path(filename: str) -> str:
    """Get the path for memory files in the repo."""
    return f"memory/{filename}"

def load_memory_from_hf(repo_id: str, hf_token: str, filename: str) -> dict:
    """Load a memory file from HuggingFace Hub."""
    from huggingface_hub import hf_hub_download
    
    if not repo_id or not hf_token:
        return {}
    
    try:
        local_path = hf_hub_download(
            repo_id=repo_id,
            filename=f"memory/{filename}",
            repo_type="dataset",
            token=hf_token,
            force_download=True
        )
        with open(local_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"[Memory] Could not load {filename}: {e}")
        return {}

def save_memory_to_hf(repo_id: str, hf_token: str, filename: str, data: dict, commit_message: str = ""):
    """Save a memory file to HuggingFace Hub."""
    from huggingface_hub import upload_file
    import tempfile
    
    if not repo_id or not hf_token:
        return
    
    try:
        tmp_fd, tmp_path = tempfile.mkstemp(suffix=".json")
        os.close(tmp_fd)
        
        with open(tmp_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        upload_file(
            path_or_fileobj=tmp_path,
            path_in_repo=f"memory/{filename}",
            repo_id=repo_id,
            repo_type="dataset",
            token=hf_token,
            commit_message=commit_message or f"Memory update: {filename}"
        )
        
        os.unlink(tmp_path)
    except Exception as e:
        print(f"[Memory] Could not save {filename}: {e}")

def load_all_memory() -> dict:
    """Load all memory files from HuggingFace."""
    repo_id = get_memory_repo_id()
    hf_token = get_hf_token()
    
    if not repo_id or not hf_token:
        print("[Memory] No HF credentials - using empty memory")
        return get_empty_memory_structure()
    
    memory = {
        "conversations": load_memory_from_hf(repo_id, hf_token, "conversations.json"),
        "insights": load_memory_from_hf(repo_id, hf_token, "insights.json"),
        "preferences": load_memory_from_hf(repo_id, hf_token, "preferences.json"),
        "stats": load_memory_from_hf(repo_id, hf_token, "stats.json"),
        "last_updated": datetime.now(timezone.utc).isoformat()
    }
    
    return memory

def get_empty_memory_structure() -> dict:
    """Return empty memory structure."""
    return {
        "conversations": [],
        "insights": [],
        "preferences": {},
        "stats": {
            "total_conversations": 0,
            "total_trades_suggested": 0,
            "successful_trades": 0,
            "failed_trades": 0,
            "win_rate": 0.0
        },
        "last_updated": datetime.now(timezone.utc).isoformat()
    }

def save_conversation_summary(conversation_id: str, user_prompt: str, ai_response: str, 
                              detected_setup: Optional[dict] = None, detected_action: Optional[dict] = None):
    """Save a conversation summary to memory."""
    repo_id = get_memory_repo_id()
    hf_token = get_hf_token()
    
    if not repo_id or not hf_token:
        return
    
    conversations = load_memory_from_hf(repo_id, hf_token, "conversations.json")
    if not isinstance(conversations, list):
        conversations = []
    
    summary = {
        "id": conversation_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "user_prompt": user_prompt[:500],
        "ai_summary": ai_response[:500] if ai_response else "",
        "trade_setup": detected_setup,
        "trade_action": detected_action,
        "symbol": detected_setup.get("symbol") if detected_setup else None
    }
    
    conversations.append(summary)
    if len(conversations) > 100:
        conversations = conversations[-100:]
    
    save_memory_to_hf(repo_id, hf_token, "conversations.json", conversations, 
                     f"New conversation: {conversation_id}")

def save_insight(insight: str, category: str = "general", confidence: float = 0.5):
    """Save a learned insight to memory."""
    repo_id = get_memory_repo_id()
    hf_token = get_hf_token()
    
    if not repo_id or not hf_token:
        return
    
    insights = load_memory_from_hf(repo_id, hf_token, "insights.json")
    if not isinstance(insights, list):
        insights = []
    
    existing = next((i for i in insights if insight in i.get("insight", "")), None)
    if existing:
        existing["occurrences"] = existing.get("occurrences", 1) + 1
        existing["last_seen"] = datetime.now(timezone.utc).isoformat()
    else:
        insights.append({
            "insight": insight,
            "category": category,
            "confidence": confidence,
            "occurrences": 1,
            "first_seen": datetime.now(timezone.utc).isoformat(),
            "last_seen": datetime.now(timezone.utc).isoformat()
        })
    
    if len(insights) > 50:
        insights = insights[-50:]
    
    save_memory_to_hf(repo_id, hf_token, "insights.json", insights, f"New insight: {category}")

def save_preference(key: str, value):
    """Save a user preference."""
    repo_id = get_memory_repo_id()
    hf_token = get_hf_token()
    
    if not repo_id or not hf_token:
        return
    
    preferences = load_memory_from_hf(repo_id, hf_token, "preferences.json")
    if not isinstance(preferences, dict):
        preferences = {}
    
    preferences[key] = value
    preferences["last_updated"] = datetime.now(timezone.utc).isoformat()
    
    save_memory_to_hf(repo_id, hf_token, "preferences.json", preferences, f"Preference updated: {key}")

def update_stats(trade_outcome: str):
    """Update trading statistics."""
    repo_id = get_memory_repo_id()
    hf_token = get_hf_token()
    
    if not repo_id or not hf_token:
        return
    
    stats = load_memory_from_hf(repo_id, hf_token, "stats.json")
    if not isinstance(stats, dict):
        stats = {"total_conversations": 0, "total_trades_suggested": 0, "successful_trades": 0, "failed_trades": 0, "win_rate": 0.0}
    
    stats["total_conversations"] = stats.get("total_conversations", 0) + 1
    
    if trade_outcome in ["success", "tp_hit", "profit"]:
        stats["successful_trades"] = stats.get("successful_trades", 0) + 1
    elif trade_outcome in ["failed", "sl_hit", "loss"]:
        stats["failed_trades"] = stats.get("failed_trades", 0) + 1
    
    total_trades = stats.get("successful_trades", 0) + stats.get("failed_trades", 0)
    if total_trades > 0:
        stats["win_rate"] = round((stats.get("successful_trades", 0) / total_trades) * 100, 2)
    
    stats["last_updated"] = datetime.now(timezone.utc).isoformat()
    
    save_memory_to_hf(repo_id, hf_token, "stats.json", stats, "Stats updated")

def build_memory_context(memory: dict) -> str:
    """Build memory context string for AI prompt."""
    context_parts = []
    
    context_parts.append("=" * 60)
    context_parts.append("🧠 PERSISTENT MEMORY CONTEXT")
    context_parts.append("=" * 60)
    
    stats = memory.get("stats", {})
    if stats.get("total_conversations", 0) > 0:
        context_parts.append(f"\n📊 YOUR HISTORY WITH THIS USER:")
        context_parts.append(f"   - Total conversations: {stats.get('total_conversations', 0)}")
        context_parts.append(f"   - Total trades suggested: {stats.get('total_trades_suggested', 0)}")
        context_parts.append(f"   - Win rate: {stats.get('win_rate', 0)}%")
    
    insights = memory.get("insights", [])
    if isinstance(insights, list) and len(insights) > 0:
        context_parts.append(f"\n💡 LEARNED INSIGHTS (from {len(insights)} observations):")
        for insight in insights[-5:]:
            occurrences = insight.get("occurrences", 1)
            context_parts.append(f"   • {insight.get('insight', '')} (seen {occurrences}x)")
    
    preferences = memory.get("preferences", {})
    if preferences and isinstance(preferences, dict):
        context_parts.append("\n👤 USER PREFERENCES:")
        for key, value in preferences.items():
            if key != "last_updated":
                context_parts.append(f"   • {key}: {value}")
    
    recent_convs = memory.get("conversations", [])
    if isinstance(recent_convs, list) and len(recent_convs) > 0:
        context_parts.append(f"\n📜 RECENT TOPICS DISCUSSED ({len(recent_convs)} conversations):")
        for conv in recent_convs[-3:]:
            ts = conv.get("timestamp", "")[:10]
            symbol = conv.get("symbol", "")
            topic = conv.get("user_prompt", "")[:80]
            context_parts.append(f"   [{ts}] {symbol or 'General'}: {topic}...")
    
    context_parts.append("\n" + "=" * 60)
    
    return "\n".join(context_parts)

def load_feedback() -> list:
    """Load all feedback from HuggingFace."""
    repo_id = get_memory_repo_id()
    hf_token = get_hf_token()
    
    if not repo_id or not hf_token:
        return []
    
    try:
        from huggingface_hub import hf_hub_download
        local_path = hf_hub_download(
            repo_id=repo_id,
            filename="memory/feedback.json",
            repo_type="dataset",
            token=hf_token,
            force_download=True
        )
        with open(local_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"[Feedback] Could not load feedback: {e}")
        return []

def save_feedback(rating: int, feedback_text: str = "", message: str = "", user: str = "user") -> bool:
    """Save user feedback to HuggingFace.
    
    Args:
        rating: 1-5 star rating (or thumbs up/down as 1/0)
        feedback_text: Optional text feedback
        message: The original AI message that was rated
        user: Username who gave feedback
    """
    repo_id = get_memory_repo_id()
    hf_token = get_hf_token()
    
    if not repo_id or not hf_token:
        print("[Feedback] No HF credentials - cannot save feedback")
        return False
    
    feedback_list = load_feedback()
    
    new_feedback = {
        "id": len(feedback_list) + 1,
        "rating": rating,
        "feedback_text": feedback_text,
        "message": message[:500] if message else "",
        "user": user,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    
    feedback_list.append(new_feedback)
    
    try:
        from huggingface_hub import upload_file
        import tempfile
        
        tmp_fd, tmp_path = tempfile.mkstemp(suffix=".json")
        os.close(tmp_fd)
        
        with open(tmp_path, 'w', encoding='utf-8') as f:
            json.dump(feedback_list, f, indent=2, ensure_ascii=False)
        
        upload_file(
            path_or_fileobj=tmp_path,
            path_in_repo="memory/feedback.json",
            repo_id=repo_id,
            repo_type="dataset",
            token=hf_token,
            commit_message=f"New feedback: {rating} stars"
        )
        
        os.unlink(tmp_path)
        print(f"[Feedback] Saved feedback to HF")
        return True
    except Exception as e:
        print(f"[Feedback] Could not save feedback: {e}")
        return False

def get_feedback_stats() -> dict:
    """Get feedback statistics."""
    feedback_list = load_feedback()
    
    if not feedback_list:
        return {"total": 0, "avg_rating": 0, "thumbs_up": 0, "thumbs_down": 0}
    
    total = len(feedback_list)
    ratings = [f["rating"] for f in feedback_list if isinstance(f["rating"], int)]
    avg_rating = sum(ratings) / len(ratings) if ratings else 0
    thumbs_up = sum(1 for f in feedback_list if f.get("rating") == 1)
    thumbs_down = sum(1 for f in feedback_list if f.get("rating") == 0)
    
    return {
        "total": total,
        "avg_rating": round(avg_rating, 2),
        "thumbs_up": thumbs_up,
        "thumbs_down": thumbs_down
    }