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

if __name__ == '__main__':
    unittest.main()
