import asyncio
import json
import logging
import os
import re
import shutil
import tempfile
import tomllib
from datetime import datetime, timedelta
from typing import Optional

import httpx
from fastapi import BackgroundTasks, HTTPException, Query
from fastapi.responses import StreamingResponse

logger = logging.getLogger(__name__)

API_URL = "http://api:8000"


class _RecordingMinio:
    BUCKET = "recordings"

    def __init__(self):
        from minio import Minio

        config_path = os.path.join(os.path.dirname(__file__), "minio_config.toml")
        with open(config_path, "rb") as f:
            cfg = tomllib.load(f)["minio"]

        self._client = Minio(
            endpoint=cfg["ENDPOINT"],
            access_key=cfg["ACCESS_KEY"],
            secret_key=cfg["SECRET_KEY"],
            secure=cfg["SECURE"],
        )
        self._public = cfg.get("PUBLIC_ENDPOINT", cfg["ENDPOINT"])

        try:
            if not self._client.bucket_exists(self.BUCKET):
                self._client.make_bucket(self.BUCKET)
            policy = {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Principal": {"AWS": ["*"]},
                        "Action": ["s3:GetObject"],
                        "Resource": [f"arn:aws:s3:::{self.BUCKET}/*"],
                    }
                ],
            }
            self._client.set_bucket_policy(self.BUCKET, json.dumps(policy))
        except Exception as e:
            logger.error(f"MinIO recordings bucket setup: {e}")

    def upload(self, file_path: str, object_name: str) -> str:
        from minio.error import S3Error

        try:
            ext = os.path.splitext(file_path)[1].lower()
            if ext in (".mp4", ".fmp4"):
                ctype = "video/mp4"
            elif ext == ".ts":
                ctype = "video/mp2t"
            else:
                ctype = "application/octet-stream"
            self._client.fput_object(
                self.BUCKET, object_name, file_path, content_type=ctype
            )
            return f"http://{self._public}/{self.BUCKET}/{object_name}"
        except S3Error as e:
            logger.error(f"MinIO upload error for '{object_name}': {e}")
            return ""

    def download(self, object_name: str, dest_path: str) -> bool:
        from minio.error import S3Error

        try:
            self._client.fget_object(self.BUCKET, object_name, dest_path)
            return True
        except S3Error as e:
            logger.error(f"MinIO download error for '{object_name}': {e}")
            return False


_minio: Optional[_RecordingMinio] = None


def _get_minio() -> _RecordingMinio:
    global _minio
    if _minio is None:
        _minio = _RecordingMinio()
    return _minio


def _parse_segment_time(filename: str) -> Optional[datetime]:
    base = os.path.splitext(filename)[0]
    try:
        return datetime.strptime(base, "%Y-%m-%d_%H-%M-%S-%f")
    except ValueError:
        return None


def _parse_duration(duration_str: str) -> int:
    total = 0
    for m in re.finditer(r"(\d+)([hms])", str(duration_str)):
        v, u = int(m.group(1)), m.group(2)
        if u == "h":
            total += v * 3600
        elif u == "m":
            total += v * 60
        elif u == "s":
            total += v
    return total or 300


async def _upload_segment(camera_path: str, segment_file: str, duration_str: str):
    if not os.path.exists(segment_file) or os.path.getsize(segment_file) == 0:
        logger.warning(f"[RECORDER] Segment not found or empty: {segment_file}")
        return

    filename = os.path.basename(segment_file)
    started_at = _parse_segment_time(filename)
    duration_sec = _parse_duration(duration_str)
    ended_at = started_at + timedelta(seconds=duration_sec) if started_at else None
    file_size = os.path.getsize(segment_file)

    object_name = f"{camera_path}/{filename}"
    minio_url = await asyncio.to_thread(_get_minio().upload, segment_file, object_name)

    if not minio_url:
        logger.error(f"[RECORDER] MinIO upload failed for {filename}")
        return

    logger.info(f"[RECORDER] Uploaded {filename} → {minio_url}")

    try:
        os.remove(segment_file)
        logger.info(f"[RECORDER] Deleted local segment {segment_file}")
    except OSError as e:
        logger.warning(f"[RECORDER] Could not delete local segment: {e}")

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(
                f"{API_URL}/internal/recordings",
                json={
                    "camera_path": camera_path,
                    "minio_object": object_name,
                    "minio_url": minio_url,
                    "started_at": started_at.isoformat() if started_at else None,
                    "ended_at": ended_at.isoformat() if ended_at else None,
                    "duration_sec": duration_sec,
                    "file_size": file_size,
                },
            )
    except Exception as e:
        logger.error(f"[RECORDER] API registration failed: {e}")


async def handle_webhook(
    path: str, segment: str, duration: str, bg: BackgroundTasks
) -> dict:
    bg.add_task(_upload_segment, path, segment, duration)
    return {"ok": True}


async def handle_download(camera: str, start: str, end: str) -> StreamingResponse:
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{API_URL}/recordings",
                params={"camera": camera, "start": start, "end": end},
            )
            resp.raise_for_status()
            segments = resp.json().get("recordings", [])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Segment lookup failed: {e}")

    if not segments:
        raise HTTPException(status_code=404, detail="No recordings found for range")

    minio = _get_minio()
    tmp_dir = tempfile.mkdtemp(prefix="rec_dl_")

    try:
        sorted_segs = sorted(segments, key=lambda s: s.get("started_at", ""))
        tmp_paths = []
        download_tasks = []
        for seg in sorted_segs:
            local_path = os.path.join(tmp_dir, os.path.basename(seg["minio_object"]))
            tmp_paths.append((local_path, seg))
            download_tasks.append(
                asyncio.to_thread(minio.download, seg["minio_object"], local_path)
            )

        results = await asyncio.gather(*download_tasks, return_exceptions=True)
        local_files = [
            (path, seg)
            for (path, seg), result in zip(tmp_paths, results)
            if result is True
        ]

        if not local_files:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            raise HTTPException(
                status_code=500, detail="Failed to retrieve segment files from storage"
            )

        concat_file = os.path.join(tmp_dir, "concat.txt")
        with open(concat_file, "w") as f:
            for path, _ in local_files:
                f.write(f"file '{path}'\n")

        start_dt = datetime.fromisoformat(start.replace("Z", "+00:00")).replace(tzinfo=None)
        end_dt = datetime.fromisoformat(end.replace("Z", "+00:00")).replace(tzinfo=None)
        first_start = datetime.fromisoformat(local_files[0][1]["started_at"])
        trim_ss = max(0.0, (start_dt - first_start).total_seconds())
        trim_t = max(1.0, (end_dt - start_dt).total_seconds())

        output_file = os.path.join(tmp_dir, "output.mp4")
        cmd = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0",
            "-i", concat_file,
            "-ss", str(trim_ss),
            "-t", str(trim_t),
            "-c", "copy",
            output_file,
        ]

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            await asyncio.wait_for(proc.communicate(), timeout=180)
        except asyncio.TimeoutError:
            proc.kill()
            shutil.rmtree(tmp_dir, ignore_errors=True)
            raise HTTPException(status_code=504, detail="FFmpeg processing timeout")

        if proc.returncode != 0:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            raise HTTPException(status_code=500, detail="FFmpeg processing failed")

    except HTTPException:
        raise
    except Exception as e:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise HTTPException(status_code=500, detail=str(e))

    def stream_file():
        try:
            with open(output_file, "rb") as f:
                while chunk := f.read(1024 * 1024):
                    yield chunk
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    safe_cam = camera.replace("/", "_")
    fname = f"recording_{safe_cam}_{start[:10]}.mp4"
    return StreamingResponse(
        stream_file(),
        media_type="video/mp4",
        headers={"Content-Disposition": f"attachment; filename={fname}"},
    )
