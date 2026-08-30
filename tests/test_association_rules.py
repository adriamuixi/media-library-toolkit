import unittest

from media_toolkit.associations.models import ObservedMedia
from media_toolkit.associations.rules import detect_relations


def observed(
    media_id: str,
    filename: str,
    extension: str,
    media_type: str,
    identifiers: tuple[str, ...] = (),
) -> ObservedMedia:
    return ObservedMedia(
        media_id=media_id,
        relative_path=f"folder/{filename}",
        parent_key="folder",
        stem_key=filename.rsplit(".", 1)[0].casefold(),
        extension=extension,
        media_type=media_type,
        metadata_identifiers=identifiers,
    )


class AssociationRuleTests(unittest.TestCase):
    def test_metadata_identifier_is_stronger_than_live_photo_basename(self) -> None:
        photo = observed("photo", "IMG_100.HEIC", ".heic", "PHOTO", ("asset-1",))
        video = observed("video", "DIFFERENT.MOV", ".mov", "VIDEO", ("asset-1",))

        relations = detect_relations((photo, video))

        self.assertEqual(len(relations), 1)
        self.assertEqual(relations[0].relation_type, "LIVE_PHOTO_PAIR")
        self.assertEqual(relations[0].confidence, "HIGH")
        self.assertEqual(relations[0].match_method, "METADATA_IDENTIFIER")

    def test_ambiguous_live_photo_basename_is_a_conflict(self) -> None:
        files = (
            observed("heic", "IMG_100.HEIC", ".heic", "PHOTO"),
            observed("jpeg", "IMG_100.JPG", ".jpg", "PHOTO"),
            observed("video", "IMG_100.MOV", ".mov", "VIDEO"),
        )

        relations = detect_relations(files)

        live_relations = [item for item in relations if item.relation_type == "LIVE_PHOTO_PAIR"]
        self.assertEqual(len(live_relations), 2)
        self.assertTrue(all(item.status == "CONFLICT" for item in live_relations))

    def test_raw_jpeg_and_xmp_are_distinct_relations(self) -> None:
        files = (
            observed("raw", "DSC_1.CR3", ".cr3", "PHOTO"),
            observed("jpeg", "DSC_1.JPG", ".jpg", "PHOTO"),
            observed("xmp", "DSC_1.XMP", ".xmp", "SIDECAR"),
        )

        relations = detect_relations(files)

        by_type = {item.relation_type: item for item in relations}
        self.assertEqual(by_type["RAW_JPEG_PAIR"].primary_media_id, "raw")
        self.assertEqual(by_type["RAW_JPEG_PAIR"].companion_media_id, "jpeg")
        self.assertEqual(by_type["SIDECAR_ASSOCIATION"].primary_media_id, "raw")
        self.assertEqual(by_type["SIDECAR_ASSOCIATION"].companion_media_id, "xmp")


if __name__ == "__main__":
    unittest.main()
