"""Handle plotting constellations on the sky field."""

# This file is adapted from the ha_skyfield project:
# https://github.com/partofthething/ha_skyfield

import os
import math
import numpy as np
from skyfield.api import Star

THIS_DIR = os.path.split(__file__)[0]
DATA_FILE = os.path.join(THIS_DIR, "constellations_by_RA_Dec.dat")

ZODIAC = [
    "Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo", "Libra",
    "Scorpius", "Sagittarius", "Capricornus", "Aquarius", "Pisces",
]
DEFAULT_CONSTELLATIONS = ZODIAC + ["Cassiopeia", "Orion", "Pegasus", "UrsaMajor"]

def _read_data():
    """Reads constellation data from the data file."""
    constellations = {}
    with open(DATA_FILE) as datafile:
        for line in datafile:
            line = line.strip()
            if line.startswith("#") or not line:
                continue
            name, ra1, dec1, ra2, dec2 = line.split()
            constellation_data = constellations.get(name, [])
            constellation_data.append(
                (
                    (float(ra1) / 360 * 24, float(dec1)),
                    (float(ra2) / 360 * 24, float(dec2)),
                )
            )
            constellations[name] = constellation_data
    return constellations

CONSTELLATION_DATA = _read_data()

class Constellation:
    """A single constellation."""
    def __init__(self, name, radec_pairs, plotter):
        self.name = name
        self.radec_pairs = radec_pairs
        self.plotter = plotter
        self.line_color = plotter.COLOR_MAP.get("k", "k") if plotter.dark_mode else "k"
        self.point_color = plotter.COLOR_MAP.get("black", "black") if plotter.dark_mode else "black"

    def draw(self, ax, when):
        """Draws the constellation on a matplotlib axis."""
        plotted = []
        for (ra1, dec1), (ra2, dec2) in self.radec_pairs:
            star1 = Star(ra_hours=ra1, dec_degrees=dec1)
            star2 = Star(ra_hours=ra2, dec_degrees=dec2)
            azi1, alt1 = self.plotter.calculator.compute_position(star1, when)
            azi2, alt2 = self.plotter.calculator.compute_position(star2, when)
            
            if alt1 > 90 and alt2 > 90:
                continue

            if (azi1, alt1) not in plotted:
                ax.scatter(azi1, alt1, s=10, alpha=0.1, color=self.point_color, edgecolor=self.point_color)
                plotted.append((azi1, alt1))
            if (azi2, alt2) not in plotted:
                ax.scatter(azi2, alt2, s=10, alpha=0.1, color=self.point_color, edgecolor=self.point_color)
                plotted.append((azi2, alt2))

            if azi2 - azi1 > math.pi:
                azi1 += math.pi * 2
            elif azi1 - azi2 > math.pi:
                azi2 += math.pi * 2
            ax.plot(np.linspace(azi1, azi2, 10), np.linspace(alt1, alt2, 10), "-", color=self.line_color, linewidth=1, alpha=0.1)

def build_constellations(plotter, whitelist=None):
    """Builds a list of Constellation objects."""
    constellations = []
    for name, radec_pairs in CONSTELLATION_DATA.items():
        if whitelist is None or name in whitelist:
            constellations.append(Constellation(name, radec_pairs, plotter))
    return constellations
