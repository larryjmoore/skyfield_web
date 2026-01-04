"""Collect data about where celestial bodies are."""

# This file is adapted from the ha_skyfield project:
# https://github.com/partofthething/ha_skyfield

import datetime
import math
from functools import lru_cache
from skyfield.api import Loader, Topos
from skyfield import almanac
from astral.location import LocationInfo
from astral.sun import sun as astral_sun, dawn as astral_dawn, dusk as astral_dusk
import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import constellations

matplotlib.use("agg")

print("Loading planetary data (Global)...")
load = Loader('data')
EPH = load('de421.bsp')
TS = load.timescale()
print("Skyfield data loaded.")


EARTH = "earth"
SUN = "sun"

BODIES = [
    ("Sun", SUN, "gold", 500),
    ("Mercury", "mercury", "pink", 40),
    ("Venus", "venus", "rosybrown", 60),
    ("Moon", "moon", "lightgrey", 300),
    ("Mars", "mars", "red", 60),
    ("Jupiter", "jupiter barycenter", "chocolate", 100),
    ("Saturn", "saturn barycenter", "khaki", 90),
    ("Uranus", "uranus barycenter", "lightsteelblue", 40),
    ("Neptune", "neptune barycenter", "royalblue", 30),
]

@lru_cache(maxsize=128)
def _get_or_compute_analemmas(lat, lon, tz, dark_mode):
    """
    Computes and returns the analemma paths for a given location.
    This function is cached to avoid re-computation for the same lat/lon/tz/dark_mode.
    """
    location = EPH[EARTH] + Topos(latitude_degrees=lat, longitude_degrees=lon)
    now = datetime.datetime.now(tz)
    fixed_offset = now.utcoffset()
    fixed_tz = datetime.timezone(fixed_offset) if fixed_offset else datetime.timezone.utc
    
    analemmas = []
    # Create a lightweight object to pass context to AnalemmaPath
    class AnalemmaContext:
        # This will be replaced by the actual Sky object later
        def __init__(self, dark_mode):
            self.COLOR_MAP = {
                "black": "white", "k": "w", "white": "black", "w": "k",
                "gray": "darkgray", "lightgrey": "dimgray", "blue": "cyan",
                "green": "lime", "gold": "gold", "pink": "pink",
                "rosybrown": "rosybrown", "chocolate": "chocolate", "khaki": "khaki",
                "lightsteelblue": "lightsteelblue", "royalblue": "royalblue",
            }
            self._dark_mode = dark_mode
            self._label_background_color = "#3a3a3a" if dark_mode else "white"

        def get_position(self, body, obs_datetime):
            return compute_position(location, TS, tz, body, obs_datetime)

    context = AnalemmaContext(dark_mode)

    for hour in range(24):
        # For analemma, use the `dark_mode` and `label_background_color` from the Sky object (context)
        path = AnalemmaPath(EPH[SUN], hour, context, fixed_tz, fmt=":", color="gray", linewidth=1, alpha=0.5, dark_mode=dark_mode, label_background_color=context._label_background_color)
        if path.is_visible:
            analemmas.append(path)
    return analemmas

@lru_cache(maxsize=256)
def _get_or_compute_astral_times(lat, lon, tz, date_str):
    """
    Computes and returns a dictionary of twilight times using the astral library.
    This function is cached to avoid re-computation.
    """
    try:
        loc = LocationInfo(latitude=lat, longitude=lon, timezone=tz)
        d = datetime.datetime.strptime(date_str, '%Y-%m-%d').date()
        
        s = astral_sun(loc.observer, date=d, tzinfo=loc.timezone)

        return {
            'astronomical_dawn': astral_dawn(loc.observer, date=d, depression=18, tzinfo=loc.timezone).strftime('%H:%M'),
            'nautical_dawn': astral_dawn(loc.observer, date=d, depression=12, tzinfo=loc.timezone).strftime('%H:%M'),
            'civil_dawn': s['dawn'].strftime('%H:%M'),
            'sunrise': s['sunrise'].strftime('%H:%M'),
            'solar_noon': s['noon'].strftime('%H:%M'),
            'sunset': s['sunset'].strftime('%H:%M'),
            'civil_dusk': s['dusk'].strftime('%H:%M'),
            'nautical_dusk': astral_dusk(loc.observer, date=d, depression=12, tzinfo=loc.timezone).strftime('%H:%M'),
            'astronomical_dusk': astral_dusk(loc.observer, date=d, depression=18, tzinfo=loc.timezone).strftime('%H:%M'),
        }
    except (ValueError, KeyError): # Astral can raise ValueError for polar nights/days or KeyError if an event doesn't occur
        return {k: "N/A" for k in ['astronomical_dawn', 'nautical_dawn', 'civil_dawn', 'sunrise', 'solar_noon', 'sunset', 'civil_dusk', 'nautical_dusk', 'astronomical_dusk']}


def compute_position(location, timescale, timezone_obj, body, obs_datetime):
    """Computes the position of a celestial body for a given location and time."""
    if obs_datetime.tzinfo is None:
        loc_time = obs_datetime.replace(tzinfo=timezone_obj)
    else:
        loc_time = obs_datetime

    obs_time = timescale.utc(loc_time)
    astrometric = location.at(obs_time).observe(body)
    alt, azi, _d = astrometric.apparent().altaz()
    
    r = 90 - alt.degrees
    theta = azi.radians
    return theta, r

class Sky:
    def __init__(self, latlong, tz, show_constellations=True, show_time=True, show_legend=True, show_analemma=True, constellation_list=None, planet_list=None, north_up=False, horizontal_flip=False, image_type="png", show_stats=True, dark_mode=False):
        self.lat, self.lon = latlong
        self._latlong = Topos(latitude_degrees=self.lat, longitude_degrees=self.lon)
        self._timezone = tz
        self._planets = None
        self._ts = None
        self._location = None
        self._winter_solstice = None
        self._summer_solstice = None
        self._analemmas = []
        self.sun_position = None
        self._constellations = []
        self._points = []
        self._show_constellations = show_constellations
        self._show_time = show_time
        self._show_legend = show_legend
        self._show_analemma = show_analemma
        self._north_up = north_up
        self._horizontal_flip = horizontal_flip
        self._image_type = image_type
        self._times = {}
        if constellation_list is None: self._constellation_names = constellations.DEFAULT_CONSTELLATIONS
        else: self._constellation_names = constellation_list
        self._planet_list = planet_list
        # Moon info
        self._moon_rise = "N/A"
        self._moon_set = "N/A"
        self._moon_phase_name = ""
        self._moon_illumination = 0
        self._show_stats = show_stats # Store new parameter
        self._dark_mode = dark_mode

        self.COLOR_MAP = {
            "black": "white",
            "k": "w",
            "white": "black",
            "w": "k",
            "gray": "darkgray",
            "lightgrey": "dimgray",
            "blue": "cyan",
            "green": "lime",
            "gold": "gold",
            "pink": "pink",
            "rosybrown": "rosybrown", 
            "chocolate": "chocolate", 
            "khaki": "khaki", 
            "lightsteelblue": "lightsteelblue", 
            "royalblue": "royalblue", 
        }

        if self._dark_mode:
            self._background_color = "#1a1a1a" # Very dark gray
            self._text_color = self.COLOR_MAP["black"]
            self._grid_color = "darkgray"
            self._tick_color = "darkgray"
            self._label_background_color = "#3a3a3a"
        else:
            self._background_color = "white"
            self._text_color = "black"
            self._grid_color = "lightgray"
            self._tick_color = "black"
            self._label_background_color = "white"

    def load(self):
        if self._planets is None:
            self._load_sky_data()
            self._run_initial_computations()

    def _load_sky_data(self):
        # EPH and TS are now loaded globally in this module
        self._planets = EPH
        self._ts = TS

    def _run_initial_computations(self):
        self._location = self._planets[EARTH] + self._latlong
        self._compute_solstice_paths()
        
        if self._show_analemma:
            self._analemmas = _get_or_compute_analemmas(self.lat, self.lon, self._timezone, self._dark_mode)

        self._load_points()
        if self._show_constellations:
            self._constellations = constellations.build_constellations(self, self._constellation_names)

    def _load_points(self):
        self._points.clear()
        for name, planet_label, color, size in BODIES:
            if self._planet_list is not None and name not in self._planet_list: continue
            self._points.append(Point(name, self._planets[planet_label], color, size, self))

    def _compute_solstice_paths(self):
        today = datetime.datetime.today()
        w_date = datetime.datetime(today.year, 12, 21)
        s_date = datetime.datetime(today.year, 6, 21)
        self._winter_solstice = BodyPath(self._planets[SUN], w_date, self, fmt="--", color="blue", linewidth=1, alpha=0.8, dark_mode=self._dark_mode)
        self._summer_solstice = BodyPath(self._planets[SUN], s_date, self, fmt="--", color="green", linewidth=1, alpha=0.8, dark_mode=self._dark_mode)

    def _compute_moon_times(self, when):
        """Calculates moon rise, set, and phase for the given date."""
        # Define search window for today (midnight to 23:59:59 local time)
        # 'when' is already timezone-aware at this point
        local_midnight = when.replace(hour=0, minute=0, second=0, microsecond=0)
        local_end_of_day = when.replace(hour=23, minute=59, second=59, microsecond=999999)

        start_search = self._ts.utc(local_midnight)
        end_search = self._ts.utc(local_end_of_day)

        f = almanac.risings_and_settings(self._planets, self._planets['moon'], self._latlong)
        times, events = almanac.find_discrete(start_search, end_search, f)
        
        moon_rises_today = []
        moon_sets_today = []
        for t, event in zip(times, events):
            local_time = t.astimezone(self._timezone)
            # Ensure event falls within the desired local day (midnight to 23:59:59)
            if local_midnight.date() == local_time.date():
                if event: # True for rising
                    moon_rises_today.append(local_time)
                else: # False for setting
                    moon_sets_today.append(local_time)

        # Sort and pick the first for the day
        if moon_rises_today:
            self._moon_rise = sorted(moon_rises_today)[0].strftime('%H:%M')
        else:
            self._moon_rise = "N/A"

        if moon_sets_today:
            self._moon_set = sorted(moon_sets_today)[0].strftime('%H:%M')
        else:
            self._moon_set = "N/A"

        # Moon Phase (remains the same)
        t = self._ts.utc(when)
        moon_phase_angle = almanac.moon_phase(self._planets, t).degrees
        self._moon_illumination = almanac.fraction_illuminated(self._planets, 'moon', t) * 100
        
        if moon_phase_angle < 7 or moon_phase_angle >= 353: self._moon_phase_name = "New Moon"
        elif 7 <= moon_phase_angle < 83: self._moon_phase_name = "Waxing Crescent"
        elif 83 <= moon_phase_angle < 97: self._moon_phase_name = "First Quarter"
        elif 97 <= moon_phase_angle < 173: self._moon_phase_name = "Waxing Gibbous"
        elif 173 <= moon_phase_angle < 187: self._moon_phase_name = "Full Moon"
        elif 187 <= moon_phase_angle < 263: self._moon_phase_name = "Waning Gibbous"
        elif 263 <= moon_phase_angle < 277: self._moon_phase_name = "Last Quarter"
        elif 277 <= moon_phase_angle < 353: self._moon_phase_name = "Waning Crescent"
        else: self._moon_phase_name = "N/A" # Should not happen


    @property
    def get_image_type(self): return self._image_type

    def get_position(self, body, obs_datetime):
        # Wrapper to call the standalone compute_position function
        return compute_position(self._location, self._ts, self._timezone, body, obs_datetime)


    def plot_sky(self, output=None, when=None):
        if when is None: when = datetime.datetime.now()
        
        # Get twilight times from the new cached astral function
        date_str = when.strftime('%Y-%m-%d')
        self._times = _get_or_compute_astral_times(self.lat, self.lon, self._timezone, date_str)
        
        # Get moon times
        self._compute_moon_times(when)

        visible = [np.linspace(0, 2 * np.pi, 200), [90.0 for _i in range(200)]]
        
        fig, ax = plt.subplots(1, 1, figsize=(6, 6.2), subplot_kw={"projection": "polar"})
        fig.set_facecolor(self._background_color) # Set figure background color
        ax.set_facecolor(self._background_color) # Set axes background color
        ax.set_axisbelow(True)
        ax.set_theta_direction(1 if self._horizontal_flip else -1)
        
        ax.plot(*visible, "-", color=self.COLOR_MAP.get("k", "k") if self._dark_mode else "k", linewidth=3, alpha=1.0)
        self._draw_objects(ax, when)

        # --- Add Text Information ---

        # Mandatory time/date on top center
        if self._show_time:
            fig.text(0.5, 0.99, when.strftime('%b %-d %Y, %H:%M %Z'), transform=fig.transFigure, fontsize=9,
                     verticalalignment='top', horizontalalignment='center', fontname='monospace', color=self._text_color)

        if self._show_stats:
            # Next Solar Event
            next_event_str = "Next Event: N/A"
            try:
                now_aware = when.replace(tzinfo=self._timezone) if when.tzinfo is None else when
                sr_str = self._times.get('sunrise')
                sn_str = self._times.get('solar_noon')
                ss_str = self._times.get('sunset')

                events_today = []
                if sr_str != "N/A": events_today.append(("Sunrise", datetime.datetime.strptime(f"{date_str} {sr_str}", '%Y-%m-%d %H:%M').astimezone(self._timezone)))
                if sn_str != "N/A": events_today.append(("Solar Noon", datetime.datetime.strptime(f"{date_str} {sn_str}", '%Y-%m-%d %H:%M').astimezone(self._timezone)))
                if ss_str != "N/A": events_today.append(("Sunset", datetime.datetime.strptime(f"{date_str} {ss_str}", '%Y-%m-%d %H:%M').astimezone(self._timezone)))

                next_event = None
                for name, event_time in sorted(events_today, key=lambda x: x[1]):
                    if event_time > now_aware:
                        next_event = (name, event_time)
                        break
                
                if next_event is None: # Must be tomorrow's sunrise
                    tomorrow_str = (when + datetime.timedelta(days=1)).strftime('%Y-%m-%d')
                    tmrw_times = _get_or_compute_astral_times(self.lat, self.lon, self._timezone, tomorrow_str)
                    sr_str_tmrw = tmrw_times.get('sunrise')
                    if sr_str_tmrw != "N/A":
                        sr_time_tmrw = datetime.datetime.strptime(f"{tomorrow_str} {sr_str_tmrw}", '%Y-%m-%d %H:%M').astimezone(self._timezone)
                        next_event = ("Sunrise", sr_time_tmrw)

                if next_event:
                    delta = next_event[1] - now_aware
                    hours, remainder = divmod(delta.total_seconds(), 3600)
                    minutes, _ = divmod(remainder, 60)
                    next_event_str = f"Time to {next_event[0]}: {int(hours)}h {int(minutes)}m"
            except (ValueError, TypeError):
                next_event_str = "Next Event: Error"


            # Twilight & Sun Times
            dawn_times = (
                f"Astro Dawn: {self._times.get('astronomical_dawn', 'N/A')}\n"
                f"Naut Dawn:  {self._times.get('nautical_dawn', 'N/A')}\n"
                f"Civil Dawn: {self._times.get('civil_dawn', 'N/A')}\n"
                f"Sunrise:    {self._times.get('sunrise', 'N/A')}"
            )
            dusk_times = (
                f"Sunset:      {self._times.get('sunset', 'N/A')}\n"
                f"Civil Dusk:  {self._times.get('civil_dusk', 'N/A')}\n"
                f"Naut Dusk:   {self._times.get('nautical_dusk', 'N/A')}\n"
                f"Astro Dusk:  {self._times.get('astronomical_dusk', 'N/A')}"
            )
            
            # Center Info (below current time)
            center_stats_text = (
                f"Solar Noon: {self._times.get('solar_noon', 'N/A')}\n"
                f"{next_event_str}"
            )

            fig.text(0.01, 0.99, dawn_times, transform=fig.transFigure, fontsize=7,
                     verticalalignment='top', horizontalalignment='left', fontname='monospace', color=self._text_color)
            fig.text(0.99, 0.99, dusk_times, transform=fig.transFigure, fontsize=7,
                     verticalalignment='top', horizontalalignment='right', fontname='monospace', color=self._text_color)
            fig.text(0.5, 0.97, center_stats_text, transform=fig.transFigure, fontsize=7, # Lowered y-position
                     verticalalignment='top', horizontalalignment='center', fontname='monospace', color=self._text_color)

            # Moon Info
            moon_events_text = []
            moon_events = []
            if self._moon_rise != "N/A":
                # Need a dummy date to parse time string for comparison
                dummy_date = datetime.datetime.now().date()
                moon_events.append((datetime.datetime.strptime(f"{dummy_date} {self._moon_rise}", '%Y-%m-%d %H:%M'), f"Moon Rise: {self._moon_rise}"))
            if self._moon_set != "N/A":
                dummy_date = datetime.datetime.now().date()
                moon_events.append((datetime.datetime.strptime(f"{dummy_date} {self._moon_set}", '%Y-%m-%d %H:%M'), f"Moon Set:  {self._moon_set}"))

            if moon_events:
                moon_events.sort(key=lambda x: x[0])
                for _, text in moon_events:
                    moon_events_text.append(text)
            else:
                moon_events_text.append("Moon Rise: N/A")
                moon_events_text.append("Moon Set:  N/A")

            moon_info = "\n".join(moon_events_text) + \
                        f"\nPhase: {self._moon_phase_name} ({self._moon_illumination:.1f}%)"
            fig.text(0.01, 0.1, moon_info, transform=fig.transFigure, fontsize=7,
                     verticalalignment='top', horizontalalignment='left', fontname='monospace', color=self._text_color)
        
        if self._show_legend:
            fig.legend(loc="lower right", bbox_transform=fig.transFigure, ncol=3, markerscale=0.6, columnspacing=1, mode=None, handletextpad=0.05, labelcolor=self._text_color, facecolor=self._label_background_color)
            
        ax.set_theta_zero_location("N" if self._north_up else "S", offset=0)
        ax.set_rmax(90)
        ax.set_rgrids(np.linspace(0, 90, 10), [f"{int(f)}˚" for f in np.linspace(90, 0, 10)], color=self._tick_color)
        ax.set_thetagrids(np.linspace(0, 360.0, 9), ["N", "NE", "E", "SE", "S", "SW", "W", "NW", "N"], color=self._tick_color)
        
        fig.tight_layout(rect=[0, 0.05, 1, 0.95]) # Adjust layout to prevent text overlap
        if output is None: plt.show()
        else: fig.savefig(output, format=self._image_type, bbox_inches='tight', pad_inches=0.05, facecolor=self._background_color)
        plt.close()

    def _draw_objects(self, ax, when):
        for analemma in self._analemmas: analemma.draw(ax)
        today_sunpath = BodyPath(self._planets[SUN], datetime.datetime.now(self._timezone).replace(hour=0, minute=0, second=0, microsecond=0), self, "-", color="k", linewidth=1, alpha=0.8)
        for sunpath in [self._winter_solstice, self._summer_solstice, today_sunpath]: sunpath.draw(ax)
        for point in self._points: point.draw(ax, when)
        for constellation in self._constellations: constellation.draw(ax, when)

class BodyPath(object):
    def __init__(self, body, day, sky, fmt, color, linewidth=1, alpha=0.8, dark_mode=False):
        self._body = body
        self._day = day
        self._sky = sky
        self.path = None
        self.fmt = fmt
        self.linewidth = linewidth
        self.alpha = alpha
        self.dark_mode = dark_mode
        self.color = sky.COLOR_MAP.get(color, color) if dark_mode else color
        self._compute_daily_path()

    def _compute_daily_path(self, delta=datetime.timedelta(minutes=20)):
        data = []
        if self._day.tzinfo is not None: self._day = self._day.replace(tzinfo=None)
        
        for interval in range(73): 
            now = self._day + delta * interval
            theta, r = self._sky.get_position(self._body, now)
            if theta is None or r > 90:
                data.append((np.nan, np.nan))
            else:
                data.append((theta, r))
        self.path = list(zip(*data))

    def draw(self, ax):
        if self.path:
            ax.plot(*self.path, self.fmt, color=self.color, linewidth=self.linewidth, alpha=self.alpha)

class AnalemmaPath(object):
    def __init__(self, body, hour, sky, fixed_tz, fmt, color, linewidth=1, alpha=0.8, dark_mode=False, label_background_color=None):
        self._body = body
        self._hour = hour
        self._sky = sky
        self._fixed_tz = fixed_tz
        self.path = None
        self.fmt = fmt
        self.linewidth = linewidth
        self.alpha = alpha
        self.is_visible = False
        self.color = sky.COLOR_MAP.get(color, color) if dark_mode else color
        self.label_background_color = sky._label_background_color if dark_mode else None # Use for text background
        self._compute_yearly_path()

    def _compute_yearly_path(self):
        data = []
        year = datetime.datetime.now().year
        start_date = datetime.datetime(year, 1, 1)
        
        for i in range(0, 366, 5): 
            d = start_date + datetime.timedelta(days=i)
            dt = datetime.datetime(d.year, d.month, d.day, self._hour, 0, 0, tzinfo=self._fixed_tz)
            theta, r = self._sky.get_position(self._body, dt)
            if r <= 90: 
                self.is_visible = True
                data.append((theta, r))
            else:
                data.append((np.nan, np.nan))

        if data:
            self.path = list(zip(*data))

    def draw(self, ax):
        if self.path:
            ax.plot(*self.path, self.fmt, color=self.color, linewidth=self.linewidth, alpha=self.alpha)
            clean_path = [p for p in zip(*self.path) if not np.isnan(p[1])]
            if len(clean_path) > 0:
                valid_thetas, valid_rs = zip(*clean_path)
                mid_idx = len(valid_thetas) // 2
                lbl_theta = valid_thetas[mid_idx]
                lbl_r = valid_rs[mid_idx]
                lbl_r = max(0, lbl_r - 3)
                
                bbox_props = dict(boxstyle="round,pad=0.1", fc=self.label_background_color, ec="none", alpha=0.6) if self.label_background_color else None
                
                ax.text(lbl_theta, lbl_r, f"{self._hour}", fontsize=6, color=self.color, ha='center', va='center', fontweight='bold', alpha=0.8, clip_on=True, bbox=bbox_props)

class Point(object):
    def __init__(self, label, body, color, size, sky):
        self._label = label
        self._body = body
        self._size = size
        self._sky = sky
        self._color = sky.COLOR_MAP.get(color, color) if sky._dark_mode else color

    def draw(self, ax, when):
        theta, r = self._sky.get_position(self._body, when)
        if theta is not None and r < 90:
            ax.scatter(theta, r, s=self._size, label=self._label, alpha=1.0, color=self._color, edgecolor="black", zorder=10)
