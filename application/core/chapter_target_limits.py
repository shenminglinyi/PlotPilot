"""每章目标字数：API、持久化、体量推导与全托管链路共用夹逼，避免各层上限不一致。"""

CHAPTER_TARGET_WORDS_MIN = 500
CHAPTER_TARGET_WORDS_MAX = 20_000


def clamp_chapter_target_words(w: int) -> int:
    return max(CHAPTER_TARGET_WORDS_MIN, min(CHAPTER_TARGET_WORDS_MAX, int(w)))
