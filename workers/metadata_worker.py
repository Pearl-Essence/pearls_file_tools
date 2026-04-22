"""Background worker that loads media metadata for a list of files."""

from pathlib import Path
from typing import List

from PyQt5.QtCore import pyqtSignal

from workers.base_worker import BaseWorker


class MetadataWorker(BaseWorker):
    """Reads media metadata for each file and emits one signal per result.

    Signals
    -------
    metadata_ready(filepath_str, info_dict)
        Emitted for each file that has readable metadata.
        info_dict keys: 'codec', 'width', 'height', 'fps',
                        'duration_secs', 'audio_channels'
    """

    metadata_ready = pyqtSignal(str, dict)

    def __init__(self, files: List[Path]):
        super().__init__()
        self._files = files

    def run(self):
        from core.media_info import get_media_info

        for filepath in self._files:
            if self.is_cancelled:
                break
            try:
                info = get_media_info(filepath)
            except Exception:
                info = None

            if info is not None:
                self.metadata_ready.emit(str(filepath), {
                    'codec': info.codec,
                    'width': info.width,
                    'height': info.height,
                    'fps': info.fps,
                    'duration_secs': info.duration_secs,
                    'audio_channels': info.audio_channels,
                })

        self.emit_finished(True, "Metadata loading complete")
