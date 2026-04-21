"""Shared constants and definitions for Pearl's File Tools."""

# File extension categories
IMAGE_EXTENSIONS = {
    '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.tiff', '.tif',
    '.svg', '.ico', '.heic', '.heif'
}
IMAGE_EXTENSIONS |= {
    '.exr', '.dpx', '.tga', '.hdr',
    '.raw', '.cr2', '.nef', '.arw', '.dng'
}

DOCUMENT_EXTENSIONS = {
    '.pdf', '.doc', '.docx', '.txt', '.rtf', '.odt',
    '.xls', '.xlsx', '.ppt', '.pptx', '.csv', '.md'
}

VIDEO_EXTENSIONS = {
    '.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv',
    '.webm', '.m4v', '.mpeg', '.mpg', '.3gp'
}
VIDEO_EXTENSIONS |= {
    '.mxf', '.r3d', '.braw', '.prores',
    '.mts', '.m2ts', '.dng', '.cine', '.ari'
}

AUDIO_EXTENSIONS = {
    '.mp3', '.wav', '.flac', '.aac', '.ogg', '.wma',
    '.m4a', '.opus', '.ape', '.alac'
}
AUDIO_EXTENSIONS |= {'.aiff', '.aif', '.bwf', '.rf64'}

ARCHIVE_EXTENSIONS = {
    '.zip', '.rar', '.7z', '.tar', '.gz', '.bz2', '.xz',
    '.tar.gz', '.tar.bz2', '.tar.xz', '.tgz', '.tbz2', '.txz'
}

# All extension categories combined
ALL_EXTENSION_CATEGORIES = {
    'images': IMAGE_EXTENSIONS,
    'documents': DOCUMENT_EXTENSIONS,
    'videos': VIDEO_EXTENSIONS,
    'audio': AUDIO_EXTENSIONS,
    'archives': ARCHIVE_EXTENSIONS
}

# Keywords for photo/image archive detection
PHOTO_KEYWORDS = ["photo", "photos", "image", "images", "picture", "pictures", "pic", "pics"]

# Application file names
CONFIG_FILE_NAME = 'pearls_file_tools_config.json'
CACHE_FILE_NAME = '.pearls_file_tools_cache.json'
BACKUP_DIR_NAME = '.pearls_file_tools_backups'

# UI constants
DEFAULT_WINDOW_WIDTH = 1200
DEFAULT_WINDOW_HEIGHT = 800
DEFAULT_THUMBNAIL_SIZE = 200
DEFAULT_GRID_COLUMNS = 5

# Operation types (for undo/history)
OP_TYPE_RENAME = 'rename'
OP_TYPE_ORGANIZE = 'organize'
OP_TYPE_EXTRACT = 'extract'

# Case transform types
CASE_NONE = 'none'
CASE_UPPER = 'upper'
CASE_LOWER = 'lower'
CASE_TITLE = 'title'

# Conflict resolution strategies
CONFLICT_COUNTER = 'counter'
CONFLICT_TIMESTAMP = 'timestamp'
CONFLICT_SKIP = 'skip'

# Caption / subtitle formats
CAPTION_EXTENSIONS = {'.srt', '.vtt', '.ttml', '.sbv', '.ass', '.ssa'}

# Sidecar / metadata companion formats
SIDECAR_EXTENSIONS = {'.xmp', '.thm', '.lrv', '.json', '.srt', '.vtt', '.ttml'}

# Theme names
THEME_DARK = 'dark'
THEME_LIGHT = 'light'
