import unittest

from ultrasound_bmode.native_backend import native_available, native_library_path


class NativeBackendTests(unittest.TestCase):
    def test_availability_matches_library_path(self):
        self.assertEqual(native_available(), native_library_path() is not None)
