import io
import datetime
import logging
import sys
from functools import wraps
from typing import Any, Callable, Optional, Union, List
from flask import Flask, send_file, request, make_response, Response
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from cachelib import FileSystemCache
from werkzeug.middleware.proxy_fix import ProxyFix
from pydantic import BaseModel, Field, ValidationError, field_validator, BeforeValidator
from typing_extensions import Annotated

import bodies

# --- Configuration ---
DEFAULT_LAT = 40.7608
DEFAULT_LON = -111.8910
DEFAULT_TZ = 'America/Denver'
DEFAULT_ELEV = 0
DEFAULT_GMT_OFFSET = -7

from dateutil.parser import parse as dateutil_parse

# --- Pydantic Models ---

def parse_gmt_offset_str(offset_str: Union[str, float, int]) -> float:
    """Parses a GMT offset string into a float."""
    if isinstance(offset_str, (float, int)):
        return float(offset_str)
    
    offset_str = str(offset_str).strip()
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

def parse_bool_str(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    if v is None:
        return False
    return str(v).lower() in ['true', '1', 'yes', 'on']

def parse_dark_mode(v: Any) -> Union[bool, str]:
    if isinstance(v, str) and v.lower() == 'auto':
        return 'auto'
    return parse_bool_str(v)

GMT_Offset = Annotated[float, BeforeValidator(parse_gmt_offset_str)]
Bool_Param = Annotated[bool, BeforeValidator(parse_bool_str)]
DarkMode_Param = Annotated[Union[bool, str], BeforeValidator(parse_dark_mode)]

class SkyChartParams(BaseModel):
    lat: float = Field(default=DEFAULT_LAT)
    lon: float = Field(default=DEFAULT_LON)
    elevation: float = Field(default=DEFAULT_ELEV)
    gmt_offset: GMT_Offset = Field(default=DEFAULT_GMT_OFFSET)
    when: Optional[str] = None
    show_analemma: Bool_Param = False
    show_constellation: Bool_Param = False
    show_planets: Bool_Param = True
    show_time: Bool_Param = True
    show_legend: Bool_Param = True
    north_up: Bool_Param = False
    show_stats: Bool_Param = True
    dark_mode: DarkMode_Param = False

def create_app() -> Flask:
    """Creates and configures the Flask app."""
    app = Flask(__name__)
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1) # type: ignore
    
    # Configure logging to both stdout and file
    handlers: List[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    
    try:
        handlers.append(logging.FileHandler('requests.log'))
    except (PermissionError, OSError):
        # Fallback if we cannot write to the file (e.g. running in a restricted directory)
        sys.stderr.write("WARNING: Could not create 'requests.log' due to permissions. Logging to stdout only.\n")

    logging.basicConfig(
        handlers=handlers,
        level=logging.INFO,
        format='%(asctime)s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Disable default Werkzeug logging (request logs) to avoid double logging
    logging.getLogger('werkzeug').setLevel(logging.ERROR)

    limiter = Limiter(
        get_remote_address,
        app=app,
        default_limits=["200 per day", "50 per hour"],
        storage_uri="memory://",
    )
    
    # Use FileSystemCache to share cache between Gunicorn workers
    import os
    cache_dir = os.path.join(os.getcwd(), 'flask_cache')
    if not os.path.exists(cache_dir):
        os.makedirs(cache_dir)
    cache = FileSystemCache(cache_dir, threshold=1000, default_timeout=60)

    def ratelimit_handler(e: Any) -> Response:
        return make_response(f"Too Many Requests: {e.description}", 429)

    def cached(timeout: int = 55) -> Callable:
        def decorator(f: Callable) -> Callable:
            @wraps(f)
            def decorated_function(*args: Any, **kwargs: Any) -> Any:
                import time
                start_time = time.time()
                
                # Prepare log info container
                from flask import g
                
                # Check show_analemma param for initial status
                show_analemma_str = request.args.get('show_analemma', 'false')
                is_analemma_requested = parse_bool_str(show_analemma_str)
                
                # Default states
                g.analemma_status = "HIT" if is_analemma_requested else "N/A"
                image_cache_status = "MISS"

                cache_key = str(sorted(request.args.items()))
                cached_image = cache.get(cache_key)
                
                def log_request(img_status: str, ana_status: str):
                    duration = time.time() - start_time
                    visitor_ip = request.remote_addr
                    # Reconstruct query string from args to ensure sorted/consistent or just use raw
                    # Using raw query string is better for debugging exact requests
                    url_args = request.query_string.decode('utf-8')
                    logging.info(f"{visitor_ip} | Image: {img_status} | Analemma: {ana_status} | Duration: {duration:.2f}s | Args: {url_args}")

                if cached_image:
                    image_cache_status = "HIT"
                    # If image is cached, we don't calculate analemmas, so Analemma status is effectively Skipped/N/A
                    # But per user request "Analemma cache hit or miss", if we skip it, it's not a hit or miss.
                    # However, "HIT" implies we didn't do work. 
                    # Let's mark it as "Skipped (Image Cached)" or just keep the initial intention.
                    # If image is HIT, we return early.
                    log_request("HIT", "Skipped")
                    
                    response = make_response(send_file(io.BytesIO(cached_image), mimetype='image/png'))
                    response.headers.set('X-Cache', 'HIT')
                    return response
                
                # Image Cache MISS - Proceed to generate
                result = f(*args, **kwargs)
                
                # After generation, check g.analemma_status (it might have changed to MISS in bodies.py)
                log_request("MISS", g.analemma_status)
                
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
    def serve_sky_chart() -> Union[Response, tuple[str, int]]:
        try:
            # Pydantic validation
            params = SkyChartParams(**request.args.to_dict())
            tz = datetime.timezone(datetime.timedelta(hours=params.gmt_offset))
        except (ValidationError, ValueError, TypeError) as e:
            return f"Error: Invalid parameters - {e}", 400

        if params.when:
            try:
                # Use dateutil.parser for robust date/time parsing
                naive_when = dateutil_parse(params.when.replace('_', ' '))
                when_aware = naive_when.replace(tzinfo=tz)
            except ValueError as e:
                return f"Error: Invalid 'when' parameter format. Could not parse date/time - {e}", 400
        else:
            when_aware = datetime.datetime.now(tz)

        final_dark_mode = params.dark_mode
        if final_dark_mode == 'auto':
            # Calculate sun position to determine if it is night
            calc = bodies.SkyCalculator((params.lat, params.lon), tz)
            _, r = calc.compute_position(bodies.sky_data.eph[bodies.SUN], when_aware)
            # r is 90 - altitude. So if r > 90, altitude is negative (below horizon).
            final_dark_mode = (r > 90)

        sky = bodies.Sky(
            latlong=(params.lat, params.lon),
            tz=tz,
            show_constellations=params.show_constellation,
            show_analemma=params.show_analemma,
            planet_list=None if params.show_planets else [],
            show_time=params.show_time,
            show_legend=params.show_legend,
            north_up=params.north_up,
            show_stats=params.show_stats,
            dark_mode=final_dark_mode,
            image_type="png"
        )
        sky.load()

        buf = io.BytesIO()
        sky.plot_sky(output=buf, when=when_aware)
        return buf
    
    return app

app = create_app()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)
