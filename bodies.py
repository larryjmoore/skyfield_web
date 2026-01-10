"""Collect data about where celestial bodies are."""

# This file is adapted from the ha_skyfield project:
# https://github.com/partofthething/ha_skyfield

import datetime
import math
import io
from functools import lru_cache
from typing import Any, Dict, List, Optional, Tuple, Union
from skyfield.api import Loader, Topos
from skyfield import almanac
from astral.location import LocationInfo
from astral.sun import sun as astral_sun, dawn as astral_dawn, dusk as astral_dusk
import matplotlib
from matplotlib.figure import Figure
from matplotlib.axes import Axes
import numpy as np
import constellations
import matplotlib.path as mpath
import matplotlib.transforms as mtransforms

matplotlib.use("agg")

class SkyData:
    """Encapsulates the skyfield data."""
    def __init__(self, data_path='data'):
        print("Loading planetary data...")
        self.load = Loader(data_path)
        self.eph = self.load('de421.bsp')
        self.ts = self.load.timescale()
        print("Skyfield data loaded.")

sky_data = SkyData()

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

@lru_cache(maxsize=64)
def calculate_analemma_paths_data(lat: float, lon: float, tz_offset_seconds: float) -> Dict[int, List[Tuple[float, float]]]:
    """
    Calculates the analemma path points for all 24 hours.
    Returns a dictionary mapping hour (int) to a list of (theta, r) tuples.
    This function is cached to avoid re-calculating for the same location.
    """
    try:
        from flask import has_request_context, g
        if has_request_context():
            g.analemma_status = "MISS"
    except ImportError:
        pass

    tz = datetime.timezone(datetime.timedelta(seconds=tz_offset_seconds))
    # We create a temporary calculator just for the math.
    calc = SkyCalculator((lat, lon), tz)
    
    results = {}
    
    year = datetime.datetime.now().year
    start_date = datetime.datetime(year, 1, 1)
    
    # Check every 5 days
    days = [start_date + datetime.timedelta(days=i) for i in range(0, 366, 5)]
    
    for hour in range(24):
        data = []
        has_visible_points = False
        for d in days:
            # Construct time with fixed offset
            dt = datetime.datetime(d.year, d.month, d.day, hour, 0, 0, tzinfo=tz)
            
            # Using calc.compute_position directly
            theta, r = calc.compute_position(sky_data.eph[SUN], dt)
            
            if r <= 90:
                data.append((theta, r))
                has_visible_points = True
            else:
                data.append((np.nan, np.nan))
        
        # Only store if there are visible points? No, store all so we can cache "empty" paths too (and just not draw them)
        # But to match logic, we just return the data. Logic to filter is in AnalemmaPath/get_analemmas.
        results[hour] = data
        
    return results

class SkyCalculator:
    """Handles astronomical calculations."""
    def __init__(self, latlong: Tuple[float, float], tz: datetime.tzinfo):
        self.lat, self.lon = latlong
        self.topos = Topos(latitude_degrees=self.lat, longitude_degrees=self.lon)
        self.location = sky_data.eph[EARTH] + self.topos
        self.timezone = tz

    def compute_position(self, body: Any, obs_datetime: datetime.datetime) -> Tuple[float, float]:
        """Computes the position of a celestial body."""
        if obs_datetime.tzinfo is None:
            loc_time = obs_datetime.replace(tzinfo=self.timezone)
        else:
            loc_time = obs_datetime
        
        obs_time = sky_data.ts.utc(loc_time)
        astrometric = self.location.at(obs_time).observe(body)
        alt, azi, _d = astrometric.apparent().altaz()
        
        return azi.radians, 90 - alt.degrees

    def get_analemmas(self, dark_mode: bool) -> List['AnalemmaPath']:
        """Computes and returns the analemma paths for a given location."""
        now = datetime.datetime.now(self.timezone)
        fixed_offset = now.utcoffset()
        fixed_tz = datetime.timezone(fixed_offset) if fixed_offset else datetime.timezone.utc
        
        tz_offset_seconds = fixed_offset.total_seconds() if fixed_offset else 0.0
        all_paths_data = calculate_analemma_paths_data(self.lat, self.lon, tz_offset_seconds)
        
        class AnalemmaContext:
            def __init__(self, calculator: 'SkyCalculator', dark_mode: bool):
                self._calculator = calculator
                self.COLOR_MAP = {
                    "black": "white", "k": "w", "white": "black", "w": "k",
                    "gray": "darkgray", "lightgrey": "white", "blue": "cyan",
                    "green": "lime", "gold": "gold", "pink": "pink",
                    "rosybrown": "rosybrown", "chocolate": "chocolate", "khaki": "khaki",
                    "lightsteelblue": "lightsteelblue", "royalblue": "royalblue",
                    "orange": "orange",
                    "dimgray": "white",
                }
                self._dark_mode = dark_mode
                self._label_background_color = "#3a3a3a" if dark_mode else "white"
            
            def get_position(self, body: Any, obs_datetime: datetime.datetime) -> Tuple[float, float]:
                return self._calculator.compute_position(body, obs_datetime)

        context = AnalemmaContext(self, dark_mode)
        analemmas = []
        for hour in range(24):
            path = AnalemmaPath(sky_data.eph[SUN], hour, context, fixed_tz, fmt=":", color="gray", linewidth=1, alpha=0.5, dark_mode=dark_mode, label_background_color=context._label_background_color, path_data=all_paths_data.get(hour))
            if path.is_visible:
                analemmas.append(path)
        return analemmas

    @lru_cache(maxsize=256)
    def get_astral_times(self, date_str: str) -> Dict[str, str]:
        """Computes and returns a dictionary of twilight times using the astral library."""
        try:
            loc = LocationInfo(latitude=self.lat, longitude=self.lon, timezone=self.timezone)
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
        except (ValueError, KeyError):
            return {k: "N/A" for k in ['astronomical_dawn', 'nautical_dawn', 'civil_dawn', 'sunrise', 'solar_noon', 'sunset', 'civil_dusk', 'nautical_dusk', 'astronomical_dusk']}

    def compute_moon_times(self, when: datetime.datetime) -> Tuple[str, str, str, float, Optional[Dict[str, Any]]]:
        """Calculates moon rise, set, phase, and next event for the given date."""
        start_of_day = when.replace(hour=0, minute=0, second=0, microsecond=0)
        start_search = sky_data.ts.utc(start_of_day)
        end_search = sky_data.ts.utc(start_of_day + datetime.timedelta(days=2))

        f = almanac.risings_and_settings(sky_data.eph, sky_data.eph['moon'], self.topos)
        times, events = almanac.find_discrete(start_search, end_search, f)
        
        all_events = sorted([{'time': t.astimezone(self.timezone), 'is_rise': event} for t, event in zip(times, events)], key=lambda x: x['time'])
        
        moon_rises_today = [e['time'] for e in all_events if e['is_rise'] and e['time'].date() == when.date()]
        moon_sets_today = [e['time'] for e in all_events if not e['is_rise'] and e['time'].date() == when.date()]
        
        moon_rise_str = moon_rises_today[0].strftime('%H:%M') if moon_rises_today else "N/A"
        moon_set_str = moon_sets_today[0].strftime('%H:%M') if moon_sets_today else "N/A"

        next_moon_event = next((event for event in all_events if event['time'] > when), None)

        t = sky_data.ts.utc(when)
        moon_phase_angle = almanac.moon_phase(sky_data.eph, t).degrees
        moon_illumination = almanac.fraction_illuminated(sky_data.eph, 'moon', t) * 100
        
        if moon_phase_angle < 7 or moon_phase_angle >= 353: moon_phase_name = "New Moon"
        elif 7 <= moon_phase_angle < 83: moon_phase_name = "Waxing Crescent"
        elif 83 <= moon_phase_angle < 97: moon_phase_name = "First Quarter"
        elif 97 <= moon_phase_angle < 173: moon_phase_name = "Waxing Gibbous"
        elif 173 <= moon_phase_angle < 187: moon_phase_name = "Full Moon"
        elif 187 <= moon_phase_angle < 263: moon_phase_name = "Waning Gibbous"
        elif 263 <= moon_phase_angle < 277: moon_phase_name = "Last Quarter"
        elif 277 <= moon_phase_angle < 353: moon_phase_name = "Waning Crescent"
        else: moon_phase_name = "N/A"
        
        return moon_rise_str, moon_set_str, moon_phase_name, moon_illumination, next_moon_event

class SkyPlotter:
    """Handles plotting the sky chart."""
    def __init__(self, calculator: SkyCalculator, **kwargs: Any):
        self.calculator = calculator
        self.config = kwargs
        self.dark_mode = self.config.get('dark_mode', False)
        self.COLOR_MAP = {
            "black": "white", "k": "w", "white": "black", "w": "k", "gray": "darkgray",
            "lightgrey": "white", "blue": "cyan", "green": "lime", "gold": "gold", "pink": "pink",
            "rosybrown": "rosybrown", "chocolate": "chocolate", "khaki": "khaki", 
            "lightsteelblue": "lightsteelblue", "royalblue": "royalblue",
            "orange": "orange",
            "dimgray": "white",
        }
        self.background_color = "#1a1a1a" if self.dark_mode else "white"
        self.text_color = self.COLOR_MAP["black"] if self.dark_mode else "black"
        self.grid_color = "darkgray" if self.dark_mode else "lightgray"
        self.tick_color = "darkgray" if self.dark_mode else "black"
        self.label_background_color = "#3a3a3a" if self.dark_mode else "white"

    def plot_sky(self, output: io.BytesIO, when: datetime.datetime) -> None:
        fig = Figure(figsize=(6, 6.2))
        ax = fig.add_subplot(1, 1, 1, projection="polar")
        fig.set_facecolor(self.background_color)
        ax.set_facecolor(self.background_color)
        ax.set_axisbelow(True)
        ax.set_theta_direction(1 if self.config.get('horizontal_flip', False) else -1)
        
        visible = [np.linspace(0, 2 * np.pi, 200), [90.0 for _ in range(200)]]
        ax.plot(*visible, "-", color=self.COLOR_MAP.get("k", "k") if self.dark_mode else "k", linewidth=3, alpha=1.0)
        
        self._draw_objects(ax, when)
        self._add_text_info(fig, ax, when)
        
        ax.set_theta_zero_location("N" if self.config.get('north_up', False) else "S", offset=0)
        ax.set_rmax(90)
        ax.set_rgrids(np.linspace(0, 90, 10), [f"{int(f)}˚" for f in np.linspace(90, 0, 10)], color=self.tick_color)
        ax.set_thetagrids(np.linspace(0, 360.0, 9), ["N", "NE", "E", "SE", "S", "SW", "W", "NW", "N"], color=self.tick_color)
        
        fig.tight_layout(rect=[0, 0.05, 1, 0.95])
        fig.savefig(output, format=self.config.get('image_type', 'png'), bbox_inches='tight', pad_inches=0.05, facecolor=self.background_color)

    def _draw_objects(self, ax: Axes, when: datetime.datetime) -> None:
        # Analemmas
        if self.config.get('show_analemma', False):
            for analemma in self.calculator.get_analemmas(self.dark_mode):
                analemma.draw(ax)

        # Sun paths
        today_sunpath = BodyPath(sky_data.eph[SUN], when.replace(hour=0, minute=0, second=0, microsecond=0), self, "-", color="orange", linewidth=1, alpha=0.8, dark_mode=self.dark_mode)
        winter_solstice = BodyPath(sky_data.eph[SUN], datetime.datetime(when.year, 12, 21), self, fmt="-", color="gray", linewidth=1, alpha=0.8, dark_mode=self.dark_mode)
        summer_solstice = BodyPath(sky_data.eph[SUN], datetime.datetime(when.year, 6, 21), self, fmt="-", color="gray", linewidth=1, alpha=0.8, dark_mode=self.dark_mode)
        
        # Moon path
        moon_path = BodyPath(sky_data.eph['moon'], when, self, "--", color="dimgray", linewidth=1, alpha=0.8, dark_mode=self.dark_mode)

        for path in [winter_solstice, summer_solstice, today_sunpath, moon_path]:
            path.draw(ax)

        # Planets
        planet_list = self.config.get('planet_list', None)
        for name, planet_label, color, size in BODIES:
            if planet_list is not None and name not in planet_list:
                continue
            Point(name, sky_data.eph[planet_label], color, size, self).draw(ax, when)

        # Constellations
        if self.config.get('show_constellations', False):
            constellation_list = self.config.get('constellation_list', constellations.DEFAULT_CONSTELLATIONS)
            for constellation in constellations.build_constellations(self, constellation_list):
                constellation.draw(ax, when)

    def _add_text_info(self, fig: Figure, ax: Axes, when: datetime.datetime) -> None:
        if self.config.get('show_time', True):
            fig.text(0.5, 0.99, when.strftime('%b %-d %Y, %H:%M %Z'), transform=fig.transFigure, fontsize=9, verticalalignment='top', horizontalalignment='center', fontname='monospace', color=self.text_color)

        if self.config.get('show_stats', True):
            date_str = when.strftime('%Y-%m-%d')
            times = self.calculator.get_astral_times(date_str)
            
            # Next Solar Event
            next_event_str = "Next Event: N/A"
            try:
                now_aware = when.replace(tzinfo=self.calculator.timezone) if when.tzinfo is None else when
                sr_str = times.get('sunrise')
                sn_str = times.get('solar_noon')
                ss_str = times.get('sunset')

                events_today = []
                if sr_str != "N/A": events_today.append(("Sunrise", datetime.datetime.strptime(f"{date_str} {sr_str}", '%Y-%m-%d %H:%M').astimezone(self.calculator.timezone)))
                if sn_str != "N/A": events_today.append(("Solar Noon", datetime.datetime.strptime(f"{date_str} {sn_str}", '%Y-%m-%d %H:%M').astimezone(self.calculator.timezone)))
                if ss_str != "N/A": events_today.append(("Sunset", datetime.datetime.strptime(f"{date_str} {ss_str}", '%Y-%m-%d %H:%M').astimezone(self.calculator.timezone)))

                next_event = next(((name, event_time) for name, event_time in sorted(events_today, key=lambda x: x[1]) if event_time > now_aware), None)

                if next_event is None: # Must be tomorrow's sunrise
                    tomorrow_str = (when + datetime.timedelta(days=1)).strftime('%Y-%m-%d')
                    tmrw_times = self.calculator.get_astral_times(tomorrow_str)
                    sr_str_tmrw = tmrw_times.get('sunrise')
                    if sr_str_tmrw != "N/A":
                        sr_time_tmrw = datetime.datetime.strptime(f"{tomorrow_str} {sr_str_tmrw}", '%Y-%m-%d %H:%M').astimezone(self.calculator.timezone)
                        next_event = ("Sunrise", sr_time_tmrw)

                if next_event:
                    delta = next_event[1] - now_aware
                    hours, remainder = divmod(delta.total_seconds(), 3600)
                    minutes, _ = divmod(remainder, 60)
                    event_name = next_event[0]
                    if next_event[1].date() != when.date():
                        event_name = f"Next {event_name}"
                    next_event_str = f"Time to {event_name}: {int(hours)}h {int(minutes)}m"
            except (ValueError, TypeError):
                next_event_str = "Next Event: Error"

            # Twilight & Sun Times
            dawn_times = (
                f"Astro Dawn: {times.get('astronomical_dawn', 'N/A')}\n"
                f"Naut Dawn:  {times.get('nautical_dawn', 'N/A')}\n"
                f"Civil Dawn: {times.get('civil_dawn', 'N/A')}\n"
                f"Sunrise:    {times.get('sunrise', 'N/A')}"
            )
            dusk_times = (
                f"Sunset:      {times.get('sunset', 'N/A')}\n"
                f"Civil Dusk:  {times.get('civil_dusk', 'N/A')}\n"
                f"Naut Dusk:   {times.get('nautical_dusk', 'N/A')}\n"
                f"Astro Dusk:  {times.get('astronomical_dusk', 'N/A')}"
            )
            
            center_stats_text = (
                f"Solar Noon: {times.get('solar_noon', 'N/A')}\n"
                f"{next_event_str}"
            )

            fig.text(0.01, 0.99, dawn_times, transform=fig.transFigure, fontsize=7, verticalalignment='top', horizontalalignment='left', fontname='monospace', color=self.text_color)
            fig.text(0.99, 0.99, dusk_times, transform=fig.transFigure, fontsize=7, verticalalignment='top', horizontalalignment='right', fontname='monospace', color=self.text_color)
            fig.text(0.5, 0.97, center_stats_text, transform=fig.transFigure, fontsize=7, verticalalignment='top', horizontalalignment='center', fontname='monospace', color=self.text_color)

            # Moon Info
            moon_rise, moon_set, moon_phase_name, moon_illumination, next_moon_event = self.calculator.compute_moon_times(when)
            moon_events = []
            if moon_rise != "N/A":
                moon_events.append((datetime.datetime.strptime(moon_rise, '%H:%M').time(), f"Moon Rise: {moon_rise}"))
            if moon_set != "N/A":
                moon_events.append((datetime.datetime.strptime(moon_set, '%H:%M').time(), f"Moon Set:  {moon_set}"))

            moon_events.sort(key=lambda x: x[0])
            moon_events_text = [text for time, text in moon_events]

            moon_info = "\n".join(moon_events_text) + \
                        f"\nPhase: {moon_phase_name} ({moon_illumination:.1f}%)"

            if next_moon_event:
                delta = next_moon_event['time'] - when
                hours, remainder = divmod(delta.total_seconds(), 3600)
                minutes, _ = divmod(remainder, 60)
                event_type_name = "Rise" if next_moon_event['is_rise'] else "Set"
                prefix = "Next " if next_moon_event['time'].date() != when.date() else ""
                moon_info += f"\nTime to {prefix}Moon {event_type_name}: {int(hours)}h {int(minutes)}m"
            
            fig.text(0.01, 0.1, moon_info, transform=fig.transFigure, fontsize=7, verticalalignment='top', horizontalalignment='left', fontname='monospace', color=self.text_color)

        if self.config.get('show_legend', True):
            handles, labels = ax.get_legend_handles_labels()
            if handles:
                fig.legend(loc="lower right", bbox_transform=fig.transFigure, ncol=3, markerscale=0.6, columnspacing=1, mode=None, handletextpad=0.05, labelcolor=self.text_color, facecolor=self.label_background_color)

class Sky:
    """Main class to interact with the sky chart generation."""
    def __init__(self, latlong: Tuple[float, float], tz: datetime.tzinfo, **kwargs: Any):
        self.calculator = SkyCalculator(latlong, tz)
        self.plotter = SkyPlotter(self.calculator, **kwargs)

    def load(self) -> None:
        # Data is loaded globally now, so this is a no-op
        pass

    def plot_sky(self, output: io.BytesIO, when: datetime.datetime) -> None:
        self.plotter.plot_sky(output, when)

class BodyPath:
    # ... (BodyPath, AnalemmaPath, Point classes remain mostly the same, but adapt to the new structure) ...
    def __init__(self, body: Any, day: datetime.datetime, plotter: SkyPlotter, fmt: str, color: str, linewidth: int = 1, alpha: float = 0.8, dark_mode: bool = False):
        self._body = body
        self._day = day
        self._plotter = plotter
        self.path: Optional[Tuple[List[float], List[float]]] = None
        self.fmt = fmt
        self.linewidth = linewidth
        self.alpha = alpha
        self.dark_mode = dark_mode
        self.color = plotter.COLOR_MAP.get(color, color) if dark_mode else color
        self._compute_daily_path()

    def _compute_daily_path(self, delta: datetime.timedelta = datetime.timedelta(minutes=20)) -> None:
        data = []
        if self._day.tzinfo is not None:
            self._day = self._day.replace(tzinfo=None)
        
        prev_theta = None
        prev_r = None

        for interval in range(73): 
            now = self._day + delta * interval
            theta, r = self._plotter.calculator.compute_position(self._body, now)
            
            if theta is None:
                data.append((np.nan, np.nan))
                prev_theta, prev_r = None, None
                continue

            # Rising event: prev_r > 90 (hidden) and r <= 90 (visible)
            if prev_r is not None and prev_r > 90 and r <= 90:
                f = (90 - prev_r) / (r - prev_r)
                diff_theta = theta - prev_theta
                if diff_theta > np.pi: diff_theta -= 2*np.pi
                elif diff_theta < -np.pi: diff_theta += 2*np.pi
                cross_theta = prev_theta + diff_theta * f
                data.append((cross_theta, 90.0))
            
            # Setting event: prev_r <= 90 (visible) and r > 90 (hidden)
            if prev_r is not None and prev_r <= 90 and r > 90:
                f = (90 - prev_r) / (r - prev_r)
                diff_theta = theta - prev_theta
                if diff_theta > np.pi: diff_theta -= 2*np.pi
                elif diff_theta < -np.pi: diff_theta += 2*np.pi
                cross_theta = prev_theta + diff_theta * f
                data.append((cross_theta, 90.0))

            if r > 90:
                data.append((np.nan, np.nan))
            else:
                data.append((theta, r))
                
            prev_theta = theta
            prev_r = r

        self.path = list(zip(*data)) # type: ignore

    def draw(self, ax: Axes) -> None:
        if self.path:
            ax.plot(*self.path, self.fmt, color=self.color, linewidth=self.linewidth, alpha=self.alpha)
            
class AnalemmaPath:
    def __init__(self, body: Any, hour: int, context: Any, fixed_tz: datetime.tzinfo, fmt: str, color: str, linewidth: int = 1, alpha: float = 0.8, dark_mode: bool = False, label_background_color: Optional[str] = None, path_data: Optional[List[Tuple[float, float]]] = None):
        self._body = body
        self._hour = hour
        self._context = context
        self._fixed_tz = fixed_tz
        self.path: Optional[Tuple[List[float], List[float]]] = None
        self.fmt = fmt
        self.linewidth = linewidth
        self.alpha = alpha
        self.is_visible = False
        self.color = context.COLOR_MAP.get(color, color) if dark_mode else color
        self.label_background_color = context._label_background_color if dark_mode else None
        
        if path_data:
            self.path = list(zip(*path_data)) # type: ignore
            # Check for visibility
            if self.path and len(self.path) > 1:
                rs = self.path[1]
                # Check if any r is not nan and <= 90
                # Note: The cached data sets invisible points to (nan, nan), so just checking for not-nan is usually enough, 
                # but r <= 90 is the strict condition.
                if any((not np.isnan(r) and r <= 90) for r in rs):
                    self.is_visible = True
        else:
            self._compute_yearly_path()

    def _compute_yearly_path(self) -> None:
        data = []
        year = datetime.datetime.now().year
        start_date = datetime.datetime(year, 1, 1)
        
        for i in range(0, 366, 5): 
            d = start_date + datetime.timedelta(days=i)
            dt = datetime.datetime(d.year, d.month, d.day, self._hour, 0, 0, tzinfo=self._fixed_tz)
            theta, r = self._context.get_position(self._body, dt)
            if r <= 90: 
                self.is_visible = True
                data.append((theta, r))
            else:
                data.append((np.nan, np.nan))

        if data:
            self.path = list(zip(*data)) # type: ignore
            
    def draw(self, ax: Axes) -> None:
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

def moon_bright_limb_rotation_deg(observer, ts, eph, when, lat_deg, lon_deg):
    """
    Moon bright-limb rotation angle in degrees, matching MoonCalc / SunCalc.

    rotation = PA_bright_limb - parallactic_angle

    Angle is CCW from local zenith toward celestial east.
    """

    t = ts.utc(when)

    # Apparent topocentric positions
    moon = observer.at(t).observe(eph['moon']).apparent()
    sun  = observer.at(t).observe(eph['sun']).apparent()

    # Equatorial coordinates
    ra_m, dec_m, _ = moon.radec()
    ra_s, dec_s, _ = sun.radec()

    ra_m = ra_m.radians
    dec_m = dec_m.radians
    ra_s = ra_s.radians
    dec_s = dec_s.radians

    # ----------------------------------
    # 1) Bright limb position angle (PA)
    # ----------------------------------
    d_ra = ra_s - ra_m

    y = np.sin(d_ra) * np.cos(dec_s)
    x = (np.cos(dec_m) * np.sin(dec_s)
         - np.sin(dec_m) * np.cos(dec_s) * np.cos(d_ra))

    pa = np.arctan2(y, x)   # radians, CCW from celestial north

    # ----------------------------------
    # 2) Parallactic angle q
    # ----------------------------------
    gast_hours = t.gast
    lst_hours = (gast_hours + lon_deg / 15.0) % 24.0

    ra_m_hours = ra_m * 12.0 / np.pi
    H_hours = lst_hours - ra_m_hours
    H = np.radians(H_hours * 15.0)

    lat = np.radians(lat_deg)
    dec = dec_m

    q = np.arctan2(
        np.sin(H),
        np.tan(lat) * np.cos(dec) - np.sin(dec) * np.cos(H)
    )

    # ----------------------------------
    # 3) Zenith angle of bright limb
    # ----------------------------------
    rotation_deg = np.degrees(pa - q) + 90

    return rotation_deg

class Point:
    def __init__(self, label: str, body: Any, color: str, size: int, plotter: SkyPlotter):
        self._label = label
        self._body = body
        self._size = size
        self._plotter = plotter
        self._color = plotter.COLOR_MAP.get(color, color) if plotter.dark_mode else color

    def draw(self, ax: Axes, when: datetime.datetime) -> None:
        theta, r = self._plotter.calculator.compute_position(self._body, when)
        
        if theta is None or r >= 90:
            return

        if self._label == "Moon":
            # 1. Calculate Geometry for Rotation
            rotation = moon_bright_limb_rotation_deg(
                observer=self._plotter.calculator.location,
                ts=sky_data.ts,
                eph=sky_data.eph,
                when=when,
                lat_deg=self._plotter.calculator.lat,
                lon_deg=self._plotter.calculator.lon,
            )
            
            # 2. Calculate Phase Fraction
            t = sky_data.ts.utc(when)
            fraction = almanac.fraction_illuminated(sky_data.eph, 'moon', t)
            
            # 3. Create Custom Path for Lit Portion
            # w = semi-minor axis of the terminator ellipse (-1 to 1)
            # w = 1 means Full, w = -1 means New (dark), w = 0 means Quarter
            # Formula: w = 1 - 2 * fraction ? 
            # If fraction=1 (Full), w=-1. Curve is Left Semicircle. Total = Right + Left = Full. Correct.
            # If fraction=0 (New), w=1. Curve is Right Semicircle. Total = Right - Right = Empty. Correct.
            w = 1 - 2 * fraction
            
            # Generate vertices
            N = 50
            # Right semicircle (Sunward side): t from -pi/2 to pi/2
            t_right = np.linspace(-np.pi/2, np.pi/2, N)
            x_right = 0.5 * np.cos(t_right) # Scale by 0.5 to match standard marker radius
            y_right = 0.5 * np.sin(t_right)
            
            # Terminator ellipse: t from pi/2 to -pi/2
            t_left = np.linspace(np.pi/2, -np.pi/2, N)
            y_left = 0.5 * np.sin(t_left)
            x_left = 0.5 * w * np.cos(t_left)
            
            verts = np.vstack((
                np.column_stack((x_right, y_right)),
                np.column_stack((x_left, y_left)),
                [[0, -0.5]] 
            ))
            
            path_lit = mpath.Path(verts)
            
            # Rotate path to point towards Sun
            trans = mtransforms.Affine2D().rotate_deg(rotation)
            path_lit_rotated = path_lit.transformed(trans)
            
            # 4. Draw
            # Draw Outline (Full Moon shape background)
            unlit_color = '#222222' if self._plotter.dark_mode else 'gray'
            ax.scatter(theta, r, s=self._size, marker='o', 
                       edgecolor=self._color if self._plotter.dark_mode else 'black', 
                       facecolor=unlit_color, linewidth=0.5, zorder=10)
            
            # Draw Lit Part
            ax.scatter(theta, r, s=self._size, marker=path_lit_rotated,
                       edgecolor='none', facecolor=self._color, zorder=10, label=self._label)
        else:
            ax.scatter(theta, r, s=self._size, label=self._label, alpha=1.0, color=self._color, edgecolor="black", zorder=10)
