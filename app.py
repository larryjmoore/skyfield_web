import io
import datetime
import logging
from functools import wraps
from flask import Flask, send_file, request, make_response
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from cachelib import SimpleCache
from werkzeug.middleware.proxy_fix import ProxyFix

import bodies

# --- Configuration ---
DEFAULT_LAT = 40.7608
DEFAULT_LON = -111.8910
DEFAULT_TZ = 'America/Denver'
DEFAULT_ELEV = 0
DEFAULT_GMT_OFFSET = -7

from dateutil.parser import parse as dateutil_parse

# --- Utility Functions ---

def parse_gmt_offset(offset_str):
    """Parses a GMT offset string into a float."""
    offset_str = offset_str.strip()
    if ':' in offset_str:
        parts = offset_str.split(':')
        hours = int(parts[0])
        minutes = int(parts[1])
        return hours - (minutes / 60.0) if hours < 0 else hours + (minutes / 60.0)
    if len(offset_str) == 5 and (offset_str.startswith(('+', '-'))) and offset_str[1:].isdigit():
        sign = -1 if offset_str[0] == '-' else 1
        hours = int(offset_str[1:3])
        minutes = int(offset_str[3:5])
        return sign * (hours + minutes / 60.0)
    if len(offset_str) == 4 and offset_str.isdigit():
        hours = int(offset_str[0:2])
        minutes = int(offset_str[2:4])
        return hours + (minutes / 60.0)
    return float(offset_str)

def is_true(key, default):
    """Checks if a request argument is true."""
    val = request.args.get(key)
    if val is None:
        return default
    return val.lower() in ['true', '1', 'yes', 'on']

def create_app():
    """Creates and configures the Flask app."""
    app = Flask(__name__)
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)
    
    logging.basicConfig(
        filename='requests.log',
        level=logging.INFO,
        format='%(asctime)s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    limiter = Limiter(
        get_remote_address,
        app=app,
        default_limits=["200 per day", "50 per hour"],
        storage_uri="memory://",
    )
    cache = SimpleCache()

    def ratelimit_handler(e):
        return make_response(f"Too Many Requests: {e.description}", 429)

    def cached(timeout=300):
        def decorator(f):
            @wraps(f)
            def decorated_function(*args, **kwargs):
                cache_key = str(sorted(request.args.items()))
                cached_image = cache.get(cache_key)
                if cached_image:
                    response = make_response(send_file(io.BytesIO(cached_image), mimetype='image/png'))
                    response.headers.set('X-Cache', 'HIT')
                    return response
                
                result = f(*args, **kwargs)
                if not isinstance(result, io.BytesIO):
                    return result

                cache.set(cache_key, result.getvalue(), timeout=timeout)
                result.seek(0)
                
                response = make_response(send_file(result, mimetype='image/png'))
                response.headers.set('X-Cache', 'MISS')
                return response
            return decorated_function
        return decorator

    @app.route('/skychart.png')
    @limiter.limit("1/second")
    @cached()
    def serve_sky_chart():
        visitor_ip = request.remote_addr
        requested_url = request.full_path.strip()
        logging.info(f"{visitor_ip} | {requested_url}")

        try:
            lat = float(request.args.get('lat', DEFAULT_LAT))
            lon = float(request.args.get('lon', DEFAULT_LON))
            elev = float(request.args.get('elevation', DEFAULT_ELEV))
            gmt_offset = parse_gmt_offset(request.args.get('gmt_offset', str(DEFAULT_GMT_OFFSET)))
            tz = datetime.timezone(datetime.timedelta(hours=gmt_offset))
        except (ValueError, TypeError):
            return "Error: Invalid lat, lon, elevation, or gmt_offset.", 400

        sky = bodies.Sky(
            latlong=(lat, lon),
            tz=tz,
            show_constellations=is_true('show_constellation', False),
            show_analemma=is_true('show_analemma', False),
            planet_list=None if is_true('show_planets', True) else [],
            show_time=is_true('show_time', True),
            show_legend=is_true('show_legend', True),
            north_up=is_true('north_up', False),
            show_stats=is_true('show_stats', True),
            dark_mode=is_true('dark_mode', False),
            image_type="png"
        )
        sky.load()

        when_param = request.args.get('when')

        if when_param:
            try:
                # Use dateutil.parser for robust date/time parsing
                naive_when = dateutil_parse(when_param.replace('_', ' '))
                when_aware = naive_when.replace(tzinfo=tz)
            except ValueError as e:
                return f"Error: Invalid 'when' parameter format. Could not parse date/time - {e}", 400
        else:
            when_aware = datetime.datetime.now(tz)

        buf = io.BytesIO()
        sky.plot_sky(output=buf, when=when_aware)
        return buf
    
    return app

def main():
    """Initializes and runs the Flask application."""
    app = create_app()
    print("Flask app starting...")
    app.run(host='0.0.0.0', port=8000)

if __name__ == '__main__':
    main()
