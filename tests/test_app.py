import unittest
from app import app, limiter

class AppTestCase(unittest.TestCase):
    def setUp(self):
        app.testing = True  # Enable testing mode for the app
        limiter.enabled = False # Disable Flask-Limiter for tests
        self.app = app.test_client()

    def test_sky_chart_is_generated(self):
        response = self.app.get('/skychart.png')
        self.assertEqual(response.status_code, 200)

    def test_sky_chart_is_generated_with_north_up(self):
        response = self.app.get('/skychart.png?north_up=true')
        self.assertEqual(response.status_code, 200)

    def test_gmt_offset_float(self):
        response = self.app.get('/skychart.png?gmt_offset=-7.5')
        self.assertEqual(response.status_code, 200)

    def test_gmt_offset_hh_mm(self):
        response = self.app.get('/skychart.png?gmt_offset=5:30')
        self.assertEqual(response.status_code, 200)

    def test_gmt_offset_plus_hhmm(self):
        response = self.app.get('/skychart.png?gmt_offset=%2B0700') # URL-encoded + for +0700
        self.assertEqual(response.status_code, 200)

    def test_gmt_offset_minus_hhmm(self):
        response = self.app.get('/skychart.png?gmt_offset=-0700')
        self.assertEqual(response.status_code, 200)

    def test_gmt_offset_hhmm(self):
        response = self.app.get('/skychart.png?gmt_offset=0530')
        self.assertEqual(response.status_code, 200)

    def test_gmt_offset_invalid_format(self):
        response = self.app.get('/skychart.png?gmt_offset=invalid')
        self.assertEqual(response.status_code, 400)
        self.assertIn(b"Error: gmt_offset must be a number", response.data)

    def test_gmt_offset_invalid_hh_mm(self):
        response = self.app.get('/skychart.png?gmt_offset=5:xx')
        self.assertEqual(response.status_code, 400)
        self.assertIn(b"Error: gmt_offset must be a number", response.data)

    def test_gmt_offset_invalid_hhmm(self):
        response = self.app.get('/skychart.png?gmt_offset=-07x0')
        self.assertEqual(response.status_code, 400)
        self.assertIn(b"Error: gmt_offset must be a number", response.data)

if __name__ == '__main__':
    unittest.main()
