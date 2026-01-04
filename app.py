import io
import datetime
import logging
from flask import Flask, send_file, request, make_response
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from cachelib import SimpleCache
from skyfield.api import Loader
from werkzeug.middleware.proxy_fix import ProxyFix
import bodies

app = Flask(__name__)
# Fix for running behind a proxy like Gunicorn
# It will trust the X-Forwarded-For header.
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)
cache = SimpleCache()

limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://",
)

logging.basicConfig(
    filename='requests.log', 
    level=logging.INFO, 
    format='%(asctime)s | %(message)s', 
    datefmt='%Y-%m-%d %H:%M:%S'
)

DEFAULT_LAT = 40.7608
DEFAULT_LON = -111.8910
DEFAULT_TZ = 'America/Denver' 
DEFAULT_ELEV = 0
DEFAULT_GMT_OFFSET = -7
def ratelimit_handler(e):
    # Any rate limit hit now means the hard "1/second" limit was exceeded,
    # so we directly return the "Too Many Requests" error.
    return make_response(f"Too Many Requests: {e.description}", 429)

@app.route('/skychart.png')
@limiter.limit("1/second") # Hard limit for very fast polling
def serve_sky_chart():
    # Because of ProxyFix, request.remote_addr is now the real IP.
    visitor_ip = request.remote_addr
    
    # Create a cache key from the request arguments
    cache_key = str(sorted(request.args.items()))

    # Check if a cached image for these exact parameters exists
    cached_image = cache.get(cache_key)
    if cached_image:
        response = make_response(send_file(io.BytesIO(cached_image), mimetype='image/png'))
        response.headers.set('X-Cache', 'HIT')
        return response

    requested_url = request.full_path.strip()
    logging.info(f"{visitor_ip} | {requested_url}")

    try:
        lat = float(request.args.get('lat', DEFAULT_LAT))
        lon = float(request.args.get('lon', DEFAULT_LON))
        elev = float(request.args.get('elevation', DEFAULT_ELEV))
    except ValueError:
        return "Error: lat, lon, and elevation must be numbers.", 400

    try:
        offset_str = request.args.get('gmt_offset', str(DEFAULT_GMT_OFFSET)).strip()
        if ':' in offset_str:
            parts = offset_str.split(':')
            hours = int(parts[0])
            minutes = int(parts[1])
            if hours < 0:
                gmt_offset = hours - (minutes / 60.0)
            else:
                gmt_offset = hours + (minutes / 60.0)
        elif len(offset_str) == 5 and (offset_str.startswith('+') or offset_str.startswith('-')) and offset_str[1:].isdigit():
            sign = -1 if offset_str[0] == '-' else 1
            hours = int(offset_str[1:3])
            minutes = int(offset_str[3:5])
            gmt_offset = sign * (hours + minutes / 60.0)
        elif len(offset_str) == 4 and offset_str.isdigit():
            hours = int(offset_str[0:2])
            minutes = int(offset_str[2:4])
            gmt_offset = hours + (minutes / 60.0)
        else:
            gmt_offset = float(offset_str)
        tz = datetime.timezone(datetime.timedelta(hours=gmt_offset))
    except (ValueError, TypeError):
        return "Error: gmt_offset must be a number (e.g., -7, 5.5), in HH:MM format (e.g., -7:00, 5:30), or in +/-HHMM/HHMM format (e.g., -0700, 0530).", 400
    
    def is_true(key, default):
        val = request.args.get(key)
        if val is None: return default
        return val.lower() in ['true', '1', 'yes', 'on']

    show_analemma = is_true('show_analemma', False)
    show_constellations = is_true('show_constellation', False)
    show_planets = is_true('show_planets', True)
    north_up = is_true('north_up', False)
    show_time = is_true('show_time', True)
    show_legend = is_true('show_legend', True)
    show_stats = is_true('show_stats', True)
    dark_mode = is_true('dark_mode', False)
    
    planet_filter = None if show_planets else []

    sky = bodies.Sky(
        latlong=(lat, lon), 
        tz=tz,
        show_constellations=show_constellations,
        show_analemma=show_analemma,
        planet_list=planet_filter,
        show_time=show_time,
        show_legend=show_legend,
        north_up=north_up,
        image_type="png",
        show_stats=show_stats,
        dark_mode=dark_mode
    )

    sky.load() 
    # Get date and time from request args or default to now
    year = request.args.get('year', type=int)
    month = request.args.get('month', type=int)
    day = request.args.get('day', type=int)
    hour = request.args.get('hour', type=int)
    minute = request.args.get('minute', type=int)
    second = request.args.get('second', type=int)

    if all(v is not None for v in [year, month, day, hour, minute, second]):
        try:
            when_aware = tz.localize(datetime.datetime(year, month, day, hour, minute, second))
        except ValueError as e:
            return f"Error: Invalid date/time provided - {e}", 400
    else:
        when_aware = datetime.datetime.now(tz)
    
    when_naive = when_aware.replace(tzinfo=None)
    
    buf = io.BytesIO()
    sky.plot_sky(output=buf, when=when_aware)
    buf.seek(0)
    
    # Cache the generated image for this specific set of parameters for 5 minutes
    cache.set(cache_key, buf.getvalue(), timeout=300)
    
    buf.seek(0)
    response = make_response(send_file(buf, mimetype='image/png'))
    response.headers.set('X-Cache', 'MISS')
    return response

def main():
    print("Flask app starting...")
    app.run(host='0.0.0.0', port=8000)

if __name__ == '__main__':
    main()

