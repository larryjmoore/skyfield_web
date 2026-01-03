"""Collect data about where celestial bodies are."""

# This file is adapted from the ha_skyfield project:
# https://github.com/partofthething/ha_skyfield

import datetime
import math
from functools import lru_cache
from pytz import timezone
from skyfield.api import Loader, Topos
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
def _get_or_compute_analemmas(lat, lon, tz_name):
    """
    Computes and returns the analemma paths for a given location.
    This function is cached to avoid re-computation for the same lat/lon/tz.
    """
    location = EPH[EARTH] + Topos(latitude_degrees=lat, longitude_degrees=lon)
    timezone_obj = timezone(tz_name)
    now = datetime.datetime.now(timezone_obj)
    fixed_offset = now.utcoffset()
    fixed_tz = datetime.timezone(fixed_offset) if fixed_offset else datetime.timezone.utc
    
    analemmas = []
    # Create a lightweight object to pass context to AnalemmaPath
    class AnalemmaContext:
        def get_position(self, body, obs_datetime):
            return compute_position(location, TS, timezone_obj, body, obs_datetime)

    context = AnalemmaContext()

    for hour in range(24):
        path = AnalemmaPath(EPH[SUN], hour, context, fixed_tz, fmt=":", color="gray", linewidth=1, alpha=0.5)
        if path.is_visible:
            analemmas.append(path)
    return analemmas

def compute_position(location, timescale, timezone_obj, body, obs_datetime):
    """Computes the position of a celestial body for a given location and time."""
    if obs_datetime.tzinfo is None:
        loc_time = timezone_obj.localize(obs_datetime)
    else:
        loc_time = obs_datetime

    obs_time = timescale.utc(loc_time)
    astrometric = location.at(obs_time).observe(body)
    alt, azi, _d = astrometric.apparent().altaz()
    
    r = 90 - alt.degrees
    theta = azi.radians
    return theta, r

class Sky:
    def __init__(self, latlong, tzname, show_constellations=True, show_time=True, show_legend=True, show_analemma=True, constellation_list=None, planet_list=None, north_up=False, horizontal_flip=False, image_type="png"):
        self.lat, self.lon = latlong
        self._latlong = Topos(latitude_degrees=self.lat, longitude_degrees=self.lon)
        self._timezone = timezone(tzname)
        self._tzname = tzname
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
        if constellation_list is None: self._constellation_names = constellations.DEFAULT_CONSTELLATIONS
        else: self._constellation_names = constellation_list
        self._planet_list = planet_list

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
            self._analemmas = _get_or_compute_analemmas(self.lat, self.lon, self._tzname)

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
        self._winter_solstice = BodyPath(self._planets[SUN], w_date, self, fmt="--", color="blue", linewidth=1, alpha=0.8)
        self._summer_solstice = BodyPath(self._planets[SUN], s_date, self, fmt="--", color="green", linewidth=1, alpha=0.8)

    @property
    def get_image_type(self): return self._image_type

    def get_position(self, body, obs_datetime):
        # Wrapper to call the standalone compute_position function
        return compute_position(self._location, self._ts, self._timezone, body, obs_datetime)


    def plot_sky(self, output=None, when=None):
        if when is None: when = datetime.datetime.now()
        visible = [np.linspace(0, 2 * np.pi, 200), [90.0 for _i in range(200)]]
        
        fig, ax = plt.subplots(1, 1, figsize=(6, 6.2), subplot_kw={"projection": "polar"})
        ax.set_axisbelow(True)
        ax.set_theta_direction(1 if self._horizontal_flip else -1)
        
        ax.plot(*visible, "-", color="k", linewidth=3, alpha=1.0)
        self._draw_objects(ax, when)
        
        if self._show_time:
            ax.annotate(str(when), xy=(0.09, 0.07), xycoords="figure fraction", horizontalalignment="left", verticalalignment="top", fontsize=8)
            ax.annotate(f"Lat: {self._latlong.latitude.degrees:.2f}, Lon: {self._latlong.longitude.degrees:.2f}", xy=(0.09, 0.05), xycoords="figure fraction", horizontalalignment="left", verticalalignment="top", fontsize=8)
        if self._show_legend:
            fig.legend(loc="lower right", bbox_transform=fig.transFigure, ncol=3, markerscale=0.6, columnspacing=1, mode=None, handletextpad=0.05)
            
        ax.set_theta_zero_location("N" if self._north_up else "S", offset=0)
        ax.set_rmax(90)
        ax.set_rgrids(np.linspace(0, 90, 10), [f"{int(f)}˚" for f in np.linspace(90, 0, 10)])
        ax.set_thetagrids(np.linspace(0, 360.0, 9), ["N", "NE", "E", "SE", "S", "SW", "W", "NW", "N"])
        
        fig.tight_layout()
        if output is None: plt.show()
        else: fig.savefig(output, format=self._image_type, bbox_inches='tight', pad_inches=0.05)
        plt.close()

    def _draw_objects(self, ax, when):
        for analemma in self._analemmas: analemma.draw(ax)
        today_sunpath = BodyPath(self._planets[SUN], datetime.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0), self, "-", color="k", linewidth=1, alpha=0.8)
        for sunpath in [self._winter_solstice, self._summer_solstice, today_sunpath]: sunpath.draw(ax)
        for point in self._points: point.draw(ax, when)
        for constellation in self._constellations: constellation.draw(ax, when)

class BodyPath(object):
    def __init__(self, body, day, sky, fmt, color, linewidth=1, alpha=0.8):
        self._body = body
        self._day = day
        self._sky = sky
        self.path = None
        self.fmt = fmt
        self.color = color
        self.linewidth = linewidth
        self.alpha = alpha
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
    def __init__(self, body, hour, sky, fixed_tz, fmt, color, linewidth=1, alpha=0.8):
        self._body = body
        self._hour = hour
        self._sky = sky
        self._fixed_tz = fixed_tz
        self.path = None
        self.fmt = fmt
        self.color = color
        self.linewidth = linewidth
        self.alpha = alpha
        self.is_visible = False
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
                ax.text(lbl_theta, lbl_r, f"{self._hour}", fontsize=6, color=self.color, ha='center', va='center', fontweight='bold', alpha=0.8, clip_on=True)

class Point(object):
    def __init__(self, label, body, color, size, sky):
        self._label = label
        self._body = body
        self._size = size
        self._color = color
        self._sky = sky

    def draw(self, ax, when):
        theta, r = self._sky.get_position(self._body, when)
        if theta is not None and r < 90:
            ax.scatter(theta, r, s=self._size, label=self._label, alpha=1.0, color=self._color, edgecolor="black", zorder=10)
