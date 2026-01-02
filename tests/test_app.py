import unittest
from skyfield_web.app import app

class AppTestCase(unittest.TestCase):
    def setUp(self):
        self.app = app.test_client()

    def test_sky_chart_is_generated(self):
        response = self.app.get('/skychart.png')
        self.assertEqual(response.status_code, 200)

    def test_sky_chart_is_generated_with_north_up(self):
        response = self.app.get('/skychart.png?north_up=true')
        self.assertEqual(response.status_code, 200)

if __name__ == '__main__':
    unittest.main()
