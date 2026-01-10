import unittest
from unittest.mock import patch, MagicMock
from app import create_app
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

class AppTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.testing = True
        self.limiter = Limiter(
            get_remote_address,
            app=self.app,
            default_limits=[],
            storage_uri="memory://",
        )
        self.limiter.enabled = False
        self.client = self.app.test_client()

    def test_sky_chart_is_generated(self):
        response = self.client.get('/skychart.png')
        self.assertEqual(response.status_code, 200)

    def test_sky_chart_is_generated_with_north_up(self):
        response = self.client.get('/skychart.png?north_up=true')
        self.assertEqual(response.status_code, 200)

    def test_gmt_offset_float(self):
        response = self.client.get('/skychart.png?gmt_offset=-7.5')
        self.assertEqual(response.status_code, 200)

    def test_gmt_offset_hh_mm(self):
        response = self.client.get('/skychart.png?gmt_offset=5:30')
        self.assertEqual(response.status_code, 200)

    def test_gmt_offset_plus_hhmm(self):
        response = self.client.get('/skychart.png?gmt_offset=%2B0700') # URL-encoded + for +0700
        self.assertEqual(response.status_code, 200)

    def test_gmt_offset_minus_hhmm(self):
        response = self.client.get('/skychart.png?gmt_offset=-0700')
        self.assertEqual(response.status_code, 200)

    def test_gmt_offset_hhmm(self):
        response = self.client.get('/skychart.png?gmt_offset=0530')
        self.assertEqual(response.status_code, 200)

    def test_gmt_offset_invalid_format(self):
        response = self.client.get('/skychart.png?gmt_offset=invalid')
        self.assertEqual(response.status_code, 400)
        self.assertIn(b"Error: Invalid parameters", response.data)

    def test_gmt_offset_invalid_hh_mm(self):
        response = self.client.get('/skychart.png?gmt_offset=5:xx')
        self.assertEqual(response.status_code, 400)
        self.assertIn(b"Error: Invalid parameters", response.data)

    def test_gmt_offset_invalid_hhmm(self):
        response = self.client.get('/skychart.png?gmt_offset=-07x0')
        self.assertEqual(response.status_code, 400)
        self.assertIn(b"Error: Invalid parameters", response.data)

    def test_lat_valid(self):
        response = self.client.get('/skychart.png?lat=34.05')
        self.assertEqual(response.status_code, 200)
    
    def test_lat_invalid(self):
        response = self.client.get('/skychart.png?lat=not_a_number')
        self.assertEqual(response.status_code, 400)
        self.assertIn(b"Error: Invalid parameters", response.data)

    def test_lon_valid(self):
        response = self.client.get('/skychart.png?lon=-118.25')
        self.assertEqual(response.status_code, 200)

    def test_lon_invalid(self):
        response = self.client.get('/skychart.png?lon=not_a_number')
        self.assertEqual(response.status_code, 400)
        self.assertIn(b"Error: Invalid parameters", response.data)

    def test_elevation_valid(self):
        response = self.client.get('/skychart.png?elevation=1000')
        self.assertEqual(response.status_code, 200)

    def test_elevation_invalid(self):
        response = self.client.get('/skychart.png?elevation=not_a_number')
        self.assertEqual(response.status_code, 400)
        self.assertIn(b"Error: Invalid parameters", response.data)

    def test_show_analemma_true(self):
        response = self.client.get('/skychart.png?show_analemma=true')
        self.assertEqual(response.status_code, 200)

    def test_show_analemma_false(self):
        response = self.client.get('/skychart.png?show_analemma=false')
        self.assertEqual(response.status_code, 200)

    def test_show_constellation_true(self):
        response = self.client.get('/skychart.png?show_constellation=true')
        self.assertEqual(response.status_code, 200)

    def test_show_constellation_false(self):
        response = self.client.get('/skychart.png?show_constellation=false')
        self.assertEqual(response.status_code, 200)

    def test_show_planets_true(self):
        response = self.client.get('/skychart.png?show_planets=true')
        self.assertEqual(response.status_code, 200)

    def test_show_planets_false(self):
        response = self.client.get('/skychart.png?show_planets=false')
        self.assertEqual(response.status_code, 200)

    def test_north_up_true(self):
        response = self.client.get('/skychart.png?north_up=true')
        self.assertEqual(response.status_code, 200)

    def test_north_up_false(self):
        response = self.client.get('/skychart.png?north_up=false')
        self.assertEqual(response.status_code, 200)

    def test_show_time_true(self):
        response = self.client.get('/skychart.png?show_time=true')
        self.assertEqual(response.status_code, 200)

    def test_show_time_false(self):
        response = self.client.get('/skychart.png?show_time=false')
        self.assertEqual(response.status_code, 200)

    def test_show_legend_true(self):
        response = self.client.get('/skychart.png?show_legend=true')
        self.assertEqual(response.status_code, 200)

    def test_show_legend_false(self):
        response = self.client.get('/skychart.png?show_legend=false')
        self.assertEqual(response.status_code, 200)

    def test_show_stats_true(self):
        response = self.client.get('/skychart.png?show_stats=true')
        self.assertEqual(response.status_code, 200)

    def test_show_stats_false(self):
        response = self.client.get('/skychart.png?show_stats=false')
        self.assertEqual(response.status_code, 200)

    def test_dark_mode_true(self):
        response = self.client.get('/skychart.png?dark_mode=true')
        self.assertEqual(response.status_code, 200)

    def test_dark_mode_false(self):
        response = self.client.get('/skychart.png?dark_mode=false')
        self.assertEqual(response.status_code, 200)

    def test_when_format_full(self):
        response = self.client.get('/skychart.png?when=2023-10-26_14:30:00')
        self.assertEqual(response.status_code, 200)
        
    def test_when_format_short(self):
        response = self.client.get('/skychart.png?when=2023-10-26_14:30')
        self.assertEqual(response.status_code, 200)

    def test_when_format_date_only(self):
        response = self.client.get('/skychart.png?when=2023-10-26')
        self.assertEqual(response.status_code, 200)

    def test_when_format_single_digit_date(self):
        response = self.client.get('/skychart.png?when=2026-1-1')
        self.assertEqual(response.status_code, 200)

    def test_when_invalid_format(self):
        response = self.client.get('/skychart.png?when=invalid-date-time')
        self.assertEqual(response.status_code, 400)
        self.assertIn(b"Error: Invalid 'when' parameter format", response.data)

    def test_when_missing(self):
        response = self.client.get('/skychart.png') # Should default to current time
        self.assertEqual(response.status_code, 200)

    @patch('app.bodies.Sky')
    @patch('app.bodies.SkyCalculator')
    def test_dark_mode_auto_night(self, mock_calculator, mock_sky):
        # Mock Calculator to simulate night (Sun below horizon -> r > 90)
        mock_calc_instance = MagicMock()
        mock_calculator.return_value = mock_calc_instance
        # compute_position returns (theta, r). 
        # Night: r > 90. Let's return (0, 100)
        mock_calc_instance.compute_position.return_value = (0.0, 100.0)

        # Mock Sky to just return an object with load/plot_sky methods
        mock_sky_instance = MagicMock()
        mock_sky.return_value = mock_sky_instance

        # Call with dark_mode=auto
        response = self.client.get('/skychart.png?dark_mode=auto&lat=40&lon=-111')
        
        self.assertEqual(response.status_code, 200)
        
        # Verify bodies.Sky was initialized with dark_mode=True
        # Check call args of mock_sky
        args, kwargs = mock_sky.call_args
        self.assertTrue(kwargs.get('dark_mode'), "Expected dark_mode=True for night time")

    @patch('app.bodies.Sky')
    @patch('app.bodies.SkyCalculator')
    def test_dark_mode_auto_day(self, mock_calculator, mock_sky):
        # Mock Calculator to simulate day (Sun above horizon -> r <= 90)
        mock_calc_instance = MagicMock()
        mock_calculator.return_value = mock_calc_instance
        # Day: r <= 90. Let's return (0, 45)
        mock_calc_instance.compute_position.return_value = (0.0, 45.0)

        mock_sky_instance = MagicMock()
        mock_sky.return_value = mock_sky_instance

        response = self.client.get('/skychart.png?dark_mode=auto&lat=40&lon=-111')
        self.assertEqual(response.status_code, 200)

        # Verify bodies.Sky was initialized with dark_mode=False
        args, kwargs = mock_sky.call_args
        self.assertFalse(kwargs.get('dark_mode'), "Expected dark_mode=False for day time")

if __name__ == '__main__':
    unittest.main()
