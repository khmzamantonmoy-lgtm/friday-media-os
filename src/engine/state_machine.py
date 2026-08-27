from enum import Enum

class ContentState(Enum):
    NEW = "NEW"
    TOPIC_SELECTED = "TOPIC_SELECTED"
    SCRIPT_READY = "SCRIPT_READY"
    ASSETS_READY = "ASSETS_READY"
    RENDERING = "RENDERING"
    RENDERED = "RENDERED"
    UPLOADING = "UPLOADING"
    PUBLIC = "PUBLIC"
    CAPTIONS_VERIFIED = "CAPTIONS_VERIFIED"
    MEMORY_UPDATED = "MEMORY_UPDATED"
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"
    RETRY = "RETRY"

class StateMachine:
    _transitions = {
        ContentState.NEW: [ContentState.TOPIC_SELECTED, ContentState.FAILED, ContentState.RETRY],
        ContentState.TOPIC_SELECTED: [ContentState.SCRIPT_READY, ContentState.FAILED, ContentState.RETRY],
        ContentState.SCRIPT_READY: [ContentState.ASSETS_READY, ContentState.FAILED, ContentState.RETRY],
        ContentState.ASSETS_READY: [ContentState.RENDERING, ContentState.FAILED, ContentState.RETRY],
        ContentState.RENDERING: [ContentState.RENDERED, ContentState.ASSETS_READY, ContentState.FAILED, ContentState.RETRY],
        ContentState.RENDERED: [ContentState.UPLOADING, ContentState.FAILED, ContentState.RETRY],
        ContentState.UPLOADING: [ContentState.PUBLIC, ContentState.RENDERED, ContentState.FAILED, ContentState.RETRY],
        ContentState.PUBLIC: [ContentState.CAPTIONS_VERIFIED, ContentState.FAILED, ContentState.RETRY],
        ContentState.CAPTIONS_VERIFIED: [ContentState.MEMORY_UPDATED, ContentState.FAILED, ContentState.RETRY],
        ContentState.MEMORY_UPDATED: [ContentState.COMPLETE, ContentState.FAILED, ContentState.RETRY],
        ContentState.COMPLETE: [],
        ContentState.FAILED: [ContentState.RETRY, ContentState.NEW],
        ContentState.RETRY: [
            ContentState.NEW, ContentState.TOPIC_SELECTED, ContentState.SCRIPT_READY,
            ContentState.ASSETS_READY, ContentState.RENDERING, ContentState.RENDERED,
            ContentState.UPLOADING, ContentState.PUBLIC, ContentState.CAPTIONS_VERIFIED,
            ContentState.MEMORY_UPDATED
        ]
    }

    @classmethod
    def can_transition(cls, current: ContentState, target: ContentState) -> bool:
        if current not in cls._transitions:
            return False
        return target in cls._transitions[current]
