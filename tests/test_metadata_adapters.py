from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

from media_toolkit.metadata.exiftool import ExifToolAdapter
from media_toolkit.metadata.ffprobe import FfprobeAdapter
from media_toolkit.metadata.models import ToolStatus


class MetadataAdapterTests(unittest.TestCase):
    def test_exiftool_normalizes_photo_geometry_and_camera_fields(self) -> None:
        output = """[{"EXIF:ImageWidth":4000,"EXIF:ImageHeight":3000,"EXIF:Orientation":6,"EXIF:Make":"Example","EXIF:Model":"Camera","EXIF:ISO":200}]"""
        completed = subprocess.CompletedProcess([], 0, output, "")
        adapter = ExifToolAdapter("exiftool", 10, 2.0)
        status = ToolStatus("ExifTool", "/tools/exiftool", True, "13.0", None)

        with patch("media_toolkit.metadata.exiftool.subprocess.run", return_value=completed):
            result = adapter.extract(Path("photo.jpg"), status)

        self.assertEqual(result.normalized.stored_width_px, 4000)
        self.assertEqual(result.normalized.display_width_px, 3000)
        self.assertEqual(result.normalized.orientation_class, "PORTRAIT")
        self.assertEqual(result.normalized.camera_make, "Example")
        self.assertEqual(result.normalized.iso, 200)

    def test_ffprobe_normalizes_duration_streams_and_rotation(self) -> None:
        output = """{"streams":[{"codec_type":"video","codec_name":"hevc","width":3840,"height":2160,"avg_frame_rate":"30000/1001","r_frame_rate":"30000/1001","tags":{"rotate":"90"},"color_transfer":"smpte2084"},{"codec_type":"audio","codec_name":"aac","sample_rate":"48000","channels":2}],"format":{"format_name":"mov,mp4","duration":"12.345","bit_rate":"9000000"}}"""
        completed = subprocess.CompletedProcess([], 0, output, "")
        adapter = FfprobeAdapter("ffprobe", 10, 2.0)
        status = ToolStatus("ffprobe", "/tools/ffprobe", True, "7.0", None)

        with patch("media_toolkit.metadata.ffprobe.subprocess.run", return_value=completed):
            result = adapter.extract(Path("video.mov"), status)

        self.assertEqual(result.normalized.duration_ms, 12345)
        self.assertEqual(result.normalized.display_width_px, 2160)
        self.assertEqual(result.normalized.video_codec, "hevc")
        self.assertEqual(result.normalized.audio_codec, "aac")
        self.assertEqual(result.normalized.stream_count, 2)
        self.assertEqual(result.normalized.dynamic_range, "HDR")


if __name__ == "__main__":
    unittest.main()
