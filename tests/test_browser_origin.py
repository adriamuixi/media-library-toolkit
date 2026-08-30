import unittest

from media_toolkit.browser.origin import classify_whatsapp_evidence


class BrowserOriginTests(unittest.TestCase):
    def test_recognizes_conservative_whatsapp_filename_patterns(self) -> None:
        for filename in (
            "IMG-20201228-WA0024.jpg",
            "VID-20240229-WA0123.mp4",
            "PTT-20200101-WA0001.opus",
            "WhatsApp Image 2020-12-28 at 12.34.56.jpeg",
        ):
            with self.subTest(filename=filename):
                evidence = classify_whatsapp_evidence(filename)
                self.assertTrue(evidence.is_whatsapp)
                self.assertEqual(evidence.reason, "FILENAME_PATTERN")

    def test_recognizes_whatsapp_path_components(self) -> None:
        evidence = classify_whatsapp_evidence(
            "mobile photos/WhatsApp Images/holiday.jpg"
        )

        self.assertTrue(evidence.is_whatsapp)
        self.assertEqual(evidence.reason, "PATH_COMPONENT")

    def test_does_not_infer_whatsapp_from_unrelated_wa_text(self) -> None:
        evidence = classify_whatsapp_evidence("Washington/IMG_0024.jpg")

        self.assertFalse(evidence.is_whatsapp)
        self.assertEqual(evidence.reason, "NO_WHATSAPP_EVIDENCE")


if __name__ == "__main__":
    unittest.main()
