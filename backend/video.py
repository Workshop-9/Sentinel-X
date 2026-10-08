import logging
import os
import threading
from collections.abc import Iterator

import cv2

logger = logging.getLogger(__name__)

CAMERA_INDEX = int(os.getenv("CAMERA_INDEX", "0"))
JPEG_QUALITY = 80
CAMERA_START_TIMEOUT_S = 5


class CameraUnavailable(Exception):
    pass


class CameraStream:
    def __init__(self, camera_index: int):
        self.camera_index = camera_index
        self._condition = threading.Condition()
        self._start_lock = threading.Lock()
        self._stop_event = threading.Event()
        self._capture = None
        self._thread = None
        self._frame: bytes | None = None
        self._frame_number = 0
        self._error: str | None = None

    def start(self):
        with self._start_lock:
            with self._condition:
                if self._thread is not None and self._thread.is_alive():
                    ready = self._condition.wait_for(
                        lambda: self._frame is not None or self._error is not None,
                        timeout=CAMERA_START_TIMEOUT_S,
                    )
                    if (
                        ready
                        and self._frame is not None
                        and self._error is None
                        and not self._stop_event.is_set()
                    ):
                        return
                    message = self._error or "La webcam n’a fourni aucune image."
                else:
                    try:
                        capture = cv2.VideoCapture(self.camera_index)
                    except cv2.error as error:
                        raise CameraUnavailable(
                            f"Impossible d’ouvrir la webcam d’index {self.camera_index}."
                        ) from error
                    if not capture.isOpened():
                        capture.release()
                        raise CameraUnavailable(
                            f"Impossible d’ouvrir la webcam d’index {self.camera_index}."
                        )

                    self._stop_event.clear()
                    self._capture = capture
                    self._frame = None
                    self._frame_number = 0
                    self._error = None
                    self._thread = threading.Thread(
                        target=self._read_frames,
                        name="sentinel-camera",
                        daemon=True,
                    )
                    self._thread.start()
                    ready = self._condition.wait_for(
                        lambda: self._frame is not None or self._error is not None,
                        timeout=CAMERA_START_TIMEOUT_S,
                    )
                    if (
                        ready
                        and self._frame is not None
                        and self._error is None
                        and not self._stop_event.is_set()
                    ):
                        return
                    message = self._error or "La webcam n’a fourni aucune image."

            self.stop()
            raise CameraUnavailable(message)

    def stop(self):
        with self._condition:
            self._stop_event.set()
            thread = self._thread
            self._condition.notify_all()

        if thread is not None:
            thread.join(timeout=CAMERA_START_TIMEOUT_S)
            if thread.is_alive():
                logger.warning("Le thread de capture webcam ne s’est pas arrêté.")

    def iter_mjpeg(self) -> Iterator[bytes]:
        last_frame_number = 0
        while True:
            with self._condition:
                ready = self._condition.wait_for(
                    lambda: self._frame_number > last_frame_number
                    or self._error is not None
                    or self._stop_event.is_set(),
                    timeout=CAMERA_START_TIMEOUT_S,
                )
                if not ready or self._error or self._stop_event.is_set():
                    return
                frame = self._frame
                last_frame_number = self._frame_number

            if frame is not None:
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n"
                    + f"Content-Length: {len(frame)}\r\n\r\n".encode("ascii")
                    + frame
                    + b"\r\n"
                )

    def _read_frames(self):
        try:
            while not self._stop_event.is_set():
                success, image = self._capture.read()
                if not success or image is None:
                    self._set_error("La lecture de la webcam a échoué.")
                    return

                success, jpeg = cv2.imencode(
                    ".jpg",
                    image,
                    [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY],
                )
                if not success:
                    self._set_error("Impossible d’encoder une image de la webcam.")
                    return

                with self._condition:
                    self._frame = jpeg.tobytes()
                    self._frame_number += 1
                    self._condition.notify_all()
        except Exception as error:
            logger.exception("Erreur pendant la capture webcam.")
            self._set_error(f"Erreur pendant la capture webcam : {error}")
        finally:
            if self._capture is not None:
                self._capture.release()
            with self._condition:
                self._condition.notify_all()

    def _set_error(self, message: str):
        logger.error("%s", message)
        with self._condition:
            self._error = message
            self._condition.notify_all()


camera_stream = CameraStream(CAMERA_INDEX)
